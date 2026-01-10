"""Telegram Bot Webhook API for handling bot commands."""

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.db import get_db
from src.models.merchant_setting import MerchantSetting
from src.models.order import Order
from src.services.telegram_service import TelegramService
from src.utils.helpers import format_utc_datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram-webhook"])


class TelegramMessage(BaseModel):
    """Telegram message structure."""

    message_id: int
    from_user: dict | None = None
    chat: dict
    text: str | None = None
    date: int

    class Config:
        populate_by_name = True
        extra = "allow"


class TelegramUpdate(BaseModel):
    """Telegram webhook update structure."""

    update_id: int
    message: TelegramMessage | None = None

    class Config:
        extra = "allow"


async def _get_merchant_by_chat_id(db: AsyncSession, chat_id: str) -> MerchantSetting | None:
    """Get merchant settings by telegram chat ID.

    Args:
        db: Database session
        chat_id: Telegram chat ID

    Returns:
        MerchantSetting if found
    """
    query = select(MerchantSetting).where(
        MerchantSetting.telegram_chat_id == chat_id,
        MerchantSetting.telegram_bot_enabled == True,  # noqa: E712
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _is_user_whitelisted(settings: MerchantSetting, user_id: str) -> bool:
    """Check if user is in the whitelist.

    Args:
        settings: Merchant settings
        user_id: Telegram user ID

    Returns:
        True if whitelisted or whitelist is empty
    """
    if not settings.telegram_whitelist:
        return True
    return user_id in settings.telegram_whitelist


async def _handle_order_command(
    db: AsyncSession,
    settings: MerchantSetting,
    order_no: str,
) -> str:
    """Handle /order command to query order details.

    Args:
        db: Database session
        settings: Merchant settings
        order_no: Order number to query

    Returns:
        Response message
    """
    # Query order
    query = select(Order).where(
        Order.merchant_id == settings.merchant_id,
        (Order.order_no == order_no) | (Order.out_trade_no == order_no),
    )
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        return "❌ 订单不存在或无权查看"

    # Format response
    service = TelegramService()
    return service.format_order_query_response(
        order_no=order.order_no,
        status=order.status.value,
        amount=order.amount,
        token=order.token,
        chain=order.chain,
        created_at=format_utc_datetime(order.created_at),
        merchant_order_no=order.out_trade_no,
        tx_hash=order.tx_hash,
    )


async def _handle_rate_command(db: AsyncSession) -> str:
    """Handle /rate command to query exchange rates.

    Args:
        db: Database session

    Returns:
        Response message with current rates
    """
    from src.services.exchange_rate_service import ExchangeRateService

    service = ExchangeRateService(db)
    sources = await service.list_sources()

    if not sources:
        return "❌ 暂无汇率数据"

    lines = ["📊 <b>当前汇率</b>\n"]

    for source in sources:
        if source.is_enabled and source.current_rate:
            base = source.base_currency
            quote = source.quote_currency
            rate = source.current_rate

            # Add emoji based on currency pair
            if "CNY" in (base, quote):
                emoji = "💵"
            elif "BTC" in (base, quote):
                emoji = "🪙"
            elif "ETH" in (base, quote):
                emoji = "🔷"
            elif "TRX" in (base, quote):
                emoji = "🔺"
            else:
                emoji = "💱"

            lines.append(f"{emoji} {base}/{quote}: {rate:,.8g}")

    from datetime import datetime

    lines.append(f"\n<i>数据更新时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>")

    return "\n".join(lines)


async def _handle_help_command() -> str:
    """Handle /help command.

    Returns:
        Help message
    """
    return """🤖 <b>AKX 支付机器人命令</b>

📋 <code>/order 订单号</code>
   查询订单详情（支持系统订单号或商户订单号）

📊 <code>/rate</code>
   查询当前 C2C 市场汇率

❓ <code>/help</code>
   显示此帮助信息"""


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Handle incoming Telegram webhook updates.

    This endpoint receives updates from Telegram when users send commands.
    """
    try:
        body = await request.json()
        logger.debug(f"Telegram webhook received: {body}")

        # Parse update
        if "message" not in body:
            return {"ok": True}

        message = body.get("message", {})
        text = message.get("text", "")
        chat = message.get("chat", {})
        from_user = message.get("from", {})

        chat_id = str(chat.get("id", ""))
        user_id = str(from_user.get("id", ""))

        if not chat_id or not text:
            return {"ok": True}

        # Get merchant by chat ID
        settings = await _get_merchant_by_chat_id(db, chat_id)
        if not settings:
            logger.debug(f"No merchant found for chat_id: {chat_id}")
            return {"ok": True}

        # Check whitelist
        if not await _is_user_whitelisted(settings, user_id):
            logger.warning(f"User {user_id} not in whitelist for merchant {settings.merchant_id}")
            return {"ok": True}

        # Parse command
        telegram_service = TelegramService()
        response_text = None

        if text.startswith("/order"):
            # Extract order number
            match = re.match(r"/order\s+(\S+)", text)
            if match:
                order_no = match.group(1)
                response_text = await _handle_order_command(db, settings, order_no)
            else:
                response_text = "⚠️ 请输入订单号，例如: <code>/order DEP20240101001</code>"

        elif text.startswith("/rate"):
            response_text = await _handle_rate_command(db)

        elif text.startswith("/help") or text == "/start":
            response_text = await _handle_help_command()

        # Send response
        if response_text:
            await telegram_service.send_message(chat_id, response_text)

        return {"ok": True}

    except Exception as e:
        logger.exception(f"Error processing telegram webhook: {e}")
        return {"ok": True}  # Always return ok to Telegram


@router.post("/set-webhook")
async def set_telegram_webhook() -> dict[str, Any]:
    """Set the Telegram webhook URL.

    Call this endpoint once to register the webhook with Telegram.
    """
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")

    webhook_url = f"{settings.api_base_url}/telegram/webhook"

    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            json={"url": webhook_url},
        )
        result = response.json()

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Failed to set webhook: {result.get('description', 'Unknown error')}",
        )

    return {"success": True, "webhook_url": webhook_url}


@router.delete("/webhook")
async def delete_telegram_webhook() -> dict[str, Any]:
    """Delete the Telegram webhook.

    Call this to stop receiving webhook updates.
    """
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")

    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/deleteWebhook",
        )
        result = response.json()

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Failed to delete webhook: {result.get('description', 'Unknown error')}",
        )

    return {"success": True, "message": "Webhook deleted"}


@router.get("/webhook-info")
async def get_telegram_webhook_info() -> dict[str, Any]:
    """Get current webhook information.

    Returns the current webhook configuration from Telegram.
    """
    settings = get_settings()

    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")

    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo",
        )
        result = response.json()

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Failed to get webhook info: {result.get('description', 'Unknown error')}",
        )

    return result.get("result", {})
