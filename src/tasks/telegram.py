"""Telegram notification tasks."""

import asyncio
import logging
from decimal import Decimal

from celery import shared_task

from src.db.engine import close_db, get_session
from src.models.merchant_setting import MerchantSetting, TelegramNotificationType
from src.services.telegram_service import (
    send_address_expense_notification,
    send_address_income_notification,
    send_deposit_failed_notification,
    should_send_notification,
)

logger = logging.getLogger(__name__)


async def _get_merchant_telegram_settings(
    merchant_id: int,
) -> tuple[bool, str | None, list[str]]:
    """Get merchant's telegram settings.

    Args:
        merchant_id: Merchant user ID

    Returns:
        Tuple of (telegram_bot_enabled, telegram_chat_id, telegram_notifications)
    """
    from sqlmodel import select

    try:
        async with get_session() as db:
            query = select(MerchantSetting).where(MerchantSetting.merchant_id == merchant_id)
            result = await db.execute(query)
            settings = result.scalar_one_or_none()

            if not settings:
                return False, None, []

            return (
                settings.telegram_bot_enabled,
                settings.telegram_chat_id,
                settings.telegram_notifications,
            )
    finally:
        await close_db()


@shared_task(name="telegram.send_address_income")
def send_address_income_task(
    merchant_id: int,
    address: str,
    amount: str,
    token: str,
    chain: str,
    tx_hash: str,
    from_address: str | None = None,
) -> bool:
    """Celery task to send address income notification.

    Args:
        merchant_id: Merchant user ID
        address: Receiving address
        amount: Transaction amount (as string)
        token: Token symbol
        chain: Chain name
        tx_hash: Transaction hash
        from_address: Sender address (optional)

    Returns:
        True if sent successfully
    """

    async def _send():
        try:
            # Get merchant settings
            enabled, chat_id, notifications = await _get_merchant_telegram_settings(merchant_id)

            # Check if should send
            if not await should_send_notification(
                TelegramNotificationType.ADDRESS_INCOME,
                enabled,
                notifications,
                chat_id,
            ):
                logger.debug(
                    "Skipping address income notification for merchant %s (not enabled)",
                    merchant_id,
                )
                return False

            # Send notification
            return await send_address_income_notification(
                chat_id=chat_id,  # type: ignore
                address=address,
                amount=Decimal(amount),
                token=token,
                chain=chain,
                tx_hash=tx_hash,
                from_address=from_address,
            )
        except Exception as e:
            logger.error("Failed to send address income notification: %s", e)
            return False

    return asyncio.get_event_loop().run_until_complete(_send())


@shared_task(name="telegram.send_address_expense")
def send_address_expense_task(
    merchant_id: int,
    address: str,
    amount: str,
    token: str,
    chain: str,
    tx_hash: str,
    to_address: str | None = None,
) -> bool:
    """Celery task to send address expense notification.

    Args:
        merchant_id: Merchant user ID
        address: Sending address
        amount: Transaction amount (as string)
        token: Token symbol
        chain: Chain name
        tx_hash: Transaction hash
        to_address: Recipient address (optional)

    Returns:
        True if sent successfully
    """

    async def _send():
        try:
            # Get merchant settings
            enabled, chat_id, notifications = await _get_merchant_telegram_settings(merchant_id)

            # Check if should send
            if not await should_send_notification(
                TelegramNotificationType.ADDRESS_EXPENSE,
                enabled,
                notifications,
                chat_id,
            ):
                logger.debug(
                    "Skipping address expense notification for merchant %s (not enabled)",
                    merchant_id,
                )
                return False

            # Send notification
            return await send_address_expense_notification(
                chat_id=chat_id,  # type: ignore
                address=address,
                amount=Decimal(amount),
                token=token,
                chain=chain,
                tx_hash=tx_hash,
                to_address=to_address,
            )
        except Exception as e:
            logger.error("Failed to send address expense notification: %s", e)
            return False

    return asyncio.get_event_loop().run_until_complete(_send())


@shared_task(name="telegram.send_deposit_failed")
def send_deposit_failed_task(
    merchant_id: int,
    order_no: str,
    amount: str,
    token: str,
    reason: str,
    merchant_order_no: str | None = None,
) -> bool:
    """Celery task to send deposit failed notification.

    Args:
        merchant_id: Merchant user ID
        order_no: System order number
        amount: Order amount (as string)
        token: Token symbol
        reason: Failure reason
        merchant_order_no: Merchant order number (optional)

    Returns:
        True if sent successfully
    """

    async def _send():
        try:
            # Get merchant settings
            enabled, chat_id, notifications = await _get_merchant_telegram_settings(merchant_id)

            # Check if should send
            if not await should_send_notification(
                TelegramNotificationType.DEPOSIT_FAILED,
                enabled,
                notifications,
                chat_id,
            ):
                logger.debug(
                    "Skipping deposit failed notification for merchant %s (not enabled)",
                    merchant_id,
                )
                return False

            # Send notification
            return await send_deposit_failed_notification(
                chat_id=chat_id,  # type: ignore
                order_no=order_no,
                amount=Decimal(amount),
                token=token,
                reason=reason,
                merchant_order_no=merchant_order_no,
            )
        except Exception as e:
            logger.error("Failed to send deposit failed notification: %s", e)
            return False

    return asyncio.get_event_loop().run_until_complete(_send())


# ============ Convenience Functions for Service Layer ============


def trigger_address_income_notification(
    merchant_id: int,
    address: str,
    amount: Decimal,
    token: str,
    chain: str,
    tx_hash: str,
    from_address: str | None = None,
) -> None:
    """Trigger address income notification task.

    This is a fire-and-forget function to be called from service layer.

    Args:
        merchant_id: Merchant user ID
        address: Receiving address
        amount: Transaction amount
        token: Token symbol
        chain: Chain name
        tx_hash: Transaction hash
        from_address: Sender address (optional)
    """
    send_address_income_task.delay(
        merchant_id=merchant_id,
        address=address,
        amount=str(amount),
        token=token,
        chain=chain,
        tx_hash=tx_hash,
        from_address=from_address,
    )


def trigger_address_expense_notification(
    merchant_id: int,
    address: str,
    amount: Decimal,
    token: str,
    chain: str,
    tx_hash: str,
    to_address: str | None = None,
) -> None:
    """Trigger address expense notification task.

    This is a fire-and-forget function to be called from service layer.

    Args:
        merchant_id: Merchant user ID
        address: Sending address
        amount: Transaction amount
        token: Token symbol
        chain: Chain name
        tx_hash: Transaction hash
        to_address: Recipient address (optional)
    """
    send_address_expense_task.delay(
        merchant_id=merchant_id,
        address=address,
        amount=str(amount),
        token=token,
        chain=chain,
        tx_hash=tx_hash,
        to_address=to_address,
    )


def trigger_deposit_failed_notification(
    merchant_id: int,
    order_no: str,
    amount: Decimal,
    token: str,
    reason: str,
    merchant_order_no: str | None = None,
) -> None:
    """Trigger deposit failed notification task.

    This is a fire-and-forget function to be called from service layer.

    Args:
        merchant_id: Merchant user ID
        order_no: System order number
        amount: Order amount
        token: Token symbol
        reason: Failure reason
        merchant_order_no: Merchant order number (optional)
    """
    send_deposit_failed_task.delay(
        merchant_id=merchant_id,
        order_no=order_no,
        amount=str(amount),
        token=token,
        reason=reason,
        merchant_order_no=merchant_order_no,
    )
