"""Initialize default fee configurations.

Run this script to create default fee configurations in the database.

Usage:
    uv run python -m src.scripts.init_fee_configs
"""

import asyncio
from decimal import Decimal

from sqlmodel import select

from src.db.engine import async_session_factory, close_db
from src.models.fee_config import FeeConfig


async def init_fee_configs() -> None:
    """Create default fee configurations."""
    async with async_session_factory() as session:
        # Check if any fee configs exist
        result = await session.execute(select(FeeConfig))
        existing_configs = result.scalars().all()

        if existing_configs:
            print(f"Found {len(existing_configs)} existing fee configurations:")
            for config in existing_configs:
                print(f"  - {config.name} (Default: {config.is_default})")
            print("\nSkipping initialization. Delete existing configs first if you want to reset.")
            return

        # Create default fee configurations
        configs = [
            FeeConfig(
                name="Standard",
                deposit_fee_percent=Decimal("1.0"),  # 1%
                withdraw_fee_fixed=Decimal("1.0"),  # 1 USDT
                withdraw_fee_percent=Decimal("0.5"),  # 0.5%
                is_default=True,
            ),
            FeeConfig(
                name="VIP",
                deposit_fee_percent=Decimal("0.5"),  # 0.5%
                withdraw_fee_fixed=Decimal("0.5"),  # 0.5 USDT
                withdraw_fee_percent=Decimal("0.3"),  # 0.3%
                is_default=False,
            ),
            FeeConfig(
                name="Premium",
                deposit_fee_percent=Decimal("0.3"),  # 0.3%
                withdraw_fee_fixed=Decimal("0.3"),  # 0.3 USDT
                withdraw_fee_percent=Decimal("0.2"),  # 0.2%
                is_default=False,
            ),
        ]

        for config in configs:
            session.add(config)

        await session.commit()

        print("✅ Successfully created default fee configurations:")
        for config in configs:
            print(f"  - {config.name}:")
            print(f"    Deposit Fee: {config.deposit_fee_percent}%")
            print(
                f"    Withdraw Fee: {config.withdraw_fee_fixed} USDT "
                f"+ {config.withdraw_fee_percent}%"
            )
            print(f"    Default: {config.is_default}")


async def main() -> None:
    """Main function with proper cleanup."""
    try:
        await init_fee_configs()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
