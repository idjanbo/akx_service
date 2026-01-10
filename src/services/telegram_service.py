"""Telegram Bot Service - Send notifications and handle commands."""

import logging
from decimal import Decimal
from typing import Any

import httpx

from src.core.config import get_settings

logger = logging.getLogger(__name__)


class TelegramService:
    """Service for sending Telegram notifications."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str | None = None):
        """Initialize Telegram service.

        Args:
            bot_token: Telegram bot token. If not provided, uses config.
        """
        settings = get_settings()
        self.bot_token = bot_token or settings.telegram_bot_token

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> dict[str, Any] | None:
        """Send a text message to a chat.

        Args:
            chat_id: Telegram chat/group ID
            text: Message text (supports HTML formatting)
            parse_mode: Parse mode (HTML or Markdown)
            disable_notification: Send silently

        Returns:
            Telegram API response or None on error
        """
        if not self.bot_token:
            logger.warning("Telegram bot token not configured, skipping notification")
            return None

        url = self.BASE_URL.format(token=self.bot_token, method="sendMessage")
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                result = response.json()

                if not result.get("ok"):
                    logger.error(
                        "Telegram API error: %s",
                        result.get("description", "Unknown error"),
                    )
                    return None

                return result
        except httpx.RequestError as e:
            logger.error("Telegram request failed: %s", e)
            return None

    # ============ Notification Templates ============

    def format_address_income_message(
        self,
        address: str,
        amount: Decimal,
        token: str,
        chain: str,
        tx_hash: str,
        from_address: str | None = None,
    ) -> str:
        """Format address income notification message.

        Args:
            address: Receiving address
            amount: Transaction amount
            token: Token symbol (e.g., USDT)
            chain: Chain name (e.g., TRON)
            tx_hash: Transaction hash
            from_address: Sender address (optional)

        Returns:
            Formatted HTML message
        """
        msg = f"""💰 <b>地址收入</b>

📍 <b>收款地址:</b>
<code>{address}</code>

💵 <b>金额:</b> {amount} {token}
🔗 <b>链:</b> {chain}
"""
        if from_address:
            msg += f"""
📤 <b>来源地址:</b>
<code>{from_address}</code>
"""
        msg += f"""
🔖 <b>交易哈希:</b>
<code>{tx_hash}</code>"""
        return msg

    def format_address_expense_message(
        self,
        address: str,
        amount: Decimal,
        token: str,
        chain: str,
        tx_hash: str,
        to_address: str | None = None,
    ) -> str:
        """Format address expense notification message.

        Args:
            address: Sending address
            amount: Transaction amount
            token: Token symbol
            chain: Chain name
            tx_hash: Transaction hash
            to_address: Recipient address (optional)

        Returns:
            Formatted HTML message
        """
        msg = f"""💸 <b>地址支出</b>

📍 <b>转出地址:</b>
<code>{address}</code>

💵 <b>金额:</b> {amount} {token}
🔗 <b>链:</b> {chain}
"""
        if to_address:
            msg += f"""
📥 <b>目标地址:</b>
<code>{to_address}</code>
"""
        msg += f"""
🔖 <b>交易哈希:</b>
<code>{tx_hash}</code>"""
        return msg

    def format_deposit_failed_message(
        self,
        order_no: str,
        amount: Decimal,
        token: str,
        reason: str,
        merchant_order_no: str | None = None,
    ) -> str:
        """Format deposit failed notification message.

        Args:
            order_no: System order number
            amount: Order amount
            token: Token symbol
            reason: Failure reason
            merchant_order_no: Merchant order number (optional)

        Returns:
            Formatted HTML message
        """
        msg = f"""❌ <b>充值订单失败</b>

📋 <b>订单号:</b> <code>{order_no}</code>
"""
        if merchant_order_no:
            msg += f"""🏷️ <b>商户订单号:</b> <code>{merchant_order_no}</code>
"""
        msg += f"""💵 <b>金额:</b> {amount} {token}

