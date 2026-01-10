"""Amount utilities for unique payment amounts."""

from decimal import ROUND_DOWN, Decimal

from src.core.redis import get_redis

# Amount suffix range: 1-9 (add 0.001 ~ 0.009 to the original amount)
SUFFIX_MIN = 1
SUFFIX_MAX = 9
SUFFIX_COUNT = 9  # 1-9


def _get_base_amount_3dp(payment_amount: Decimal) -> Decimal:
    """Get base amount truncated to 3 decimal places.

    Example: 100.1234 -> 100.123, 99.9999 -> 99.999
    """
    return payment_amount.quantize(Decimal("0.001"), rounding=ROUND_DOWN)


def _build_redis_key(wallet_address: str, base_amount_3dp: Decimal) -> str:
    """Build Redis key for tracking used suffixes.

    Key format: unique_amount:{address}:{base_amount_3dp}
    Example: unique_amount:TXxx...xxx:100.123
    """
    return f"unique_amount:{wallet_address}:{base_amount_3dp}"


async def generate_unique_amount(
    wallet_address: str,
    payment_amount: Decimal,
    ttl_seconds: int = 900,
) -> Decimal:
    """Generate a unique payment amount using Redis atomic operations.

    Adds 0.001 ~ 0.009 to the original amount (truncated to 3dp).
    Carry-over is acceptable (e.g., 100.999 + 0.001 = 101.000).

    Args:
        wallet_address: The deposit wallet address
        payment_amount: Payment amount (already converted to token)
        ttl_seconds: TTL for Redis key (default 15 minutes, should >= order expiry)

    Returns:
        Unique amount with suffix added (e.g., 100.123 -> 100.125)

    Raises:
        ValueError: If all 9 suffixes (1-9) are occupied

    Example:
        payment_amount = 100.123
        possible results: 100.124, 100.125, ..., 100.132
    """
    r = get_redis()

    # Get base amount (truncated to 3 decimals)
    base_amount_3dp = _get_base_amount_3dp(payment_amount)
    redis_key = _build_redis_key(wallet_address, base_amount_3dp)

    # Try to find an available suffix using Redis SET for atomic operations
    for _ in range(SUFFIX_COUNT + 1):  # +1 for safety
        # Atomic increment counter to get next suffix candidate
        counter_key = f"{redis_key}:counter"
        counter = await r.incr(counter_key)
        await r.expire(counter_key, ttl_seconds)

        # Calculate suffix (1-9)
        suffix = (counter % SUFFIX_COUNT) + 1

        # Try to add suffix to used set (atomic SADD returns 1 if new, 0 if exists)
        used_key = f"{redis_key}:used"
        added = await r.sadd(used_key, suffix)
        await r.expire(used_key, ttl_seconds)

        if added == 1:
            # Successfully reserved this suffix
            final_amount = base_amount_3dp + Decimal(suffix) / Decimal(1000)
            return final_amount

    # All 9 suffixes are occupied
    raise ValueError(
        f"No available amount suffix for address {wallet_address} "
        f"with base amount {base_amount_3dp}. All {SUFFIX_COUNT} suffixes (1-9) are occupied."
    )


async def release_amount_suffix(
    wallet_address: str,
    amount: Decimal,
) -> bool:
    """Release a previously reserved amount suffix.

    Call this when an order is completed, cancelled, or expired
    to free up the suffix for reuse.

    Args:
        wallet_address: The deposit wallet address
        amount: The full amount (e.g., 100.125)

    Returns:
        True if suffix was released, False if not found
    """
    r = get_redis()

    # We need to find the original base amount by subtracting the suffix
    # The suffix is 1-9, so we try each possibility
    amount_3dp = _get_base_amount_3dp(amount)

    # Try suffixes 1-9 to find which base amount this came from
    for suffix in range(SUFFIX_MIN, SUFFIX_MAX + 1):
        potential_base = amount_3dp - Decimal(suffix) / Decimal(1000)
        redis_key = _build_redis_key(wallet_address, potential_base)
        used_key = f"{redis_key}:used"

        # Check if this suffix exists in the set
        is_member = await r.sismember(used_key, suffix)
        if is_member:
            # Found it, remove from set
            removed = await r.srem(used_key, suffix)
            return removed == 1

    return False
