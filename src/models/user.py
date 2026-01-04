"""AKX Crypto Payment Gateway - User model."""

import secrets
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.fee_config import FeeConfig
    from src.models.wallet import Wallet


class UserRole(str, Enum):
    """User roles for access control."""

    SUPER_ADMIN = "super_admin"
    MERCHANT = "merchant"
    SUPPORT = "support"
    GUEST = "guest"


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
    role: UserRole = Field(default=UserRole.GUEST)
    google_secret: str | None = Field(default=None, max_length=512)
    is_active: bool = Field(default=True)

    # Merchant-specific fields
    balance: Decimal = Field(
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

    # Relationships
    wallets: list["Wallet"] = Relationship(back_populates="user")
    fee_config: Optional["FeeConfig"] = Relationship(back_populates="users")
