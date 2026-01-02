"""AKX Crypto Payment Gateway - Webhook service.

Handles webhook delivery to merchants.
Callback URL is stored per-order in chain_metadata["callback_url"].
"""

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.order import Order
from src.models.webhook import WebhookDelivery, WebhookEventType

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for webhook delivery.

    Features:
    - Deliver webhooks with HMAC signatures
    - Retry failed deliveries
    - Track delivery history

    Note: Callback URL comes from order.chain_metadata["callback_url"],
    not from a separate WebhookConfig table.
    """

    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 10

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def generate_event_id() -> str:
        """Generate unique event ID."""
        return f"evt_{secrets.token_urlsafe(16)}"

    @staticmethod
    def sign_payload(payload: str, secret: str) -> str:
        """Create HMAC-SHA256 signature for payload.

        Args:
            payload: JSON string payload
            secret: Merchant's deposit_key or withdraw_key

        Returns:
            Hex-encoded signature
        """
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def send_order_webhook(
        self,
        order: Order,
        event_type: WebhookEventType,
        secret: str,
    ) -> bool:
        """Send webhook for an order event.

        Args:
            order: Order that triggered the event
            event_type: Type of event
            secret: Merchant's key for signing (deposit_key or withdraw_key)

        Returns:
            True if delivery succeeded
        """
        # Get callback URL from order metadata
        callback_url = order.chain_metadata.get("callback_url")
        if not callback_url:
            logger.warning(f"No callback_url for order {order.order_no}")
            return False

        # Build payload
        event_id = self.generate_event_id()
        payload = {
            "event_type": event_type.value,
            "event_id": event_id,
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "order_no": order.order_no,
                "merchant_ref": order.merchant_ref,
                "order_type": order.order_type.value,
                "chain": order.chain,
                "token": order.token,
                "amount": str(order.amount),
                "fee": str(order.fee),
                "net_amount": str(order.net_amount),
                "status": order.status.value,
                "wallet_address": order.wallet_address,
                "tx_hash": order.tx_hash,
                "confirmations": order.confirmations,
                "created_at": order.created_at.isoformat(),
                "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            },
        }

        return await self._deliver_webhook(
            order_id=order.id,  # type: ignore
            url=callback_url,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            secret=secret,
        )

    async def _deliver_webhook(
        self,
        order_id: int,
        url: str,
        event_type: WebhookEventType,
        event_id: str,
        payload: dict,
        secret: str,
    ) -> bool:
        """Deliver webhook with retries.

        Args:
            order_id: Order ID for tracking
            url: Callback URL
            event_type: Event type
            event_id: Unique event ID
            payload: Webhook payload
            secret: Key for signing

        Returns:
            True if delivery succeeded
        """
        payload_str = json.dumps(payload, default=str)
        signature = self.sign_payload(payload_str, secret)

        # Create delivery record
        delivery = WebhookDelivery(
            order_id=order_id,
            event_type=event_type.value,
            event_id=event_id,
            url=url,
            payload=payload,
            attempts=0,
            success=False,
        )
        self._db.add(delivery)
        await self._db.commit()

        headers = {
            "Content-Type": "application/json",
            "X-AKX-Signature": signature,
            "X-AKX-Event-Type": event_type.value,
            "X-AKX-Event-ID": event_id,
        }

        for attempt in range(self.MAX_RETRIES):
            delivery.attempts = attempt + 1
            delivery.last_attempt_at = datetime.utcnow()

            try:
                async with httpx.AsyncClient(timeout=self.TIMEOUT_SECONDS) as client:
                    response = await client.post(
                        url,
                        content=payload_str,
                        headers=headers,
                    )

                delivery.response_status = response.status_code
                delivery.response_body = response.text[:2000]  # Truncate

                if 200 <= response.status_code < 300:
                    delivery.success = True
                    await self._db.commit()
                    logger.info(f"Webhook delivered: {event_id} to {url}")
                    return True

            except httpx.TimeoutException:
                delivery.response_body = "Timeout"
                logger.warning(f"Webhook timeout: {event_id} attempt {attempt + 1}")

            except Exception as e:
                delivery.response_body = str(e)[:2000]
                logger.error(f"Webhook error: {event_id} - {e}")

            await self._db.commit()

        logger.error(f"Webhook delivery failed after {self.MAX_RETRIES} attempts: {event_id}")
        return False

    async def retry_failed_deliveries(self, merchant_secrets: dict[int, str]) -> int:
        """Retry failed webhook deliveries.

        Called by background worker to retry recent failures.

        Args:
            merchant_secrets: Dict mapping user_id to their signing key

        Returns:
            Number of successful retries
        """
        cutoff = datetime.utcnow() - timedelta(hours=24)

        result = await self._db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.success == False,  # noqa: E712
                WebhookDelivery.attempts < self.MAX_RETRIES,
                WebhookDelivery.created_at > cutoff,
            )
        )
        failed_deliveries = result.scalars().all()

        success_count = 0
        for delivery in failed_deliveries:
            # Get order to find user_id
            order_result = await self._db.execute(
                select(Order).where(Order.id == delivery.order_id)
            )
            order = order_result.scalar_one_or_none()
            if not order:
                continue

            # Get merchant secret
            secret = merchant_secrets.get(order.user_id)
            if not secret:
                continue

            success = await self._deliver_webhook(
                order_id=delivery.order_id,
                url=delivery.url,
                event_type=WebhookEventType(delivery.event_type),
                event_id=delivery.event_id,
                payload=delivery.payload,
                secret=secret,
            )
            if success:
                success_count += 1

        return success_count
