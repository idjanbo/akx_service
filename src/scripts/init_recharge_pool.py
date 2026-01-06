"""Initialize recharge address pool.

This script generates a batch of TRON recharge addresses for the address pool.
Run this after database migration to prepare addresses for merchant recharges.

Usage:
    uv run python -m src.scripts.init_recharge_pool --count 20

Options:
    --count: Number of addresses to generate (default: 20)
    --chain: Chain code (default: tron)
    --token: Token code (default: USDT)
"""

import argparse
import asyncio

from src.db.engine import close_db, get_session
from src.services.recharge_service import RechargeService


async def main(count: int, chain_code: str, token_code: str) -> None:
    """Generate recharge addresses for the pool."""
    print(f"\n{'=' * 60}")
    print("Initializing Recharge Address Pool")
    print(f"{'=' * 60}")
    print(f"Chain: {chain_code}")
    print(f"Token: {token_code}")
    print(f"Count: {count}")
    print(f"{'=' * 60}\n")

    try:
        async with get_session() as db:
            service = RechargeService(db)

            # Check current pool stats
            stats = await service.get_pool_stats(chain_code=chain_code, token_code=token_code)
            print("Current pool status:")
            print(f"  Total: {stats['total']}")
            print(f"  Available: {stats['available']}")
            print(f"  Assigned: {stats['assigned']}")
            print()

            if stats["available"] >= count:
                print(f"Pool already has {stats['available']} available addresses.")
                print("No new addresses generated.")
                return

            # Generate addresses
            to_generate = count - stats["available"]
            print(f"Generating {to_generate} new addresses...")

            addresses = await service.generate_address_pool(
                count=to_generate,
                chain_code=chain_code,
                token_code=token_code,
            )

            print(f"\n✅ Successfully generated {len(addresses)} addresses!")

            # Show updated stats
            stats = await service.get_pool_stats(chain_code=chain_code, token_code=token_code)
            print("\nUpdated pool status:")
            print(f"  Total: {stats['total']}")
            print(f"  Available: {stats['available']}")
            print(f"  Assigned: {stats['assigned']}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize recharge address pool")
    parser.add_argument("--count", type=int, default=20, help="Number of addresses to generate")
    parser.add_argument("--chain", type=str, default="tron", help="Chain code")
    parser.add_argument("--token", type=str, default="USDT", help="Token code")

    args = parser.parse_args()

    asyncio.run(main(args.count, args.chain, args.token))
