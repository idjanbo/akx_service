"""Exchange rate sync tasks."""

import asyncio
import logging

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import get_settings
from src.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger(__name__)


def _create_task_session() -> tuple:
    """Create a fresh engine and session for task execution.

    This avoids event loop conflicts when running async code in Celery tasks.
    """
    engine = create_async_engine(
        str(get_settings().database_url),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory


@shared_task(name="exchange_rates.sync_all", ignore_result=True)
def sync_all_exchange_rates() -> None:
    """Sync all enabled exchange rate sources.

    This task is scheduled to run periodically to keep rates up to date.
    """
    asyncio.run(_sync_all_rates())


async def _sync_all_rates() -> None:
    """Async implementation of rate sync."""
    engine, session_factory = _create_task_session()
    try:
        async with session_factory() as db:
            service = ExchangeRateService(db)
            await service.sync_all_rates()
    finally:
        await engine.dispose()


@shared_task(name="exchange_rates.sync_source")
def sync_exchange_rate_source(source_id: int) -> dict | None:
    """Sync a specific exchange rate source.

    Args:
        source_id: ID of the rate source to sync

    Returns:
        Updated source info or None if failed
    """
    return asyncio.run(_sync_source(source_id))


async def _sync_source(source_id: int) -> dict | None:
    """Async implementation of single source sync."""
    engine, session_factory = _create_task_session()
    try:
        async with session_factory() as db:
            service = ExchangeRateService(db)
            source = await service.sync_rate_from_source(source_id)

            if source:
                return {
                    "id": source.id,
                    "pair": f"{source.base_currency}/{source.quote_currency}",
                    "rate": str(source.current_rate) if source.current_rate else None,
                    "synced_at": source.last_synced_at.isoformat()
                    if source.last_synced_at
                    else None,
                }
            return None
    finally:
        await engine.dispose()
