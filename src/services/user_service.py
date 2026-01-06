"""User Service - Business logic for user management."""

from datetime import datetime
from decimal import Decimal

import pyotp
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.core.security import AESCipher
from src.models.fee_config import FeeConfig
from src.models.user import User, UserRole, generate_api_key
from src.utils.pagination import PaginatedResult, PaginationParams


def _get_cipher() -> AESCipher:
    """Get AES cipher for encrypting/decrypting secrets."""
    settings = get_settings()
    return AESCipher(settings.aes_encryption_key)


class UserService:
    """Service for user-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(
        self,
        params: PaginationParams,
        search: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> PaginatedResult[User]:
        """List users with filters and pagination.

        Note: Super admins are excluded from the list.

        Args:
            params: Pagination parameters
            search: Search by email
            role: Filter by role
            is_active: Filter by active status

        Returns:
            Paginated user list
        """
        query = select(User).where(User.role != UserRole.SUPER_ADMIN)

        if search:
            # Escape special LIKE characters to prevent pattern injection
            escaped = search.replace("%", r"\%").replace("_", r"\_")
            query = query.where(User.email.ilike(f"%{escaped}%"))
        if role is not None:
            query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch paginated results
        query = query.order_by(User.created_at.desc())
        query = query.offset(params.offset).limit(params.page_size)
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return PaginatedResult(
            items=users,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_user(self, user_id: int) -> User | None:
        """Get user by ID (excludes super admins).

        Args:
            user_id: User ID

        Returns:
            User or None
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id).where(User.role != UserRole.SUPER_ADMIN)
        )
        return result.scalar_one_or_none()

    async def update_user_role(self, user_id: int, role: UserRole) -> User | None:
        """Update user role.

        Args:
            user_id: User ID
            role: New role

        Returns:
            Updated user or None

        Raises:
            ValueError: If trying to set super_admin role
        """
        if role == UserRole.SUPER_ADMIN:
            raise ValueError("Cannot assign super_admin role")

        user = await self.get_user(user_id)
        if not user:
            return None

        user.role = role
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user_status(self, user_id: int, is_active: bool) -> User | None:
        """Update user active status.

        Args:
            user_id: User ID
            is_active: New status

        Returns:
            Updated user or None
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        user.is_active = is_active
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user_balance(self, user_id: int, balance: Decimal) -> User | None:
        """Update user balance.

        Args:
            user_id: User ID
            balance: New balance

        Returns:
            Updated user or None
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        user.balance = balance
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user_credit_limit(self, user_id: int, credit_limit: Decimal) -> User | None:
        """Update user credit limit.

        Args:
            user_id: User ID
            credit_limit: New credit limit

        Returns:
            Updated user or None

        Raises:
            ValueError: If credit limit is negative
        """
        if credit_limit < 0:
            raise ValueError("Credit limit cannot be negative")

        user = await self.get_user(user_id)
        if not user:
            return None

        user.credit_limit = credit_limit
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user_fee_config(self, user_id: int, fee_config_id: int | None) -> User | None:
        """Update user fee configuration.

        Args:
            user_id: User ID
            fee_config_id: New fee config ID (or None to use default)

        Returns:
            Updated user or None

        Raises:
            ValueError: If fee config not found
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        if fee_config_id is not None:
            fee_config = await self.db.get(FeeConfig, fee_config_id)
            if not fee_config:
                raise ValueError("Fee config not found")

        user.fee_config_id = fee_config_id
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def reset_deposit_key(self, user_id: int) -> str | None:
        """Reset user deposit API key.

        Args:
            user_id: User ID

        Returns:
            New key or None if user not found
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        new_key = generate_api_key()
        user.deposit_key = new_key
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        return new_key

    async def reset_withdraw_key(self, user_id: int) -> str | None:
        """Reset user withdrawal API key.

        Args:
            user_id: User ID

        Returns:
            New key or None if user not found
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        new_key = generate_api_key()
        user.withdraw_key = new_key
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()
        return new_key

    async def reset_google_secret(self, user_id: int) -> dict[str, str] | None:
        """Reset user Google authenticator secret.

        Args:
            user_id: User ID

        Returns:
            Dict with secret and qr_uri, or None if user not found
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        secret = pyotp.random_base32()

        # Encrypt the secret before storing (marked as pending until enabled)
        cipher = _get_cipher()
        encrypted_secret = cipher.encrypt(f"pending:{secret}")
        user.google_secret = encrypted_secret
        user.updated_at = datetime.now(datetime.UTC)
        self.db.add(user)
        await self.db.commit()

        totp = pyotp.TOTP(secret)
        qr_uri = totp.provisioning_uri(name=user.email, issuer_name="AKX Payment")

        return {"secret": secret, "qr_uri": qr_uri}

    async def verify_totp(self, user: User, code: str) -> bool:
        """Verify TOTP code for user.

        Args:
            user: User to verify
            code: TOTP code

        Returns:
            True if valid, False otherwise
        """
        if not user.google_secret:
            return False

        totp = pyotp.TOTP(user.google_secret)
        return totp.verify(code)
