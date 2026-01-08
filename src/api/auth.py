"""AKX Crypto Payment Gateway - Clerk authentication middleware."""

from typing import Annotated

from clerk_backend_api import AuthenticateRequestOptions, Clerk, authenticate_request
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.db import get_db
from src.models.user import User, UserRole
from src.utils.totp import totp_required


class ClerkAuth:
    """Clerk authentication handler.

    Verifies JWT tokens from Clerk and syncs users to local database.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = Clerk(bearer_auth=settings.clerk_secret_key)

    async def verify_token(self, request: Request) -> dict:
        """Verify Clerk JWT token from request.

        Args:
            request: FastAPI request object

        Returns:
            Decoded JWT claims

        Raises:
            HTTPException: If token is invalid or missing
        """
        try:
            request_state = authenticate_request(
                request,
                AuthenticateRequestOptions(secret_key=get_settings().clerk_secret_key),
            )

            if not request_state.is_signed_in:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                )

            return request_state.payload or {}

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Authentication failed: {e!s}",
            ) from e

    def get_user_info(self, clerk_id: str) -> dict[str, str]:
        """Fetch user info from Clerk API.

        Args:
            clerk_id: Clerk user ID (e.g., user_xxx)

        Returns:
            Dict with email and username
        """
        try:
            user = self._client.users.get(user_id=clerk_id)
            email = ""
            username = ""

            # Get primary email or first available email
            if user.email_addresses:
                primary = next(
                    (e for e in user.email_addresses if e.id == user.primary_email_address_id),
                    user.email_addresses[0],
                )
                email = primary.email_address

            # Get username (Clerk stores it as username field)
            if user.username:
                username = user.username

            return {"email": email, "username": username}
        except Exception:
            return {"email": "", "username": ""}

    def get_user_email(self, clerk_id: str) -> str:
        """Fetch user email from Clerk API (legacy, use get_user_info instead)."""
        return self.get_user_info(clerk_id).get("email", "")


# Singleton instance
_clerk_auth: ClerkAuth | None = None


def get_clerk_auth() -> ClerkAuth:
    """Get Clerk auth singleton."""
    global _clerk_auth
    if _clerk_auth is None:
        _clerk_auth = ClerkAuth()
    return _clerk_auth


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    clerk: Annotated[ClerkAuth, Depends(get_clerk_auth)],
) -> User:
    """FastAPI dependency to get current authenticated user.

    Verifies Clerk token and syncs user to local database if needed.

    Usage:
        @router.get("/profile")
        async def get_profile(user: User = Depends(get_current_user)):
            return user
    """
    claims = await clerk.verify_token(request)

    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
        )

    # Find or create user in local database
    result = await db.execute(select(User).where(User.clerk_id == clerk_id))
    user = result.scalar_one_or_none()

    if not user:
        # User not in local DB - this shouldn't happen in invitation-only mode
        # The user should have been created via webhook when they registered
        # For safety, we reject the request
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found. Please complete registration via invitation link.",
        )
    else:
        # Update email/username if changed (sync from Clerk)
        user_info = clerk.get_user_info(clerk_id)
        updated = False
        if user_info.get("email") and user.email != user_info["email"]:
            user.email = user_info["email"]
            updated = True
        if user_info.get("username") and user.username != user_info["username"]:
            user.username = user_info["username"]
            updated = True
        if updated:
            db.add(user)
            await db.commit()
            await db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


def require_role(*roles: UserRole):
    """Factory for role-based access control dependency.

    Usage:
        @router.post("/admin/settings")
        async def update_settings(
            user: User = Depends(require_role(UserRole.SUPER_ADMIN))
        ):
            ...
    """

    async def role_checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {', '.join(r.value for r in roles)}",
            )
        return user

    return role_checker


# Convenience dependency factories (use with Depends())
def require_admin():
    """Require super admin role."""
    return require_role(UserRole.SUPER_ADMIN)


# Alias for require_admin
require_super_admin = require_admin


def require_merchant():
    """Require merchant or super admin role."""
    return require_role(UserRole.MERCHANT, UserRole.SUPER_ADMIN)


# FastAPI Router
router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me")
async def get_me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get current user profile with role information.

    Returns:
        Current user data including role for frontend RBAC
        For merchants: includes merchant_no, deposit_key, withdraw_key
        For support users: includes parent merchant's keys
    """
    # 检查 TOTP 是否已启用（有 google_secret 且不是 pending 状态）
    totp_enabled = False
    if user.google_secret:
        # google_secret 是加密存储的，这里只检查是否存在
        # pending 状态的密钥以 "pending:" 开头（加密前）
        # 由于是加密的，我们需要解密后检查
        from src.core.config import get_settings
        from src.core.security import AESCipher

        try:
            cipher = AESCipher(get_settings().aes_encryption_key)
            decrypted = cipher.decrypt(user.google_secret)
            totp_enabled = not decrypted.startswith("pending:")
        except Exception:
            totp_enabled = False

    # Base response
    response = {
        "id": user.id,
        "clerk_id": user.clerk_id,
        "email": user.email,
        "username": user.username,
        "nickname": user.nickname,
        "role": user.role.value,
        "is_active": user.is_active,
        "totp_enabled": totp_enabled,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }

    # For merchants: include merchant keys and balance
    if user.role == UserRole.MERCHANT:
        response.update(
            {
                "balance": str(user.balance),
                "frozen_balance": str(user.frozen_balance),
                "credit_limit": str(user.credit_limit),
                "merchant_no": f"M{user.id}",
                "deposit_key": user.deposit_key,
                "withdraw_key": user.withdraw_key,
            }
        )

    # For support users: include parent merchant's info
    if user.role == UserRole.SUPPORT and user.parent_id:
        parent = await db.get(User, user.parent_id)
        if parent:
            response.update(
                {
                    "parent_id": parent.id,
                    "permissions": user.permissions or [],
                    # Include parent merchant's keys for support user reference
                    "parent_merchant_no": f"M{parent.id}",
                    "parent_deposit_key": parent.deposit_key,
                    "parent_withdraw_key": parent.withdraw_key,
                }
            )

    return response


class ResetKeyRequest(BaseModel):
    """Request model for resetting API keys (requires TOTP)."""

    totp_code: str = PydanticField(..., min_length=6, max_length=6, description="TOTP 验证码")


@router.post("/me/reset-deposit-key")
@totp_required
async def reset_my_deposit_key(
    data: ResetKeyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reset current user's deposit API key (merchant only, requires TOTP).

    Returns:
        New deposit key
    """
    if user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can reset deposit keys",
        )

    import secrets

    new_key = secrets.token_hex(32)
    user.deposit_key = new_key
    db.add(user)
    await db.commit()

    return {"key": new_key}


@router.post("/me/reset-withdraw-key")
@totp_required
async def reset_my_withdraw_key(
    data: ResetKeyRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Reset current user's withdraw API key (merchant only, requires TOTP).

    Returns:
        New withdraw key
    """
    if user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can reset withdraw keys",
        )

    import secrets

    new_key = secrets.token_hex(32)
    user.withdraw_key = new_key
    db.add(user)
    await db.commit()

    return {"key": new_key}


class UpdateNicknameRequest(BaseModel):
    """Request model for updating nickname."""

    nickname: str = PydanticField(..., min_length=1, max_length=50, description="用户昵称")


@router.patch("/me/nickname")
async def update_my_nickname(
    request: UpdateNicknameRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update current user's nickname.

    Returns:
        Updated nickname
    """
    user.nickname = request.nickname.strip()
    db.add(user)
    await db.commit()

    return {"nickname": user.nickname}
