"""AKX Crypto Payment Gateway - Base chain scanner.

Abstract base class for chain-specific scanners.
Each chain implements its own scanning logic.

Payment method is uniquely identified by: chain + token
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from src.models.order import Order, OrderStatus
from src.models.wallet import Chain, Token

logger = logging.getLogger(__name__)


class DepositMatch:
    """Represents a matched deposit transaction."""

    def __init__(
        self,
        order: Order,
        tx_hash: str,
        amount: Decimal,
        token: Token,
        confirmations: int,
        block_number: int,
        from_address: str | None = None,
        raw_data: dict[str, Any] | None = None,
    ):
        self.order = order
        self.tx_hash = tx_hash
        self.amount = amount
        self.token = token
        self.confirmations = confirmations
        self.block_number = block_number
        self.from_address = from_address
        self.raw_data = raw_data or {}


class BaseChainScanner(ABC):
    """Abstract base class for blockchain scanners.

    Each chain (TRON, Ethereum, Solana) implements its own scanner
    that extends this base class.

    Payment method is uniquely identified by: chain + token

    Workflow:
    1. Get pending deposit orders for this chain
    2. Scan blockchain for matching transactions (by address AND token)
    3. When matched: update order status, trigger callback
    """

    # Chain identifier
    chain: Chain

    # Required confirmations for finality
    required_confirmations: int = 1

    # Token contracts for this chain (token -> contract address)
    token_contracts: dict[Token, str] = {}

    def __init__(self):
        """Initialize the scanner."""
        self._last_scanned_block: int | None = None

    @abstractmethod
    async def get_current_block_number(self) -> int:
        """Get the current block number on this chain.

        Returns:
            Current block height
        """
        pass

    @abstractmethod
    async def scan_block_for_deposits(
        self,
        block_number: int,
        pending_orders: list[Order],
    ) -> list[DepositMatch]:
        """Scan a block for deposit transactions matching pending orders.

        Should match by: wallet_address AND token (from order.token)

        Args:
            block_number: Block to scan
            pending_orders: List of pending deposit orders

        Returns:
            List of matched deposits
        """
        pass

    @abstractmethod
    async def get_transaction_confirmations(self, tx_hash: str) -> int:
        """Get current confirmation count for a transaction.

        Args:
            tx_hash: Transaction hash

        Returns:
            Number of confirmations
        """
        pass

    async def scan_blocks(self) -> dict[str, Any]:
        """Scan recent blocks for deposits.

        This is the main entry point called by Celery tasks.

        Returns:
            Dict with scan statistics
        """
        from sqlmodel import select

        from src.db import async_session_factory

        stats = {
            "chain": self.chain.value,
            "blocks_scanned": 0,
            "deposits_found": 0,
            "orders_updated": 0,
            "errors": [],
        }

        try:
            current_block = await self.get_current_block_number()

            # Initialize last scanned block
            if self._last_scanned_block is None:
                # Start from recent blocks
                self._last_scanned_block = current_block - 10

            # Don't scan too many blocks at once
            start_block = self._last_scanned_block + 1
            end_block = min(current_block, start_block + 100)

            if start_block > end_block:
                return stats

            async with async_session_factory() as db:
                # Get pending deposit orders for this chain
                result = await db.execute(
                    select(Order).where(
                        Order.chain == self.chain.value,
                        Order.status == OrderStatus.PENDING,
                    )
                )
                pending_orders = list(result.scalars().all())

                if not pending_orders:
                    self._last_scanned_block = end_block
                    stats["blocks_scanned"] = end_block - start_block + 1
                    return stats

                # Scan each block
                for block_num in range(start_block, end_block + 1):
                    try:
                        matches = await self.scan_block_for_deposits(block_num, pending_orders)
                        stats["blocks_scanned"] += 1

                        for match in matches:
                            await self._process_deposit_match(db, match)
                            stats["deposits_found"] += 1
                            # Remove matched order from pending list
                            pending_orders = [o for o in pending_orders if o.id != match.order.id]

                    except Exception as e:
                        logger.error(f"Error scanning block {block_num}: {e}")
                        stats["errors"].append(str(e))

                self._last_scanned_block = end_block

        except Exception as e:
            logger.error(f"Chain scan error ({self.chain.value}): {e}", exc_info=True)
            stats["errors"].append(str(e))

        return stats

    async def update_confirmations(self) -> dict[str, Any]:
        """Update confirmation counts for confirming orders.

        Returns:
            Dict with update statistics
        """
        from sqlmodel import select

        from src.db import async_session_factory

        stats = {
            "chain": self.chain.value,
            "orders_checked": 0,
            "orders_confirmed": 0,
            "errors": [],
        }

        async with async_session_factory() as db:
            # Get confirming orders for this chain
            result = await db.execute(
                select(Order).where(
                    Order.chain == self.chain.value,
                    Order.status == OrderStatus.CONFIRMING,
                )
            )
            orders = list(result.scalars().all())

            for order in orders:
                if not order.tx_hash:
                    continue

                stats["orders_checked"] += 1

                try:
                    confirmations = await self.get_transaction_confirmations(order.tx_hash)
                    order.confirmations = confirmations

                    if confirmations >= self.required_confirmations:
                        # Order is confirmed - trigger callback
                        await self._confirm_order(db, order)
                        stats["orders_confirmed"] += 1

                    await db.commit()

                except Exception as e:
                    logger.error(f"Error updating order {order.order_no}: {e}")
                    stats["errors"].append(str(e))

        return stats

    async def _process_deposit_match(self, db, match: DepositMatch) -> None:
        """Process a matched deposit.

        Updates order status and records transaction details.
        """
        from datetime import datetime

        order = match.order

        # Verify amount matches
        if match.amount < order.amount:
            logger.warning(
                f"Order {order.order_no}: received {match.amount}, expected {order.amount}"
            )
            return

        # Update order
        order.tx_hash = match.tx_hash
        order.confirmations = match.confirmations
        order.chain_metadata = {
            **order.chain_metadata,
            "block_number": match.block_number,
            "from_address": match.from_address,
            "detected_at": datetime.utcnow().isoformat(),
        }

        if match.confirmations >= self.required_confirmations:
            order.status = OrderStatus.SUCCESS
            order.completed_at = datetime.utcnow()
        else:
            order.status = OrderStatus.CONFIRMING

        order.updated_at = datetime.utcnow()
        db.add(order)
        await db.commit()

        logger.info(
            f"Deposit matched: Order {order.order_no}, "
            f"tx={match.tx_hash}, amount={match.amount}, "
            f"confirmations={match.confirmations}"
        )

        # Trigger webhook callback if confirmed
        if order.status == OrderStatus.SUCCESS:
            await self._trigger_callback(db, order)

    async def _confirm_order(self, db, order: Order) -> None:
        """Confirm an order and trigger callback."""
        from datetime import datetime

        from src.services.order_service import OrderService

        order.status = OrderStatus.SUCCESS
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        await db.commit()

        logger.info(f"Order confirmed: {order.order_no}")

        # Credit user balance
        order_service = OrderService(db)
        await order_service.credit_balance(
            user_id=order.user_id,
            amount=order.net_amount,
            order=order,
        )

        # Trigger callback
        await self._trigger_callback(db, order)

    async def _trigger_callback(self, db, order: Order) -> None:
        """Trigger webhook callback for completed order."""
        from src.models.webhook import WebhookEventType
        from src.services.webhook_service import WebhookService

        try:
            webhook_service = WebhookService(db)
            await webhook_service.trigger_webhook(
                user_id=order.user_id,
                event_type=WebhookEventType.ORDER_COMPLETED,
                payload={
                    "order_no": order.order_no,
                    "merchant_ref": order.merchant_ref,
                    "order_type": order.order_type.value,
                    "chain": order.chain,
                    "amount": str(order.amount),
                    "fee": str(order.fee),
                    "net_amount": str(order.net_amount),
                    "status": order.status.value,
                    "tx_hash": order.tx_hash,
                    "wallet_address": order.wallet_address,
                    "completed_at": order.completed_at.isoformat() if order.completed_at else None,
                },
            )
        except Exception as e:
            logger.error(f"Failed to trigger callback for order {order.order_no}: {e}")
