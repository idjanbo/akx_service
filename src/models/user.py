"""AKX Crypto Payment Gateway - User model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.wallet import Wallet


class UserRole(str, Enum):
    """User roles for access control."""

    SUPER_ADMIN = "super_admin"
    MERCHANT = "merchant"
    SUPPORT = "support"


class User(SQLModel, table=True):
    """User model - synced from Clerk.

    Attributes:
        id: Auto-increment primary key
        clerk_id: Unique Clerk user ID (indexed)
        email: User email address (indexed)
        role: User role for RBAC
        google_secret: Encrypted TOTP secret for sensitive operations
        is_active: Account status
    """

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    clerk_id: str = Field(max_length=255, unique=True, index=True)
    email: str = Field(max_length=255, index=True)
    role: UserRole = Field(default=UserRole.MERCHANT)
    google_secret: str | None = Field(default=None, max_length=512)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    wallets: list["Wallet"] = Relationship(back_populates="user")
