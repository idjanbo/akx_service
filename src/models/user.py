"""AKX Crypto Payment Gateway - User model."""

import secrets
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.exchange_rate import ExchangeRate
    from src.models.fee_config import FeeConfig
    from src.models.merchant_setting import MerchantSetting
    from src.models.wallet import Wallet


class UserRole(str, Enum):
    """User roles for access control."""

    SUPER_ADMIN = "super_admin"
    MERCHANT = "merchant"
    SUPPORT = "support"


class SupportPermission(str, Enum):
    """Permissions that can be granted to support users by their parent merchant.

    Support users can have any combination of these permissions.
    """

    # View permissions
    VIEW_WALLETS = "view_wallets"  # 查看钱包
    VIEW_ORDERS = "view_orders"  # 查看订单
    VIEW_TRANSACTIONS = "view_transactions"  # 查看交易流水
    VIEW_ASSETS = "view_assets"  # 查看资产

    # Action permissions
    CREATE_WALLETS = "create_wallets"  # 创建钱包
    EXPORT_DATA = "export_data"  # 导出数据


def generate_api_key() -> str:
    """Generate a secure 32-byte hex API key."""
    return secrets.token_hex(32)


class User(SQLModel, table=True):
    """User model - synced from Clerk.

    Attributes:
        id: Auto-increment primary key
        clerk_id: Unique Clerk user ID (indexed)
        email: User email address (indexed)
        role: User role for RBAC
        google_secret: Encrypted TOTP secret for sensitive operations
        is_active: Account status

        # Support user fields (子账号)
        parent_id: Parent merchant ID (for support users only)
        permissions: JSON list of granted permissions (for support users only)

        # Merchant-specific fields
        balance: Account balance (can be negative up to credit_limit)
        credit_limit: Maximum negative balance allowed (赊账额度)
        deposit_key: API key for deposit operations
        withdraw_key: API key for withdrawal operations
        fee_config_id: Associated fee rate configuration
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    clerk_id: str = Field(max_length=255, unique=True, index=True)
    email: str = Field(max_length=255, index=True)
    username: str | None = Field(default=None, max_length=255)
    nickname: str | None = Field(default=None, max_length=255)  # 用户昵称
    role: UserRole = Field(default=UserRole.MERCHANT)  # Default for invited users
    google_secret: str | None = Field(default=None, max_length=512)
    is_active: bool = Field(default=True)

    # Support user fields (子账号) - support users belong to a merchant
    parent_id: int | None = Field(default=None, foreign_key="users.id", index=True)
    permissions: list[str] = Field(
        default=[],
        sa_column=sa.Column(sa.JSON, nullable=False, default=[]),
    )

    # Merchant-specific fields
    balance: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
    )
    frozen_balance: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
    )
    credit_limit: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
    )
    deposit_key: str | None = Field(default=None, max_length=64, index=True)
    withdraw_key: str | None = Field(default=None, max_length=64, index=True)
    fee_config_id: int | None = Field(default=None, foreign_key="fee_configs.id")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships - use selectin for fee_config to avoid async lazy-load issues
    wallets: list["Wallet"] = Relationship(back_populates="user")
    fee_config: Optional["FeeConfig"] = Relationship(
        back_populates="users",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    exchange_rates: list["ExchangeRate"] = Relationship(back_populates="user")
    # Merchant settings (one-to-one)
    merchant_setting: Optional["MerchantSetting"] = Relationship(
        back_populates="merchant",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    # Self-referential relationship for parent merchant
    parent: Optional["User"] = Relationship(
        sa_relationship_kwargs={
            "remote_side": "User.id",
            "lazy": "selectin",
        },
    )

    # ============ Helper Methods ============

    def get_effective_user_id(self) -> int:
        """Get the effective user ID for data access.

        For support users, returns the parent merchant's ID.
        For all other users, returns their own ID.

        This ensures support users access their parent merchant's data.
        """
        if self.role == UserRole.SUPPORT and self.parent_id:
            return self.parent_id
        return self.id  # type: ignore

    def has_permission(self, permission: SupportPermission | str) -> bool:
        """Check if user has a specific permission.

        Super admins and merchants have all permissions.
        Support users only have explicitly granted permissions.

        Args:
            permission: Permission to check (SupportPermission enum or string)

        Returns:
            True if user has the permission
        """
        # Super admin and merchant have all permissions
        if self.role in (UserRole.SUPER_ADMIN, UserRole.MERCHANT):
            return True

        # Support users check their granted permissions
        if self.role == UserRole.SUPPORT:
            perm_value = (
                permission.value if isinstance(permission, SupportPermission) else permission
            )
            return perm_value in self.permissions

        return False
