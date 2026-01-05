"""Callback tasks for merchant notifications."""

import asyncio
import logging

import httpx

from src.db.engine import close_db, get_session
from src.models.order import CallbackStatus, Order
from src.services.payment_service import PaymentService
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

CALLBACK_TIMEOUT = 30
CALLBACK_RETRY_INTERVALS = [60, 300, 900, 3600, 21600]  # 1m, 5m, 15m, 1h, 6h


@celery_app.task(
    bind=True,
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=21600,
)
def send_callback(self, order_id: int) -> dict:
    """Send callback notification to merchant."""
    return asyncio.run(_send_callback(self, order_id))


async def _send_callback(task, order_id: int) -> dict:
    try:
        async with get_session() as db:
            service = PaymentService(db)

            # Get order
            order = await db.get(Order, order_id)
            if not order:
                logger.error(f"Order {order_id} not found for callback")
                return {"success": False, "message": "Order not found"}

            # Skip if callback already successful
            if order.callback_status == CallbackStatus.SUCCESS:
                logger.info(f"Callback already successful for order {order_id}")
                return {"success": True, "message": "Already sent"}

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

                    # Check response - HTTP 200 means success
                    if response.status_code == 200:
                        await service.mark_callback_success(order)
                        logger.info(f"Callback successful for order {order_id}")
                        return {"success": True, "message": "Callback sent"}
                    else:
                        logger.warning(
                            f"Callback failed for order {order_id}: "
                            f"HTTP {response.status_code} - {response.text}"
                        )
                        await service.mark_callback_failed(order)

                        # Retry with exponential backoff
                        retry_count = order.callback_retry_count
                        if retry_count < len(CALLBACK_RETRY_INTERVALS):
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

    except Exception as e:
        logger.exception(f"Callback task error for order {order_id}: {e}")
        raise
    finally:
        await close_db()
