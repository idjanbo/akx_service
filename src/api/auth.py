"""AKX Crypto Payment Gateway - Clerk authentication middleware."""

from typing import Annotated

from clerk_backend_api import AuthenticateRequestOptions, Clerk, authenticate_request
from fastapi import Depends, HTTPException, Request, status
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
                self._client,
                request,
                AuthenticateRequestOptions(),
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
        # Sync user from Clerk to local DB
        email = claims.get("email", "")
        user = User(
            clerk_id=clerk_id,
            email=email,
            role=UserRole.MERCHANT,  # Default role
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def require_role(*roles: UserRole):
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


# Convenience dependencies
RequireAdmin = Depends(require_role(UserRole.SUPER_ADMIN))
RequireMerchant = Depends(require_role(UserRole.MERCHANT, UserRole.SUPER_ADMIN))