⚠️ <b>失败原因:</b>
{reason}"""
        return msg

    def format_order_query_response(
        self,
        order_no: str,
        status: str,
        amount: Decimal,
        token: str,
        chain: str,
        created_at: str,
        merchant_order_no: str | None = None,
        tx_hash: str | None = None,
    ) -> str:
        """Format order query response message.

        Args:
            order_no: System order number
            status: Order status
            amount: Order amount
            token: Token symbol
            chain: Chain name
            created_at: Order creation time
            merchant_order_no: Merchant order number (optional)
            tx_hash: Transaction hash (optional)

        Returns:
            Formatted HTML message
        """
        status_emoji = {
            "PENDING": "⏳",
            "PROCESSING": "🔄",
            "SUCCESS": "✅",
            "FAILED": "❌",
            "EXPIRED": "⏰",
            "CANCELLED": "🚫",
        }.get(status, "❓")

        msg = f"""📋 <b>订单查询结果</b>

📋 <b>订单号:</b> <code>{order_no}</code>
"""
        if merchant_order_no:
            msg += f"""🏷️ <b>商户订单号:</b> <code>{merchant_order_no}</code>
"""
        msg += f"""{status_emoji} <b>状态:</b> {status}
💵 <b>金额:</b> {amount} {token}
🔗 <b>链:</b> {chain}
🕐 <b>创建时间:</b> {created_at}
"""
        if tx_hash:
            msg += f"""
🔖 <b>交易哈希:</b>
<code>{tx_hash}</code>"""
        return msg


# ============ Notification Helper Functions ============


async def should_send_notification(
    notification_type: str,
    telegram_bot_enabled: bool,
    telegram_notifications: list[str],
    telegram_chat_id: str | None,
) -> bool:
    """Check if notification should be sent.

    Args:
        notification_type: Type of notification
        telegram_bot_enabled: Whether bot is enabled
        telegram_notifications: List of enabled notification types
        telegram_chat_id: Chat ID to send to

    Returns:
        True if notification should be sent
    """
    if not telegram_bot_enabled:
        return False
    if not telegram_chat_id:
        return False
    if notification_type not in telegram_notifications:
        return False
    return True


async def send_address_income_notification(
    chat_id: str,
    address: str,
    amount: Decimal,
    token: str,
    chain: str,
    tx_hash: str,
    from_address: str | None = None,
) -> bool:
    """Send address income notification.

    Args:
        chat_id: Telegram chat ID
        address: Receiving address
        amount: Transaction amount
        token: Token symbol
        chain: Chain name
        tx_hash: Transaction hash
        from_address: Sender address (optional)

    Returns:
        True if sent successfully
    """
    service = TelegramService()
    message = service.format_address_income_message(
        address=address,
        amount=amount,
        token=token,
        chain=chain,
        tx_hash=tx_hash,
        from_address=from_address,
    )
    result = await service.send_message(chat_id, message)
    return result is not None


async def send_address_expense_notification(
    chat_id: str,
    address: str,
    amount: Decimal,
    token: str,
    chain: str,
    tx_hash: str,
    to_address: str | None = None,
) -> bool:
    """Send address expense notification.

    Args:
        chat_id: Telegram chat ID
        address: Sending address
        amount: Transaction amount
        token: Token symbol
        chain: Chain name
        tx_hash: Transaction hash
        to_address: Recipient address (optional)

    Returns:
        True if sent successfully
    """
    service = TelegramService()
    message = service.format_address_expense_message(
        address=address,
        amount=amount,
        token=token,
        chain=chain,
        tx_hash=tx_hash,
        to_address=to_address,
    )
    result = await service.send_message(chat_id, message)
    return result is not None


async def send_deposit_failed_notification(
    chat_id: str,
    order_no: str,
    amount: Decimal,
    token: str,
    reason: str,
    merchant_order_no: str | None = None,
) -> bool:
    """Send deposit failed notification.

    Args:
        chat_id: Telegram chat ID
        order_no: System order number
        amount: Order amount
        token: Token symbol
        reason: Failure reason
        merchant_order_no: Merchant order number (optional)

    Returns:
        True if sent successfully
    """
    service = TelegramService()
    message = service.format_deposit_failed_message(
        order_no=order_no,
        amount=amount,
        token=token,
        reason=reason,
        merchant_order_no=merchant_order_no,
    )
    result = await service.send_message(chat_id, message)
    return result is not None
