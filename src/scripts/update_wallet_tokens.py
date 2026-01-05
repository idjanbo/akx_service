"""
Script to update existing wallets with default token_id (USDT).

Run with: uv run python -m src.scripts.update_wallet_tokens
"""

import asyncio
import logging

from sqlalchemy import select, update

from src.db.engine import close_db, get_session
from src.models.token import Token
from src.models.wallet import Wallet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def update_wallet_tokens():
    """Update all wallets without token_id to use USDT token."""
    try:
        async with get_session() as db:
            # Find USDT token
            result = await db.execute(select(Token).where(Token.code == "usdt"))
            usdt_token = result.scalar_one_or_none()

            if not usdt_token:
                logger.error("USDT token not found in database")
                return

            logger.info(f"Found USDT token with id: {usdt_token.id}")

            # Count wallets without token_id
            result = await db.execute(
                select(Wallet).where(Wallet.token_id == None)  # noqa: E711
            )
            wallets_to_update = result.scalars().all()
            count = len(wallets_to_update)

            if count == 0:
                logger.info("No wallets need updating")
                return

            logger.info(f"Found {count} wallets without token_id")

            # Update all wallets without token_id
            await db.execute(
                update(Wallet)
                .where(Wallet.token_id == None)  # noqa: E711
                .values(token_id=usdt_token.id)
            )

            await db.commit()
            logger.info(f"Successfully updated {count} wallets with token_id={usdt_token.id}")
    finally:
        # 必须：关闭数据库连接池，避免事件循环关闭时的警告
        await close_db()


if __name__ == "__main__":
    asyncio.run(update_wallet_tokens())
