"""Merchant Settings API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser
from src.db import get_db
from src.schemas.merchant_setting import (
    TELEGRAM_NOTIFICATION_TYPES,
    MerchantSettingResponse,
    PaymentSettingsUpdate,
    TelegramNotificationTypeInfo,
    TelegramSettingsUpdate,
)
from src.services.merchant_setting_service import MerchantSettingService
from src.utils.helpers import format_utc_datetime

router = APIRouter(prefix="/merchant-settings", tags=["merchant-settings"])


def get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> MerchantSettingService:
    """Create MerchantSettingService instance."""
    return MerchantSettingService(db)


def _to_response(settings) -> MerchantSettingResponse:
    """Convert MerchantSetting to response schema."""
    return MerchantSettingResponse(
        id=settings.id,
        merchant_id=settings.merchant_id,
        deposit_expiry_seconds=settings.deposit_expiry_seconds,
        callback_retry_count=settings.callback_retry_count,
        telegram_bot_enabled=settings.telegram_bot_enabled,
        telegram_chat_id=settings.telegram_chat_id,
        telegram_whitelist=settings.telegram_whitelist,
        telegram_notifications=settings.telegram_notifications,
        created_at=format_utc_datetime(settings.created_at),
        updated_at=format_utc_datetime(settings.updated_at),
    )


@router.get("", response_model=MerchantSettingResponse)
async def get_merchant_settings(
    user: CurrentUser,
    service: Annotated[MerchantSettingService, Depends(get_service)],
) -> MerchantSettingResponse:
    """Get current merchant's settings.

    Creates default settings if not exists.
    """
    merchant_id = user.get_effective_user_id()
    settings = await service.get_or_create_settings(merchant_id)
    return _to_response(settings)


@router.patch("/payment", response_model=MerchantSettingResponse)
async def update_payment_settings(
    user: CurrentUser,
    data: PaymentSettingsUpdate,
    service: Annotated[MerchantSettingService, Depends(get_service)],
) -> MerchantSettingResponse:
    """Update payment settings.

    - deposit_expiry_seconds: Order expiry time (60-3600 seconds)
    - callback_retry_count: Callback retry attempts (0-10)
    """
    settings = await service.update_payment_settings(user, data)
    return _to_response(settings)


@router.patch("/telegram", response_model=MerchantSettingResponse)
async def update_telegram_settings(
    user: CurrentUser,
    data: TelegramSettingsUpdate,
    service: Annotated[MerchantSettingService, Depends(get_service)],
) -> MerchantSettingResponse:
    """Update telegram bot settings.

    - telegram_bot_enabled: Enable/disable notifications
    - telegram_chat_id: Bound chat/group ID
    - telegram_whitelist: Allowed user IDs for commands
    - telegram_notifications: Enabled notification types
    """
    settings = await service.update_telegram_settings(user, data)
    return _to_response(settings)


@router.get("/telegram/notification-types", response_model=list[TelegramNotificationTypeInfo])
async def get_telegram_notification_types() -> list[TelegramNotificationTypeInfo]:
    """Get available telegram notification types.

    Returns a list of notification types that can be enabled:
    - address_income: 地址收入通知
    - address_expense: 地址支出通知
    - deposit_failed: 充值失败通知
    """
    return TELEGRAM_NOTIFICATION_TYPES
