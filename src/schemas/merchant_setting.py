"""Merchant Settings API schemas."""

from pydantic import BaseModel, Field


class PaymentSettingsUpdate(BaseModel):
    """Schema for updating payment settings."""

    deposit_expiry_seconds: int | None = Field(
        default=None,
        ge=60,
        le=3600,
        description="Order expiry time in seconds (60-3600, i.e., 1-60 minutes)",
    )
    callback_retry_count: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Number of callback retry attempts (0-10)",
    )


class TelegramSettingsUpdate(BaseModel):
    """Schema for updating telegram bot settings."""

    telegram_bot_enabled: bool | None = Field(
        default=None,
        description="Whether telegram bot notifications are enabled",
    )
    telegram_chat_id: str | None = Field(
        default=None,
        max_length=64,
        description="Telegram group/chat ID bound to this merchant",
    )
    telegram_whitelist: list[str] | None = Field(
        default=None,
        description="List of allowed Telegram user IDs who can send commands",
    )
    telegram_notifications: list[str] | None = Field(
        default=None,
        description="List of enabled notification types",
    )


class MerchantSettingResponse(BaseModel):
    """Response schema for merchant settings."""

    id: int
    merchant_id: int

    # Payment Settings
    deposit_expiry_seconds: int
    callback_retry_count: int

    # Telegram Bot Settings
    telegram_bot_enabled: bool
    telegram_chat_id: str | None
    telegram_whitelist: list[str]
    telegram_notifications: list[str]

    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TelegramNotificationTypeInfo(BaseModel):
    """Info about a telegram notification type."""

    value: str
    label: str
    description: str


TELEGRAM_NOTIFICATION_TYPES = [
    TelegramNotificationTypeInfo(
        value="address_income",
        label="地址收入",
        description="当钱包地址收到转账时通知",
    ),
    TelegramNotificationTypeInfo(
        value="address_expense",
        label="地址支出",
        description="当钱包地址发生支出时通知",
    ),
    TelegramNotificationTypeInfo(
        value="deposit_failed",
        label="充值失败",
        description="充值下单失败时通知（含失败原因）",
    ),
]
