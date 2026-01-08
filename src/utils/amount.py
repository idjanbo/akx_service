"""Amount utilities for unique payment amounts."""

import random
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.order import Order, OrderStatus


async def generate_unique_amount(
    db: AsyncSession,
    wallet_address: str,
    requested_amount: Decimal,
) -> Decimal:
    """Generate a unique payment amount by adding a random suffix.

    To avoid collisions when multiple orders share the same address,
    we add a random 3-decimal suffix (0.001 ~ 0.999) to the amount.

    Args:
        db: Database session
        wallet_address: The deposit wallet address
        requested_amount: Original amount requested by merchant

    Returns:
        Unique amount with random suffix (e.g., 100.00 -> 100.123)

    Raises:
        ValueError: If all 999 suffixes are occupied (extremely rare)
    """
    # Get the integer part as base
    base_amount = int(requested_amount)

    # Query existing pending order amounts for this address with same base amount
    query = (
        select(Order.amount)
        .where(Order.wallet_address == wallet_address)
        .where(Order.status == OrderStatus.PENDING)
        .where(Order.expire_time > datetime.now(UTC))
    )
    result = await db.execute(query)
    existing_amounts = result.scalars().all()

    # Extract used suffixes (last 3 decimals) for same base amount
    used_suffixes: set[int] = set()
    for amount in existing_amounts:
        if int(amount) == base_amount:
            # Extract suffix: 100.123 -> 123
            suffix = int((amount % 1) * 1000)
            used_suffixes.add(suffix)

    # Also consider the original amount's suffix if it has decimals
    original_suffix = int((requested_amount % 1) * 1000)

    # Generate available suffixes (001 ~ 999)
    all_suffixes = set(range(1, 1000))
    available_suffixes = list(all_suffixes - used_suffixes)

    if not available_suffixes:
        raise ValueError(
            f"No available amount suffix for address {wallet_address} "
            f"with base amount {base_amount}. All 999 suffixes are occupied."
        )

    # Prefer keeping original suffix if available and non-zero
    if original_suffix > 0 and original_suffix not in used_suffixes:
        chosen_suffix = original_suffix
    else:
        chosen_suffix = random.choice(available_suffixes)

    # Build final amount: base + suffix/1000
    final_amount = Decimal(base_amount) + Decimal(chosen_suffix) / Decimal(1000)

    return final_amount
