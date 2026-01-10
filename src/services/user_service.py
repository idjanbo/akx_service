"""User Service - Business logic for user management."""

from datetime import UTC, datetime
from decimal import Decimal

import pyotp
from fastapi_pagination.ext.sqlmodel import apaginate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.core.security import AESCipher
from src.models.fee_config import FeeConfig
from src.models.user import SupportPermission, User, UserRole, generate_api_key
from src.schemas.pagination import CustomPage
from src.schemas.user import UserResponse


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
        search: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> CustomPage[UserResponse]:
        """List users with filters and pagination.

        Note: Super admins are excluded from the list.

        Args:
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

        query = query.order_by(User.created_at.desc())

        return await apaginate(
            self.db,
            query,
            transformer=lambda items: [UserResponse.model_validate(u) for u in items],
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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
        user.updated_at = datetime.now(UTC)
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

    # ============ Support User Management (客服管理) ============

    async def list_support_users(self, merchant: User) -> list[User]:
        """List all support users for a merchant.

        Args:
            merchant: The merchant user

        Returns:
            List of support users belonging to this merchant
        """
        result = await self.db.execute(
            select(User)
            .where(
                User.parent_id == merchant.id,
                User.role == UserRole.SUPPORT,
            )
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_support_permissions(
        self,
        merchant: User,
        support_id: int,
        permissions: list[str],
    ) -> User:
        """Update support user permissions.

        Args:
            merchant: The merchant user
            support_id: Support user ID
            permissions: New list of permissions

        Returns:
            Updated support user

        Raises:
            ValueError: If support user not found or doesn't belong to merchant
        """
        user = await self.db.get(User, support_id)
        if not user:
            raise ValueError("Support user not found")

        if user.parent_id != merchant.id:
            raise ValueError("Support user doesn't belong to this merchant")

        if user.role != UserRole.SUPPORT:
            raise ValueError("User is not a support user")

        # Validate permissions
        valid_permissions = {p.value for p in SupportPermission}
        for perm in permissions:
            if perm not in valid_permissions:
                raise ValueError(f"Invalid permission: {perm}")

        user.permissions = permissions
        user.updated_at = datetime.now(UTC)

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def toggle_support_status(
        self,
        merchant: User,
        support_id: int,
        is_active: bool,
    ) -> User:
        """Toggle support user active status.

        Args:
            merchant: The merchant user
            support_id: Support user ID
            is_active: New active status

        Returns:
            Updated support user

        Raises:
            ValueError: If support user not found or doesn't belong to merchant
        """
        user = await self.db.get(User, support_id)
        if not user:
            raise ValueError("Support user not found")

        if user.parent_id != merchant.id:
            raise ValueError("Support user doesn't belong to this merchant")

        if user.role != UserRole.SUPPORT:
            raise ValueError("User is not a support user")

        user.is_active = is_active
        user.updated_at = datetime.now(UTC)

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def remove_support_user(
        self,
        merchant: User,
        support_id: int,
    ) -> bool:
        """Remove a support user.

        This removes the support relationship and deactivates the user.
        The user can be re-invited later if needed.

        Args:
            merchant: The merchant user
            support_id: Support user ID to remove

        Returns:
            True if removed, False if not found

        Raises:
            ValueError: If support user doesn't belong to merchant
        """
        user = await self.db.get(User, support_id)
        if not user:
            return False

        if user.parent_id != merchant.id:
            raise ValueError("Support user doesn't belong to this merchant")

        if user.role != UserRole.SUPPORT:
            raise ValueError("User is not a support user")

        # Deactivate user and remove relationship
        user.is_active = False
        user.parent_id = None
        user.permissions = []
        user.updated_at = datetime.now(UTC)

        self.db.add(user)
        await self.db.commit()
        return True
