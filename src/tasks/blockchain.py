"""Blockchain tasks.

Celery tasks for:
- Confirming transactions
- Processing withdrawals
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal

from celery import shared_task
from sqlmodel import and_, select

from src.blockchain.factory import get_blockchain_service
from src.db.engine import get_session
from src.models import Order
from src.models.order import OrderStatus, OrderType
from src.tasks.callback import send_callback
from src.tasks.telegram import trigger_deposit_failed_notification

logger = logging.getLogger(__name__)


@shared_task(name="blockchain.confirm_transactions")
def confirm_transactions():
    """Check and update confirmation counts for pending transactions.

    This task runs periodically to update transaction confirmations.
    """
    return asyncio.run(_confirm_transactions())


async def _confirm_transactions():
    """Async implementation of transaction confirmation checking."""

    async with get_session() as db:
        # Get orders with tx_hash that are still confirming
        stmt = select(Order).where(
            and_(
                Order.tx_hash.is_not(None),
                Order.status == OrderStatus.CONFIRMING,
            )
        )
        result = await db.execute(stmt)
        orders = result.scalars().all()

        logger.info(f"Checking confirmations for {len(orders)} transactions")

        for order in orders:
            try:
                await _check_transaction_confirmations(db, order)
            except Exception as e:
                logger.error(f"Error checking confirmations for {order.order_no}: {e}")

        await db.commit()


async def _check_transaction_confirmations(db, order: Order):
    """Check confirmations for a specific transaction.

    Args:
        db: Database session
        order: Order with tx_hash to check
    """
    try:
        service = get_blockchain_service(order.chain_code)
    except ValueError as e:
        logger.error(f"Unsupported chain for order {order.order_no}: {e}")
        return

    # Get transaction info
    tx_info = await service.get_transaction(order.tx_hash)
    if not tx_info:
        logger.warning(f"Transaction not found for order {order.order_no}: {order.tx_hash}")
        return

    # Update confirmation count
    order.confirmations = tx_info.confirmations
    order.updated_at = datetime.now(UTC)

    logger.info(
        f"Order {order.order_no} has "
        f"{tx_info.confirmations}/{service.REQUIRED_CONFIRMATIONS} confirmations"
    )

    # Check if fully confirmed
    if tx_info.confirmations >= service.REQUIRED_CONFIRMATIONS:
        if tx_info.is_success:
            order.status = OrderStatus.SUCCESS
            order.confirmed_at = datetime.now(UTC)
            logger.info(f"Order {order.order_no} confirmed successfully")

            # Trigger callback
            send_callback.delay(str(order.id))
        else:
            order.status = OrderStatus.FAILED
            order.error_message = "Transaction failed on blockchain"
            logger.warning(f"Order {order.order_no} transaction failed")

            # Trigger callback for failure
            send_callback.delay(str(order.id))

            # Send Telegram notification for deposit failed
            if order.order_type == OrderType.DEPOSIT:
                trigger_deposit_failed_notification(
                    merchant_id=order.merchant_id,
                    order_no=order.order_no,
                    amount=order.amount,
                    token=order.token,
                    reason="区块链交易失败",
                    merchant_order_no=order.out_trade_no,
                )

            # Trigger callback for failure
            send_callback.delay(str(order.id))


@shared_task(name="blockchain.process_withdraw")
def process_withdraw(order_id: str):
    """Process a withdrawal order by sending the blockchain transaction.

    Args:
        order_id: Order ID to process
    """
    return asyncio.run(_process_withdraw(order_id))


async def _process_withdraw(order_id: str):
    """Async implementation of withdrawal processing.

    Args:
        order_id: Order ID to process
    """

    from src.core.security import aes_decrypt
    from src.models import Wallet

    async with get_session() as db:
        # Get the order
        order = await db.get(Order, order_id)
        if not order:
            logger.error(f"Order not found: {order_id}")
            return

        if order.order_type != OrderType.WITHDRAW:
            logger.error(f"Order {order_id} is not a withdrawal order")
            return

        if order.status != OrderStatus.PENDING:
            logger.warning(f"Order {order_id} is not in PENDING status: {order.status}")
            return

        logger.info(f"Processing withdrawal order {order.order_no}")

        # Update status to processing
        order.status = OrderStatus.PROCESSING
        order.updated_at = datetime.now(UTC)
        await db.commit()

        try:
            # Get blockchain service
            service = get_blockchain_service(order.chain_code)

            # Get the wallet to send from
            # In production, implement wallet selection logic
            stmt = select(Wallet).where(
                and_(
                    Wallet.chain_id == order.chain_id,
                    Wallet.is_active == True,  # noqa: E712
                )
            )
            result = await db.execute(stmt)
            wallet = result.scalars().first()

            if not wallet:
                raise ValueError(f"No available wallet for chain {order.chain_code}")

            # Decrypt private key
            private_key = aes_decrypt(wallet.encrypted_private_key)

            # Get token contract if needed
            token_contract = None
            if order.token_symbol and order.token_symbol.upper() != order.chain_code.upper():
                token_contract = await _get_token_contract(db, order.chain_code, order.token_symbol)

            # Send the transaction
            amount = Decimal(str(order.amount))
            result = await service.transfer(
                from_address=wallet.address,
                to_address=order.to_address,
                amount=amount,
                private_key=private_key,
                token_contract=token_contract,
            )

            if result.success:
                order.tx_hash = result.tx_hash
                order.from_address = wallet.address
                order.status = OrderStatus.CONFIRMING
                order.updated_at = datetime.now(UTC)
                logger.info(f"Withdrawal sent for order {order.order_no}: tx={result.tx_hash}")
            else:
                order.status = OrderStatus.FAILED
                order.error_message = result.error_message or "Transaction failed"
                order.updated_at = datetime.now(UTC)
                logger.error(
                    f"Withdrawal failed for order {order.order_no}: {result.error_message}"
                )

                # Trigger callback for failure
                send_callback.delay(str(order.id))

        except Exception as e:
            logger.error(f"Error processing withdrawal {order.order_no}: {e}")
            order.status = OrderStatus.FAILED
            order.error_message = str(e)
            order.updated_at = datetime.now(UTC)

            # Trigger callback for failure
            send_callback.delay(str(order.id))

        await db.commit()


async def _get_token_contract(db, chain_code: str, token_symbol: str) -> str | None:
    """Get token contract address from database.

    Args:
        db: Database session
        chain_code: Chain code
        token_symbol: Token symbol

    Returns:
        Contract address or None
    """

    from src.models import Chain, Token

    # Get chain
    stmt = select(Chain).where(Chain.code == chain_code.upper())
    result = await db.execute(stmt)
    chain = result.scalars().first()
    if not chain:
        return None

    # Get token
    stmt = select(Token).where(
        and_(
            Token.chain_id == chain.id,
            Token.symbol == token_symbol.upper(),
        )
    )
    result = await db.execute(stmt)
    token = result.scalars().first()

    return token.contract_address if token else None


# Celery beat schedule for blockchain tasks
BLOCKCHAIN_BEAT_SCHEDULE = {
    "confirm-transactions": {
        "task": "blockchain.confirm_transactions",
        "schedule": 30.0,  # Every 30 seconds
    },
}
