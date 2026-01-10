"""Callback tasks for merchant notifications."""

import asyncio
import logging

import httpx
from celery.exceptions import Retry

from src.db.engine import close_db, get_session
from src.models.order import CallbackStatus, Order
from src.services.merchant_setting_service import MerchantSettingService
from src.services.payment_service import PaymentService
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

CALLBACK_TIMEOUT = 30
# Default retry intervals: 1m, 5m, 15m, 1h, 6h, 12h, 24h, 48h, 72h, 168h (7d)
CALLBACK_RETRY_INTERVALS = [60, 300, 900, 3600, 21600, 43200, 86400, 172800, 259200, 604800]


@celery_app.task(
    bind=True,
    max_retries=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=604800,
)
def send_callback(self, order_id: int) -> dict:
    """Send callback notification to merchant."""
    return asyncio.run(_send_callback(self, order_id))


async def _send_callback(task, order_id: int) -> dict:
    try:
        async with get_session() as db:
            service = PaymentService(db)
            merchant_setting_service = MerchantSettingService(db)

            # Get order
            order = await db.get(Order, order_id)
            if not order:
                logger.error(f"Order {order_id} not found for callback")
                return {"success": False, "message": "Order not found"}

            # Skip if callback already successful
            if order.callback_status == CallbackStatus.SUCCESS:
                logger.info(f"Callback already successful for order {order_id}")
                return {"success": True, "message": "Already sent"}

            # Get merchant-specific callback retry count
            max_retries = await merchant_setting_service.get_callback_retry_count(
                order.merchant_id, default=3
            )

            # Build callback payload
            try:
                payload = await service.build_callback_payload(order)
            except Exception as e:
                logger.error(f"Failed to build callback payload for order {order_id}: {e}")
                return {"success": False, "message": str(e)}

            # Send HTTP request
            try:
                async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT) as client:
                    response = await client.post(
                        order.callback_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )

                    # Check response - HTTP 200 and body contains "ok" or "success"
                    response_text = response.text.strip().lower()
                    is_success = response.status_code == 200 and (
                        "ok" in response_text or "success" in response_text
                    )

                    if is_success:
                        await service.mark_callback_success(order)
                        logger.info(f"Callback successful for order {order_id}")
                        return {"success": True, "message": "Callback sent"}
                    else:
                        logger.warning(
                            f"Callback failed for order {order_id}: "
                            f"HTTP {response.status_code} - {response.text}"
                        )
                        await service.mark_callback_failed(order)

                        # Retry with exponential backoff (respecting merchant settings)
                        retry_count = order.callback_retry_count
                        if retry_count < max_retries and retry_count < len(
                            CALLBACK_RETRY_INTERVALS
                        ):
                            delay = CALLBACK_RETRY_INTERVALS[retry_count]
                            task.retry(countdown=delay)

                        return {
                            "success": False,
                            "message": f"HTTP {response.status_code}",
                        }

            except httpx.TimeoutException:
                logger.warning(f"Callback timeout for order {order_id}")
                await service.mark_callback_failed(order)
                raise  # Will trigger retry

            except httpx.RequestError as e:
                logger.warning(f"Callback request error for order {order_id}: {e}")
                await service.mark_callback_failed(order)
                raise  # Will trigger retry

    except Retry:
        # Retry 异常是正常的重试信号，直接抛出让 Celery 处理
        raise
    except Exception as e:
        logger.exception(f"Callback task error for order {order_id}: {e}")
        raise
    finally:
        await close_db()
