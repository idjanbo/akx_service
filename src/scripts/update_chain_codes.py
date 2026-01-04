"""Update chain codes to follow industry standard abbreviations.

Run with: uv run python -m src.scripts.update_chain_codes
"""

import asyncio

from sqlmodel import select

from src.db.engine import async_session_factory, close_db
from src.models.chain import Chain

# Chain code mappings (old_code -> new_code)
CHAIN_CODE_UPDATES = {
    "BNB_CHAIN": "BSC",  # BNB Smart Chain
    "ETHEREUM": "ETH",  # Ethereum
    "SOLANA": "SOL",  # Solana
    # TRON 保持不变，因为 TRON 比 TRX 作为链代码更清晰
    # TON 保持不变
}


async def update_chain_codes():
    """Update chain codes to industry standard abbreviations."""
    async with async_session_factory() as session:
        print("开始更新链代码...\n")

        update_count = 0
        for old_code, new_code in CHAIN_CODE_UPDATES.items():
            # 查找旧代码的链
            result = await session.execute(select(Chain).where(Chain.code == old_code))
            chain = result.scalars().first()

            if chain:
                print(f"更新: {old_code} -> {new_code} ({chain.name})")
                chain.code = new_code
                update_count += 1
            else:
                print(f"⚠️  未找到链: {old_code}")

        await session.commit()

        print(f"\n✓ 链代码已更新: {update_count} 条记录")
        print("\n更新后的链列表:")

        # 显示所有链
        result = await session.execute(select(Chain).order_by(Chain.sort_order))
        chains = result.scalars().all()

        for chain in chains:
            print(f"  {chain.code:<10} -> {chain.name}")


async def main():
    """Main function to run update and cleanup."""
    try:
        await update_chain_codes()
    finally:
        # Ensure database connections are properly closed
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
