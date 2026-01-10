"""Redis connection management for AKX Payment Gateway."""

import redis.asyncio as redis

from src.core.config import get_settings

# Redis connection pool (initialized in lifespan)
_redis_pool: redis.Redis | None = None


async def init_redis() -> None:
    """Initialize Redis connection pool.

    Call this during application startup (lifespan).
    """
    global _redis_pool
    settings = get_settings()
    _redis_pool = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


async def close_redis() -> None:
    """Close Redis connection pool.

    Call this during application shutdown (lifespan).
    """
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


def get_redis() -> redis.Redis:
    """Get Redis connection.

    Returns:
        Redis client instance

    Raises:
        RuntimeError: If Redis is not initialized
    """
    if _redis_pool is None:
        raise RuntimeError("Redis not initialized. Call init_redis() during application startup.")
    return _redis_pool
