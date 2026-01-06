"""Recharge Monitor Script - Watch for incoming merchant recharges and process them.

This script monitors assigned recharge addresses for incoming USDT transfers
and processes them when detected (merchant balance top-up).

Usage:
    uv run python -m src.scripts.recharge_monitor

The script runs continuously, polling the blockchain for new transactions.
"""

import asyncio
import logging
from decimal import Decimal

from sqlmodel import select

from src.db.engine import close_db, get_session
from src.models.recharge import RechargeAddress, RechargeAddressStatus
from src.services.recharge_service import RechargeService
from src.services.tron_service import TronService, get_tron_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
POLL_INTERVAL = 15  # seconds between polls
BATCH_SIZE = 50  # addresses per batch


async def process_recharge(
    recharge_service: RechargeService,
    address: str,
    tx_hash: str,
    amount: Decimal,
    confirmations: int,
) -> None:
    """Process a detected recharge transaction."""
    logger.info(
        f"Processing recharge: address={address}, tx={tx_hash}, "
        f"amount={amount}, confirmations={confirmations}"
    )

    result = await recharge_service.process_detected_recharge(
        address=address,
        tx_hash=tx_hash,
        amount=amount,
        confirmations=confirmations,
    )

    if result:
        logger.info(f"Recharge processed: {result}")
    else:
        logger.warning(f"No pending order for recharge to {address}")


async def monitor_loop(tron: TronService) -> None:
    """Main monitoring loop."""
    logger.info("Starting recharge monitor...")

    # Track last check timestamp per address
    last_check: dict[str, int] = {}

    while True:
        try:
            async with get_session() as db:
                recharge_service = RechargeService(db)

                # Get all assigned recharge addresses
                query = (
                    select(RechargeAddress)
                    .where(RechargeAddress.status == RechargeAddressStatus.ASSIGNED)
                    .limit(BATCH_SIZE)
                )

                result = await db.execute(query)
                addresses = result.scalars().all()

                if not addresses:
                    logger.debug("No assigned recharge addresses to monitor")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                logger.info(f"Monitoring {len(addresses)} recharge addresses...")

                for recharge_addr in addresses:
                    if not recharge_addr.wallet:
                        continue

                    address = recharge_addr.wallet.address
                    min_timestamp = last_check.get(address)

                    try:
                        # Get recent transactions
                        transactions = await tron.get_trc20_transactions(
                            address=address,
                            only_confirmed=False,  # Get pending too
                            only_to=True,
                            min_timestamp=min_timestamp,
                            limit=20,
                        )

                        for tx in transactions:
                            tx_hash = tx["tx_hash"]
                            amount = tx["amount"]

                            # Get confirmation count
                            confirmations = await tron.get_transaction_confirmations(tx_hash)

                            # Process the recharge
                            await process_recharge(
                                recharge_service=recharge_service,
                                address=address,
                                tx_hash=tx_hash,
                                amount=amount,
                                confirmations=confirmations,
                            )

                        # Update last check timestamp
                        import time

                        last_check[address] = int(time.time() * 1000)

                    except Exception as e:
                        logger.error(f"Error monitoring {address}: {e}")

        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")

        await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    """Main entry point."""
    tron = get_tron_service()

    print("\n" + "=" * 60)
    print("AKX Recharge Monitor (Merchant Balance Top-up)")
    print("=" * 60)
    print(f"Network: {tron.network}")
    print(f"Poll Interval: {POLL_INTERVAL}s")
    print(f"Batch Size: {BATCH_SIZE}")
    print("=" * 60 + "\n")

    try:
        await monitor_loop(tron)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await tron.close()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
