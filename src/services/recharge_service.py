"""Recharge Service - Business logic for merchant online recharge (商户在线充值) operations.

This service handles:
1. Address Management - Generate and assign recharge addresses on demand
2. Recharge Order Creation - Create orders when merchants initiate balance top-up
3. Recharge Detection - Process incoming transactions from blockchain
4. Balance Credit - Credit merchant balance after confirmed recharges

Note: This is different from Orders.deposit which handles merchant's customer deposits.
- Recharge: Merchant tops up their platform balance (商户向平台充值)
- Deposit Order: Merchant's customer pays merchant (商户客户向商户充值)
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.config import get_settings
from src.core.security import get_cipher
from src.models.chain import Chain
from src.models.ledger import (
    BalanceChangeType,
    BalanceLedger,
)
from src.models.recharge import (
    CollectTask,
    CollectTaskStatus,
    RechargeAddress,
    RechargeAddressStatus,
    RechargeOrder,
    RechargeOrderStatus,
    generate_recharge_order_no,
)
from src.models.token import Token
from src.models.user import User
from src.models.wallet import Wallet, WalletType
from src.utils.crypto import generate_wallet_for_chain


class RechargeService:
    """Service for merchant recharge-related business logic."""

    # TRON configuration
    TRON_CHAIN_CODE = "tron"
    USDT_TOKEN_CODE = "USDT"
    TRON_CONFIRMATIONS = 19  # Required confirmations for TRON

    # Collect thresholds
    MIN_COLLECT_AMOUNT = Decimal("10")  # Minimum amount to trigger collection (USDT)
    MAX_GAS_RATIO = Decimal("0.03")  # Max gas fee as percentage of amount

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.cipher = get_cipher()

    # ============ Address Management ============

    async def _generate_recharge_address(
        self,
        user: User,
        chain: Chain,
        token: Token,
    ) -> RechargeAddress:
        """Generate a new recharge address for a merchant.

        Creates both wallet and recharge address records.

        Args:
            user: Merchant user
            chain: Chain to generate address for
            token: Token for the address

        Returns:
            Created RechargeAddress
        """
        # Generate wallet
        address, private_key = generate_wallet_for_chain(chain.code)
        encrypted_key = self.cipher.encrypt(private_key)

        # Create wallet record
        wallet = Wallet(
            user_id=user.id,
            chain_id=chain.id,
            token_id=token.id,
            address=address,
            encrypted_private_key=encrypted_key,
            wallet_type=WalletType.RECHARGE,
            is_active=True,
            label=f"Recharge - {user.email}",
        )
        self.db.add(wallet)
        await self.db.flush()

        # Create recharge address record
        recharge_address = RechargeAddress(
            wallet_id=wallet.id,
            user_id=user.id,
            chain_id=chain.id,
            token_id=token.id,
            status=RechargeAddressStatus.ASSIGNED,
            assigned_at=datetime.utcnow(),
        )
        self.db.add(recharge_address)
        await self.db.commit()
        await self.db.refresh(recharge_address)

        return recharge_address

    async def get_or_create_address(
        self,
        user: User,
        chain_code: str = "tron",
        token_code: str = "USDT",
    ) -> RechargeAddress | None:
        """Get merchant's existing recharge address or create a new one.

        Args:
            user: Merchant user
            chain_code: Blockchain network
            token_code: Token code

        Returns:
            RechargeAddress or None if chain/token not found
        """
        # Get chain and token
        chain_result = await self.db.execute(
            select(Chain).where(func.lower(Chain.code) == chain_code.lower())
        )
        chain = chain_result.scalar_one_or_none()

        token_result = await self.db.execute(
            select(Token).where(func.upper(Token.code) == token_code.upper())
        )
        token = token_result.scalar_one_or_none()

        if not chain or not token:
            return None

        # Check if merchant already has an address for this chain+token
        existing_query = select(RechargeAddress).where(
            RechargeAddress.user_id == user.id,
            RechargeAddress.chain_id == chain.id,
            RechargeAddress.token_id == token.id,
            RechargeAddress.status == RechargeAddressStatus.ASSIGNED,
        )
        existing_result = await self.db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()

        if existing:
            return existing

        # Generate a new address for this merchant
        return await self._generate_recharge_address(user, chain, token)

    async def get_recharge_address_details(
        self,
        user: User,
        chain_code: str = "tron",
        token_code: str = "USDT",
    ) -> dict[str, Any] | None:
        """Get recharge address with full details for API response.

        Args:
            user: Merchant user
            chain_code: Blockchain network
            token_code: Token code

        Returns:
            Dict with address details including chain/token info, or None if unavailable
        """
        # Get or create address
        recharge_address = await self.get_or_create_address(user, chain_code, token_code)
        if not recharge_address:
            return None

        # Eager load relationships
        await self.db.refresh(recharge_address, ["wallet", "chain", "token"])

        chain = recharge_address.chain
        token = recharge_address.token
        wallet = recharge_address.wallet

        if not wallet or not chain or not token:
            return None

        return {
            "address": wallet.address,
            "chain_code": chain.code,
            "chain_name": chain.name,
            "token_code": token.code,
            "token_symbol": token.symbol,
            "qr_content": wallet.address,  # QR code content is just the address
            "min_recharge": None,  # Can be configured per chain if needed
            "confirmations": chain.confirmation_blocks,
            "assigned_at": recharge_address.assigned_at.isoformat()
            if recharge_address.assigned_at
            else None,
        }

    # ============ Recharge Order Management ============

    async def create_recharge_order(
        self,
        user: User,
        amount: Decimal,
        chain_code: str = "tron",
        token_code: str = "USDT",
        expiry_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Create a new recharge order for merchant balance top-up.

        Args:
            user: Merchant user making the recharge
            amount: Expected recharge amount
            chain_code: Blockchain network
            token_code: Token code
            expiry_minutes: Order expiry time (default from settings)

        Returns:
            Recharge order details including address

        Raises:
            ValueError: If no addresses available or invalid params
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        # Get or create recharge address
        recharge_address = await self.get_or_create_address(user, chain_code, token_code)
        if not recharge_address:
            raise ValueError("Failed to create recharge address. Please contact support.")

        # Calculate expiry
        expiry_secs = (
            expiry_minutes * 60 if expiry_minutes else self.settings.deposit_expiry_seconds
        )
        expires_at = datetime.utcnow() + timedelta(seconds=expiry_secs)

        # Create order
        order = RechargeOrder(
            order_no=generate_recharge_order_no(),
            user_id=user.id,
            recharge_address_id=recharge_address.id,
            chain_id=recharge_address.chain_id,
            token_id=recharge_address.token_id,
            expected_amount=amount,
            status=RechargeOrderStatus.PENDING,
            required_confirmations=self.TRON_CONFIRMATIONS,
            expires_at=expires_at,
        )
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)

        # Get chain and token names
        chain = await self.db.get(Chain, recharge_address.chain_id)
        token = await self.db.get(Token, recharge_address.token_id)

        return {
            "order_no": order.order_no,
            "recharge_address": recharge_address.wallet.address if recharge_address.wallet else "",
            "chain": chain.code if chain else chain_code,
            "chain_name": chain.name if chain else "",
            "token": token.code if token else token_code,
            "token_name": token.name if token else "",
            "expected_amount": str(amount),
            "expires_at": expires_at.isoformat(),
            "status": order.status.value,
            "required_confirmations": order.required_confirmations,
        }

    async def get_recharge_order(
        self,
        order_no: str,
        user: User | None = None,
    ) -> dict[str, Any] | None:
        """Get recharge order details.

        Args:
            order_no: Order number
            user: User for access control (None for admin)

        Returns:
            Order details or None
        """
        query = select(RechargeOrder).where(RechargeOrder.order_no == order_no)

        if user:
            query = query.where(RechargeOrder.user_id == user.id)

        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            return None

        return self._order_to_dict(order)

    async def list_recharge_orders(
        self,
        user: User | None = None,
        status: RechargeOrderStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List recharge orders.

        Args:
            user: User for filtering (None for admin - all orders)
            status: Filter by status
            limit: Max results
            offset: Offset for pagination

        Returns:
            List of order dicts
        """
        query = select(RechargeOrder)

        if user:
            query = query.where(RechargeOrder.user_id == user.id)
        if status:
            query = query.where(RechargeOrder.status == status)

        query = query.order_by(RechargeOrder.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        orders = result.scalars().all()

        return [self._order_to_dict(o) for o in orders]

    # ============ Recharge Detection & Processing ============

    async def process_detected_recharge(
        self,
        address: str,
        tx_hash: str,
        amount: Decimal,
        confirmations: int = 0,
    ) -> dict[str, Any] | None:
        """Process a detected recharge from blockchain monitoring.

        Called by blockchain scanner when a recharge is detected.

        Args:
            address: Recharge address that received funds
            tx_hash: Transaction hash
            amount: Actual received amount
            confirmations: Current confirmation count

        Returns:
            Processing result or None if no pending order
        """
        # Find recharge address
        addr_query = select(RechargeAddress).join(Wallet).where(Wallet.address == address)

        addr_result = await self.db.execute(addr_query)
        recharge_address = addr_result.scalar_one_or_none()

        if not recharge_address or not recharge_address.user_id:
            return None  # Not a known recharge address or not assigned

        # Find pending order for this address
        order_query = (
            select(RechargeOrder)
            .where(
                RechargeOrder.recharge_address_id == recharge_address.id,
                RechargeOrder.status.in_(
                    [
                        RechargeOrderStatus.PENDING,
                        RechargeOrderStatus.DETECTED,
                        RechargeOrderStatus.CONFIRMING,
                    ]
                ),
            )
            .order_by(RechargeOrder.created_at.desc())
        )

        order_result = await self.db.execute(order_query)
        order = order_result.scalar_one_or_none()

        if not order:
            # No pending order - auto-create order for this recharge
            order = RechargeOrder(
                order_no=generate_recharge_order_no(),
                user_id=recharge_address.user_id,
                recharge_address_id=recharge_address.id,
                chain_id=recharge_address.chain_id,
                token_id=recharge_address.token_id,
                expected_amount=amount,  # Use actual amount as expected
                actual_amount=amount,
                tx_hash=tx_hash,
                confirmations=confirmations,
                status=RechargeOrderStatus.DETECTED,
                required_confirmations=self.TRON_CONFIRMATIONS,
                detected_at=datetime.utcnow(),
            )
            self.db.add(order)

        # Update order based on confirmations
        order.tx_hash = tx_hash
        order.actual_amount = amount
        order.confirmations = confirmations
        order.updated_at = datetime.utcnow()

        if order.status == RechargeOrderStatus.PENDING:
            order.status = RechargeOrderStatus.DETECTED
            order.detected_at = datetime.utcnow()

        if confirmations >= order.required_confirmations:
            # Fully confirmed - credit merchant balance
            if order.status != RechargeOrderStatus.SUCCESS:
                await self._credit_user_balance(order, recharge_address)
                order.status = RechargeOrderStatus.SUCCESS
                order.confirmed_at = datetime.utcnow()
                order.credited_at = datetime.utcnow()
        else:
            order.status = RechargeOrderStatus.CONFIRMING

        await self.db.commit()

        return {
            "status": order.status.value,
            "order_no": order.order_no,
            "amount": str(amount),
            "confirmations": confirmations,
            "required": order.required_confirmations,
        }

    async def _credit_user_balance(
        self,
        order: RechargeOrder,
        recharge_address: RechargeAddress,
    ) -> None:
        """Credit merchant balance after confirmed recharge.

        Args:
            order: Confirmed recharge order
            recharge_address: The recharge address
        """
        user = await self.db.get(User, order.user_id)
        if not user:
            return

        amount = order.actual_amount or order.expected_amount
        pre_balance = user.balance

        # Update merchant balance
        user.balance = user.balance + amount
        user.updated_at = datetime.utcnow()

        # Create balance ledger entry - ONLINE_RECHARGE for blockchain deposits
        chain_code = recharge_address.chain.code if recharge_address.chain else "TRON"
        token_code = recharge_address.token.code if recharge_address.token else "USDT"
        ledger = BalanceLedger(
            user_id=user.id,
            order_id=order.id,
            change_type=BalanceChangeType.ONLINE_RECHARGE,
            amount=amount,
            pre_balance=pre_balance,
            post_balance=user.balance,
            remark=f"Recharge {order.order_no} via {chain_code}-{token_code}",
        )
        self.db.add(ledger)

        # Update recharge address stats
        recharge_address.total_recharged = recharge_address.total_recharged + amount
        recharge_address.last_recharge_at = datetime.utcnow()
        recharge_address.updated_at = datetime.utcnow()

    async def expire_pending_orders(self) -> int:
        """Expire orders that have passed their expiry time.

        Called periodically by a scheduler.

        Returns:
            Number of orders expired
        """
        now = datetime.utcnow()

        query = select(RechargeOrder).where(
            RechargeOrder.status == RechargeOrderStatus.PENDING,
            RechargeOrder.expires_at < now,
        )

        result = await self.db.execute(query)
        orders = result.scalars().all()

        for order in orders:
            order.status = RechargeOrderStatus.EXPIRED
            order.updated_at = now

        await self.db.commit()
        return len(orders)

    # ============ Fund Collection (归集) ============

    async def check_and_create_collect_tasks(
        self,
        hot_wallet_address: str,
        chain_code: str = "tron",
        token_code: str = "USDT",
    ) -> list[CollectTask]:
        """Check recharge addresses and create collection tasks if needed.

        Called periodically to identify addresses that need collection.

        Args:
            hot_wallet_address: Destination hot wallet address
            chain_code: Blockchain network
            token_code: Token code

        Returns:
            List of created collect tasks
        """
        # Get hot wallet
        hot_wallet_query = select(Wallet).where(Wallet.address == hot_wallet_address)
        hot_wallet_result = await self.db.execute(hot_wallet_query)
        hot_wallet = hot_wallet_result.scalar_one_or_none()

        if not hot_wallet:
            raise ValueError(f"Hot wallet not found: {hot_wallet_address}")

        # Get chain and token
        chain_result = await self.db.execute(
            select(Chain).where(func.lower(Chain.code) == chain_code.lower())
        )
        chain = chain_result.scalar_one_or_none()

        token_result = await self.db.execute(
            select(Token).where(func.upper(Token.code) == token_code.upper())
        )
        token = token_result.scalar_one_or_none()

        if not chain or not token:
            return []

        # Find addresses with balance above threshold
        addresses_query = select(RechargeAddress).where(
            RechargeAddress.chain_id == chain.id,
            RechargeAddress.token_id == token.id,
            RechargeAddress.status == RechargeAddressStatus.ASSIGNED,
            RechargeAddress.total_recharged >= self.MIN_COLLECT_AMOUNT,
        )

        # Exclude addresses with pending collect tasks
        subquery = select(CollectTask.recharge_address_id).where(
            CollectTask.status.in_([CollectTaskStatus.PENDING, CollectTaskStatus.PROCESSING])
        )
        addresses_query = addresses_query.where(RechargeAddress.id.notin_(subquery))

        result = await self.db.execute(addresses_query)
        addresses = result.scalars().all()

        created_tasks: list[CollectTask] = []

        for addr in addresses:
            # TODO: Get actual balance from blockchain
            # For now, use total_recharged (should be replaced)
            balance = addr.total_recharged

            if balance < self.MIN_COLLECT_AMOUNT:
                continue

            task = CollectTask(
                recharge_address_id=addr.id,
                hot_wallet_id=hot_wallet.id,
                chain_id=chain.id,
                token_id=token.id,
                amount=balance,
                status=CollectTaskStatus.PENDING,
            )
            self.db.add(task)
            created_tasks.append(task)

        await self.db.commit()
        return created_tasks

    async def get_pending_collect_tasks(
        self,
        chain_code: str = "tron",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get pending collection tasks for execution.

        Args:
            chain_code: Filter by chain
            limit: Max tasks to return

        Returns:
            List of task details
        """
        chain_result = await self.db.execute(
            select(Chain).where(func.lower(Chain.code) == chain_code.lower())
        )
        chain = chain_result.scalar_one_or_none()

        if not chain:
            return []

        query = (
            select(CollectTask)
            .where(
                CollectTask.chain_id == chain.id,
                CollectTask.status == CollectTaskStatus.PENDING,
            )
            .order_by(CollectTask.created_at)
            .limit(limit)
        )

        result = await self.db.execute(query)
        tasks = result.scalars().all()

        return [
            {
                "id": t.id,
                "from_address": t.recharge_address.wallet.address
                if t.recharge_address and t.recharge_address.wallet
                else "",
                "to_address": t.hot_wallet.address if t.hot_wallet else "",
                "amount": str(t.amount),
                "chain": chain_code,
                "status": t.status.value,
            }
            for t in tasks
        ]

    async def update_collect_task_status(
        self,
        task_id: int,
        status: CollectTaskStatus,
        tx_hash: str | None = None,
        gas_used: Decimal | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update collection task status after execution.

        Args:
            task_id: Task ID
            status: New status
            tx_hash: Transaction hash if executed
            gas_used: Gas used if executed
            error_message: Error message if failed

        Returns:
            True if updated successfully
        """
        task = await self.db.get(CollectTask, task_id)
        if not task:
            return False

        task.status = status
        if tx_hash:
            task.tx_hash = tx_hash
        if gas_used:
            task.gas_used = gas_used
        if error_message:
            task.error_message = error_message

        if status == CollectTaskStatus.PROCESSING:
            task.executed_at = datetime.utcnow()
        elif status in [
            CollectTaskStatus.SUCCESS,
            CollectTaskStatus.FAILED,
            CollectTaskStatus.SKIPPED,
        ]:
            task.completed_at = datetime.utcnow()

        await self.db.commit()
        return True

    # ============ Helper Methods ============

    def _order_to_dict(self, order: RechargeOrder) -> dict[str, Any]:
        """Convert order to dict."""
        address = ""
        if order.recharge_address and order.recharge_address.wallet:
            address = order.recharge_address.wallet.address

        return {
            "id": order.id,
            "order_no": order.order_no,
            "user_id": order.user_id,
            "recharge_address": address,
            "chain": order.chain.code if order.chain else "",
            "chain_name": order.chain.name if order.chain else "",
            "token": order.token.code if order.token else "",
            "token_name": order.token.name if order.token else "",
            "expected_amount": str(order.expected_amount),
            "actual_amount": str(order.actual_amount) if order.actual_amount else None,
            "status": order.status.value,
            "tx_hash": order.tx_hash,
            "confirmations": order.confirmations,
            "required_confirmations": order.required_confirmations,
            "expires_at": order.expires_at.isoformat() if order.expires_at else None,
            "detected_at": order.detected_at.isoformat() if order.detected_at else None,
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
            "credited_at": order.credited_at.isoformat() if order.credited_at else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        }
