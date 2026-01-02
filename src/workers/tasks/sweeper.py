"""AKX Crypto Payment Gateway - Fund sweeping tasks.

Tasks for sweeping funds from deposit wallets to cold storage.
"""

import logging

from src.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.workers.tasks.sweeper.sweep_funds")
def sweep_funds():
    """Sweep funds from deposit wallets to cold storage."""
    import asyncio

    from src.services.sweeper_service import SweeperService

    sweeper = SweeperService()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(sweeper.sweep_once())
        logger.info(f"Sweep complete: {result}")
        return result
    finally:
        loop.close()
