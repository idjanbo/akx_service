"""AKX Crypto Payment Gateway - Merchant Settings model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.user import User


class TelegramNotificationType(str):
    """Telegram notification types that can be enabled."""

    ADDRESS_INCOME = "address_income"  # 地址收入
    ADDRESS_EXPENSE = "address_expense"  # 地址支出
    DEPOSIT_FAILED = "deposit_failed"  # 充值下单失败及原因


class MerchantSetting(SQLModel, table=True):
    """Merchant settings for payment and notification configuration.

    Each merchant can have customized settings for:
    - Payment: order expiry time, callback retry count
    - Telegram Bot: notification preferences, group bindings

    Attributes:
        id: Auto-increment primary key
        merchant_id: Foreign key to users table (unique, one-to-one)

        # Payment Settings
        deposit_expiry_seconds: Order expiry time in seconds (default 600 = 10 minutes)
        callback_retry_count: Number of callback retry attempts (default 3)

        # Telegram Bot Settings
        telegram_bot_enabled: Whether telegram bot notifications are enabled
        telegram_chat_id: Telegram group/chat ID bound to this merchant
        telegram_whitelist: JSON list of allowed user IDs who can send commands
        telegram_notifications: JSON list of enabled notification types
    """

    __tablename__ = "merchant_settings"

    id: int | None = Field(default=None, primary_key=True)
    merchant_id: int = Field(
        foreign_key="users.id",
        unique=True,
        index=True,
        description="Merchant user ID (one-to-one relationship)",
    )

    # ============ Payment Settings ============
    deposit_expiry_seconds: int = Field(
        default=600,
        ge=60,
        le=3600,
        description="Order expiry time in seconds (1-60 minutes)",
    )
    callback_retry_count: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of callback retry attempts (0-10)",
    )

    # ============ Telegram Bot Settings ============
    telegram_bot_enabled: bool = Field(
        default=False,
        description="Whether telegram bot notifications are enabled",
    )
    telegram_chat_id: str | None = Field(
        default=None,
        max_length=64,
        description="Telegram group/chat ID bound to this merchant",
    )
    telegram_whitelist: list[str] = Field(
        default=[],
        sa_column=sa.Column(sa.JSON, nullable=False, default=[]),
        description="List of allowed Telegram user IDs who can send commands",
    )
    telegram_notifications: list[str] = Field(
        default=[],
        sa_column=sa.Column(sa.JSON, nullable=False, default=[]),
        description="List of enabled notification types",
    )

    # ============ Timestamps ============
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record creation time",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Record last update time",
    )

    # ============ Relationships ============
    merchant: Optional["User"] = Relationship(
        back_populates="merchant_setting",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
