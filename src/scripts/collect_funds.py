"""Fund Collection Script - Execute fund collection from deposit addresses to hot wallet.

This script scans deposit addresses with sufficient balance and collects funds
to the hot wallet.

Usage:
    # Scan and create collection tasks
    uv run python -m src.scripts.collect_funds --action scan --hot-wallet-id 1

    # Execute pending tasks (dry run)
    uv run python -m src.scripts.collect_funds --action execute --dry-run

    # Execute pending tasks (real)
    uv run python -m src.scripts.collect_funds --action execute

    # View statistics
    uv run python -m src.scripts.collect_funds --action stats

Options:
    --action: scan, execute, retry, stats
    --hot-wallet-id: Hot wallet ID for collection destination
    --max-tasks: Maximum tasks to execute (default: 10)
    --dry-run: Preview without executing transfers
    --chain: Chain code (default: tron)
    --token: Token code (default: USDT)
"""

import argparse
import asyncio

from src.db.engine import close_db, get_session
from src.services.collect_service import CollectService


async def scan_action(
    hot_wallet_id: int,
    chain_code: str,
    token_code: str,
) -> None:
    """Scan deposit addresses and create collection tasks."""
    print("\nScanning for addresses to collect...")
    print(f"Hot Wallet ID: {hot_wallet_id}")
    print(f"Chain: {chain_code}, Token: {token_code}\n")

    async with get_session() as db:
        service = CollectService(db)
        tasks = await service.scan_and_create_tasks(
            hot_wallet_id=hot_wallet_id,
            chain_code=chain_code,
            token_code=token_code,
        )

        if tasks:
            print(f"✅ Created {len(tasks)} collection tasks")
            for task in tasks:
                print(f"  - Task #{task.id}: {task.amount} USDT")
        else:
            print("ℹ️  No addresses need collection at this time")


async def execute_action(
    max_tasks: int,
    dry_run: bool,
    chain_code: str,
) -> None:
    """Execute pending collection tasks."""
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\nExecuting collection tasks ({mode})...")
    print(f"Max tasks: {max_tasks}")
    print(f"Chain: {chain_code}\n")

    async with get_session() as db:
        service = CollectService(db)
        result = await service.execute_pending_tasks(
            chain_code=chain_code,
            max_tasks=max_tasks,
            dry_run=dry_run,
        )

        print("\n" + "=" * 50)
        print("Execution Summary")
        print("=" * 50)
        print(f"Total tasks: {result.get('total', 0)}")
        print(f"Success: {result.get('success', 0)}")
        print(f"Failed: {result.get('failed', 0)}")
        print(f"Skipped: {result.get('skipped', 0)}")

        if result.get("details"):
            print("\nDetails:")
            for detail in result["details"]:
                status_icon = "✅" if detail["status"] == "success" else "❌"
                print(f"  {status_icon} Task #{detail['task_id']}: {detail['status']}")
                if detail.get("tx_hash"):
                    print(f"      TX: {detail['tx_hash']}")
                if detail.get("error"):
                    print(f"      Error: {detail['error']}")


async def retry_action(chain_code: str, max_retries: int) -> None:
    """Retry failed collection tasks."""
    print("\nRetrying failed tasks...")
    print(f"Chain: {chain_code}")
    print(f"Max retries: {max_retries}\n")

    async with get_session() as db:
        service = CollectService(db)
        result = await service.retry_failed_tasks(
            chain_code=chain_code,
            max_retries=max_retries,
        )

        print(f"✅ {result.get('message', 'Done')}")


async def stats_action(chain_code: str) -> None:
    """Show collection statistics."""
    print(f"\nCollection Statistics for {chain_code.upper()}")
    print("=" * 50)

    async with get_session() as db:
        service = CollectService(db)
        stats = await service.get_collection_stats(chain_code=chain_code)

        print(f"Total tasks: {stats.get('total_tasks', 0)}")
        print(f"Total collected: {stats.get('total_collected', '0')} USDT")
        print("\nBy status:")
        for status, data in stats.get("by_status", {}).items():
            print(f"  {status}: {data['count']} tasks, {data['amount']} USDT")


async def main(args: argparse.Namespace) -> None:
    """Main entry point."""
    try:
        if args.action == "scan":
            if not args.hot_wallet_id:
                print("Error: --hot-wallet-id is required for scan action")
                return
            await scan_action(
                hot_wallet_id=args.hot_wallet_id,
                chain_code=args.chain,
                token_code=args.token,
            )
        elif args.action == "execute":
            await execute_action(
                max_tasks=args.max_tasks,
                dry_run=args.dry_run,
                chain_code=args.chain,
            )
        elif args.action == "retry":
            await retry_action(
                chain_code=args.chain,
                max_retries=args.max_retries,
            )
        elif args.action == "stats":
            await stats_action(chain_code=args.chain)
        else:
            print(f"Unknown action: {args.action}")
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fund collection script")
    parser.add_argument(
        "--action",
        type=str,
        choices=["scan", "execute", "retry", "stats"],
        required=True,
        help="Action to perform",
    )
    parser.add_argument(
        "--hot-wallet-id",
        type=int,
        help="Hot wallet ID for collection destination",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=10,
        help="Maximum tasks to execute",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retry count for failed tasks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without executing transfers",
    )
    parser.add_argument(
        "--chain",
        type=str,
        default="tron",
        help="Chain code",
    )
    parser.add_argument(
        "--token",
        type=str,
        default="USDT",
        help="Token code",
    )

    args = parser.parse_args()
    asyncio.run(main(args))
