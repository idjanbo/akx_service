"""AKX Crypto Payment Gateway - Order expiry tasks.

Tasks for expiring pending deposit orders:
- expire_single_order: Delayed task for individual order expiry
- schedule_order_expiry: Helper to schedule delayed expiry
"""

import logging

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.workers.tasks.order_expiry.expire_single_order")
def expire_single_order(order_no: str):
    """Expire a single order by order number.

    This task is scheduled with a delay when an order is created.
    It's more efficient than polling the database.

    Args:
        order_no: The order number to expire
    """
    import asyncio

    from src.db import async_session_factory
    from src.services.order_service import OrderService

    async def _expire():
        async with async_session_factory() as db:
            service = OrderService(db)
            return await service.expire_order_by_no(order_no)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_expire())
        if result:
            logger.info(f"Order {order_no} expired via delayed task")
        return {"order_no": order_no, "expired": result}
    finally:
        loop.close()


def schedule_order_expiry(order_no: str, expire_seconds: int):
    """Schedule an order to expire after a delay.

    Called when creating a new deposit order.

    Args:
        order_no: The order number
        expire_seconds: Seconds until expiry
    """
    # Add a small buffer (10 seconds) to ensure the order is truly expired
    delay = expire_seconds + 10
    expire_single_order.apply_async(
        args=[order_no],
        countdown=delay,
    )
    logger.debug(f"Scheduled expiry for order {order_no} in {delay} seconds")
