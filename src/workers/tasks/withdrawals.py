"""AKX Crypto Payment Gateway - Withdrawal processing tasks.

Tasks for processing pending withdrawal orders.
"""

import logging

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.workers.tasks.withdrawals.process_pending_withdrawals")
def process_pending_withdrawals():
    """Process pending withdrawal orders."""
    import asyncio

    from sqlmodel import select

    from src.db import async_session_factory
    from src.models.order import Order, OrderStatus, OrderType
    from src.services.order_service import OrderService

    async def _process():
        processed = 0
        failed = 0

        async with async_session_factory() as db:
            result = await db.execute(
                select(Order)
                .where(
                    Order.order_type == OrderType.WITHDRAWAL,
                    Order.status == OrderStatus.PENDING,
                )
                .limit(10)
            )
            orders = result.scalars().all()

            service = OrderService(db)

            for order in orders:
                try:
                    await service.execute_withdrawal(order.id)
                    processed += 1
                except Exception as e:
                    failed += 1
                    logger.error(f"Withdrawal failed {order.order_no}: {e}")

        return {"processed": processed, "failed": failed}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_process())
        logger.info(f"Processed withdrawals: {result}")
        return result
    finally:
        loop.close()
