"""Order lifecycle tasks for AKX Payment Gateway.

This module contains Celery tasks for order lifecycle management:
- Order expiration
"""

import asyncio
import logging

from src.db.engine import close_db, get_session
from src.models.order import Order, OrderStatus
from src.services.payment_service import PaymentService
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async coroutine in sync context for Celery."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="order.expire_order")
def expire_order(order_id: int) -> dict:
    """Expire a deposit order after timeout.

    This task is scheduled when an order is created with a delay
    equal to the order's expiration time.

    Args:
        order_id: Order ID to expire

    Returns:
        Dict with expiration result
    """
    return run_async(_expire_order_async(order_id))


async def _expire_order_async(order_id: int) -> dict:
    """Async implementation of expire_order."""
    from src.tasks.callback import send_callback

    try:
        async with get_session() as db:
            service = PaymentService(db)

            order = await db.get(Order, order_id)
            if not order:
                logger.warning(f"Order {order_id} not found for expiration")
                return {"success": False, "message": "Order not found"}

            # Only expire if still pending
            if order.status != OrderStatus.PENDING:
                logger.info(f"Order {order.order_no} not expired - status is {order.status}")
                return {
                    "success": True,
                    "message": f"Order already in {order.status} status",
                }

            # Mark as expired
            await service.update_order_status(order, OrderStatus.EXPIRED)
            logger.info(f"Order {order.order_no} marked as expired")

            # Send callback for expired order
            send_callback.delay(order.id)

            return {"success": True, "order_no": order.order_no}

    except Exception as e:
        logger.exception(f"Expire order error for {order_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await close_db()
