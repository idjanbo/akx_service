"""AKX Crypto Payment Gateway - Clerk authentication middleware."""

from typing import Annotated

from clerk_backend_api import AuthenticateRequestOptions, Clerk, authenticate_request
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.db import get_db
from src.models.user import User, UserRole


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

    def get_user_email(self, clerk_id: str) -> str:
        """Fetch user email from Clerk API.

        Args:
            clerk_id: Clerk user ID (e.g., user_xxx)

        Returns:
            User's primary email address
        """
        try:
            user = self._client.users.get(user_id=clerk_id)
            # Return primary email or first available email
            if user.email_addresses:
                primary = next(
                    (e for e in user.email_addresses if e.id == user.primary_email_address_id),
                    user.email_addresses[0],
                )
                return primary.email_address
            return ""
        except Exception:
            return ""


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
        # Sync user from Clerk to local DB - fetch email from Clerk API
        email = clerk.get_user_email(clerk_id)
        user = User(
            clerk_id=clerk_id,
            email=email,
            role=UserRole.GUEST,  # Default role for new users
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif not user.email:
        # Update email if missing (for existing users)
        email = clerk.get_user_email(clerk_id)
        if email:
            user.email = email
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
router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(user: Annotated[User, Depends(get_current_user)]):
    """Get current user profile with role information.

    Returns:
        Current user data including role for frontend RBAC
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

    return {
        "id": user.id,
        "clerk_id": user.clerk_id,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "totp_enabled": totp_enabled,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }
