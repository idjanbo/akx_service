"""AKX Crypto Payment Gateway - Webhook retry tasks.

Tasks for retrying failed webhook deliveries.
"""

import logging

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.workers.tasks.webhooks.retry_webhooks")
def retry_webhooks():
    """Retry failed webhook deliveries.

    Loads merchant secrets (deposit_key) for signing retried webhooks.
    """
    import asyncio

    from sqlmodel import select

    from src.db import async_session_factory
    from src.models.merchant import Merchant
    from src.services.webhook_service import WebhookService

    async def _retry():
        async with async_session_factory() as db:
            # Load all active merchant secrets
            result = await db.execute(
                select(Merchant).where(Merchant.is_active == True)  # noqa: E712
            )
            merchants = result.scalars().all()

            # Map user_id -> deposit_key for signing
            merchant_secrets = {m.user_id: m.deposit_key for m in merchants}

            service = WebhookService(db)
            return await service.retry_failed_deliveries(merchant_secrets)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        count = loop.run_until_complete(_retry())
        if count > 0:
            logger.info(f"Retried {count} webhooks successfully")
        return {"retried": count}
    finally:
        loop.close()
