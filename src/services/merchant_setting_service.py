"""Merchant Settings Service - Business logic for merchant settings."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.merchant_setting import MerchantSetting
from src.models.user import User
from src.schemas.merchant_setting import (
    PaymentSettingsUpdate,
    TelegramSettingsUpdate,
)


class MerchantSettingService:
    """Service for managing merchant settings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_settings(self, merchant_id: int) -> MerchantSetting:
        """Get merchant settings, creating default if not exists.

        Args:
            merchant_id: Merchant user ID

        Returns:
            MerchantSetting instance
        """
        query = select(MerchantSetting).where(MerchantSetting.merchant_id == merchant_id)
        result = await self.db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            # Create default settings
            settings = MerchantSetting(merchant_id=merchant_id)
            self.db.add(settings)
            await self.db.commit()
            await self.db.refresh(settings)

        return settings

    async def get_settings_by_merchant(self, merchant_id: int) -> MerchantSetting | None:
        """Get merchant settings by merchant ID.

        Args:
            merchant_id: Merchant user ID

        Returns:
            MerchantSetting if found, None otherwise
        """
        query = select(MerchantSetting).where(MerchantSetting.merchant_id == merchant_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_payment_settings(
        self,
        user: User,
        data: PaymentSettingsUpdate,
    ) -> MerchantSetting:
        """Update payment settings for a merchant.

        Args:
            user: Current user (merchant)
            data: Payment settings update data

        Returns:
            Updated MerchantSetting
        """
        merchant_id = user.get_effective_user_id()
        settings = await self.get_or_create_settings(merchant_id)

        # Update only provided fields
        if data.deposit_expiry_seconds is not None:
            settings.deposit_expiry_seconds = data.deposit_expiry_seconds
        if data.callback_retry_count is not None:
            settings.callback_retry_count = data.callback_retry_count

        settings.updated_at = datetime.utcnow()
        self.db.add(settings)
        await self.db.commit()
        await self.db.refresh(settings)

        return settings

    async def update_telegram_settings(
        self,
        user: User,
        data: TelegramSettingsUpdate,
    ) -> MerchantSetting:
        """Update telegram bot settings for a merchant.

        Args:
            user: Current user (merchant)
            data: Telegram settings update data

        Returns:
            Updated MerchantSetting
        """
        merchant_id = user.get_effective_user_id()
        settings = await self.get_or_create_settings(merchant_id)

        # Update only provided fields
        if data.telegram_bot_enabled is not None:
            settings.telegram_bot_enabled = data.telegram_bot_enabled
        if data.telegram_chat_id is not None:
            settings.telegram_chat_id = data.telegram_chat_id
        if data.telegram_whitelist is not None:
            settings.telegram_whitelist = data.telegram_whitelist
        if data.telegram_notifications is not None:
            settings.telegram_notifications = data.telegram_notifications

        settings.updated_at = datetime.utcnow()
        self.db.add(settings)
        await self.db.commit()
        await self.db.refresh(settings)

        return settings

    async def get_deposit_expiry_seconds(self, merchant_id: int, default: int = 600) -> int:
        """Get deposit expiry seconds for a merchant.

        Args:
            merchant_id: Merchant user ID
            default: Default value if no settings found

        Returns:
            Deposit expiry seconds
        """
        settings = await self.get_settings_by_merchant(merchant_id)
        if settings:
            return settings.deposit_expiry_seconds
        return default

    async def get_callback_retry_count(self, merchant_id: int, default: int = 3) -> int:
        """Get callback retry count for a merchant.

        Args:
            merchant_id: Merchant user ID
            default: Default value if no settings found

        Returns:
            Callback retry count
        """
        settings = await self.get_settings_by_merchant(merchant_id)
        if settings:
            return settings.callback_retry_count
        return default
