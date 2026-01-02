"""AKX Crypto Payment Gateway - Order service."""

import secrets
import string
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from src.chains import get_chain
from src.core.exceptions import InsufficientBalanceError, ValidationError
from src.models.order import Order, OrderStatus, OrderType
from src.models.transaction import Transaction, TransactionDirection, TransactionType
from src.models.wallet import Chain, Token, Wallet
from src.services.wallet_service import WalletService


class OrderService:
    """Service for order management.

    Handles deposit and withdrawal order creation, status updates,
    and ledger entries.
    """

    # Fee configuration (should be loaded from DB/config in production)
    FEE_PERCENTAGE = Decimal("0.01")  # 1%
    FEE_FIXED = Decimal("1.0")  # 1 USDT fixed fee
    MIN_WITHDRAWAL = Decimal("10.0")  # Minimum withdrawal

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._wallet_service = WalletService(db)

    @staticmethod
    def generate_order_no() -> str:
        """Generate unique order number.

        Format: AKX + timestamp + random (20 chars total)
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        chars = string.ascii_uppercase + string.digits
        random_part = "".join(secrets.choice(chars) for _ in range(6))
        return f"AKX{timestamp}{random_part}"

    def calculate_fee(self, amount: Decimal) -> Decimal:
        """Calculate withdrawal fee.

        Formula: (amount * percentage) + fixed_fee
        """
        return (amount * self.FEE_PERCENTAGE) + self.FEE_FIXED

    async def get_user_balance(self, user_id: int) -> Decimal:
        """Get user's available balance from ledger.

        Calculates balance from transaction history.
        """
        result = await self._db.execute(
            select(
                func.sum(
                    func.case(
                        (Transaction.direction == TransactionDirection.CREDIT, Transaction.amount),
                        else_=-Transaction.amount,
                    )
                )
            ).where(Transaction.user_id == user_id)
        )
        balance = result.scalar()
        return balance if balance else Decimal("0")

    async def create_withdrawal(
        self,
        user_id: int,
        chain: Chain,
        to_address: str,
        amount: Decimal,
        merchant_ref: str | None = None,
        token: Token = Token.USDT,
    ) -> Order:
        """Create a withdrawal order.

        Payment method is uniquely identified by: chain + token

        Args:
            user_id: Merchant user ID
            chain: Target blockchain
            to_address: Destination address
            amount: Withdrawal amount
            merchant_ref: Optional merchant reference
            token: Token/currency (default: USDT)

        Returns:
            Created order

        Raises:
            ValidationError: If validation fails
            InsufficientBalanceError: If balance too low
        """
        # Validate amount
        if amount < self.MIN_WITHDRAWAL:
            raise ValidationError(
                f"Minimum withdrawal is {self.MIN_WITHDRAWAL}",
                {"min_amount": str(self.MIN_WITHDRAWAL)},
            )

        # Validate address
        chain_impl = get_chain(chain)
        if not chain_impl.validate_address(to_address):
            raise ValidationError(
                f"Invalid {chain.value} address",
                {"address": to_address},
            )

        # Calculate fee and net amount
        fee = self.calculate_fee(amount)
        net_amount = amount - fee

        # Check balance (balance is per chain+token in production)
        balance = await self.get_user_balance(user_id)
        if balance < amount:
            raise InsufficientBalanceError(
                "Insufficient balance",
                {"available": str(balance), "required": str(amount)},
            )

        # Create order
        order = Order(
            order_no=self.generate_order_no(),
            merchant_ref=merchant_ref,
            user_id=user_id,
            order_type=OrderType.WITHDRAWAL,
            chain=chain.value,
            token=token.value,
            amount=amount,
            fee=fee,
            net_amount=net_amount,
            status=OrderStatus.PENDING,
            wallet_address=to_address,
        )

        self._db.add(order)
        await self._db.commit()
        await self._db.refresh(order)

        # Create ledger entry (freeze funds)
        await self._create_ledger_entry(
            user_id=user_id,
            order_id=order.id,
            tx_type=TransactionType.WITHDRAWAL,
            direction=TransactionDirection.DEBIT,
            amount=amount,
            description=f"Withdrawal {order.order_no}",
        )

        return order

    async def process_deposit(
        self,
        wallet_address: str,
        chain: Chain,
        amount: Decimal,
        tx_hash: str,
        confirmations: int,
    ) -> Order | None:
        """Process incoming deposit.

        Called by block scanner when deposit detected.

        Args:
            wallet_address: Receiving wallet address
            chain: Blockchain network
            amount: Deposit amount
            tx_hash: Transaction hash
            confirmations: Current confirmations

        Returns:
            Created/updated order, None if wallet not found
        """
        # Find wallet
        wallet = await self._wallet_service.get_wallet_by_address(wallet_address, chain)
        if not wallet or not wallet.user_id:
            return None

        # Check if order already exists for this tx
        result = await self._db.execute(select(Order).where(Order.tx_hash == tx_hash))
        existing = result.scalar_one_or_none()

        if existing:
            # Update confirmations
            existing.confirmations = confirmations
            chain_impl = get_chain(chain)
            if chain_impl.is_confirmed(confirmations) and existing.status != OrderStatus.SUCCESS:
                existing.status = OrderStatus.SUCCESS
                existing.completed_at = datetime.utcnow()

                # Credit user balance
                await self._create_ledger_entry(
                    user_id=wallet.user_id,
                    wallet_id=wallet.id,
                    order_id=existing.id,
                    tx_type=TransactionType.DEPOSIT,
                    direction=TransactionDirection.CREDIT,
                    amount=amount,
                    description=f"Deposit {existing.order_no}",
                )

            await self._db.commit()
            return existing

        # Create new deposit order
        chain_impl = get_chain(chain)
        is_confirmed = chain_impl.is_confirmed(confirmations)

        order = Order(
            order_no=self.generate_order_no(),
            user_id=wallet.user_id,
            order_type=OrderType.DEPOSIT,
            chain=chain.value,
            amount=amount,
            fee=Decimal("0"),
            net_amount=amount,
            status=OrderStatus.SUCCESS if is_confirmed else OrderStatus.CONFIRMING,
            wallet_address=wallet_address,
            tx_hash=tx_hash,
            confirmations=confirmations,
            completed_at=datetime.utcnow() if is_confirmed else None,
        )

        self._db.add(order)
        await self._db.commit()
        await self._db.refresh(order)

        if is_confirmed:
            await self._create_ledger_entry(
                user_id=wallet.user_id,
                wallet_id=wallet.id,
                order_id=order.id,
                tx_type=TransactionType.DEPOSIT,
                direction=TransactionDirection.CREDIT,
                amount=amount,
                description=f"Deposit {order.order_no}",
            )

        return order

    async def execute_withdrawal(self, order_id: int) -> Order:
        """Execute a pending withdrawal on-chain.

        Args:
            order_id: Order ID to execute

        Returns:
            Updated order

        Raises:
            ChainError: If transaction broadcast fails
        """
        from src.core.security import decrypt_private_key

        result = await self._db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()

        if not order or order.status != OrderStatus.PENDING:
            raise ValidationError("Order not found or not pending")

        chain = Chain(order.chain)

        # Get system hot wallet for this chain
        hot_wallet = await self._get_hot_wallet(chain)
        if not hot_wallet:
            raise ValidationError(f"No hot wallet configured for {chain.value}")

        # Check hot wallet balance
        chain_impl = get_chain(chain)
        balance = await chain_impl.get_balance(hot_wallet.address)

        if balance.usdt_balance < order.net_amount:
            raise InsufficientBalanceError(
                "Hot wallet has insufficient USDT balance",
                {"available": str(balance.usdt_balance), "required": str(order.net_amount)},
            )

        # Update order status to processing
        order.status = OrderStatus.PROCESSING
        order.updated_at = datetime.utcnow()
        await self._db.commit()

        # Decrypt hot wallet private key
        private_key = decrypt_private_key(hot_wallet.encrypted_private_key)

        try:
            # Broadcast transaction
            tx_result = await chain_impl.transfer_usdt(
                from_address=hot_wallet.address,
                to_address=order.wallet_address,
                amount=order.net_amount,
                private_key=private_key,
            )

            if tx_result.success:
                order.tx_hash = tx_result.tx_hash
                order.status = OrderStatus.PROCESSING  # Will become SUCCESS after confirmations
                order.chain_metadata = {
                    "hot_wallet": hot_wallet.address,
                    "block_number": tx_result.block_number,
                }
            else:
                order.status = OrderStatus.FAILED
                order.chain_metadata = {"error": tx_result.error_message}

                # Refund the frozen balance
                await self._create_ledger_entry(
                    user_id=order.user_id,
                    order_id=order.id,
                    tx_type=TransactionType.ADJUSTMENT,
                    direction=TransactionDirection.CREDIT,
                    amount=order.amount,
                    description=f"Refund failed withdrawal {order.order_no}",
                )

        finally:
            # Clear private key from memory
            del private_key

        order.updated_at = datetime.utcnow()
        await self._db.commit()
        await self._db.refresh(order)

        return order

    async def _get_hot_wallet(self, chain: Chain) -> "Wallet | None":
        """Get the hot wallet for a chain.

        Hot wallet is a COLD type wallet owned by system (user_id = None).
        In production, you might have multiple hot wallets for load balancing.
        """
        from src.models.wallet import Wallet, WalletType

        result = await self._db.execute(
            select(Wallet).where(
                Wallet.chain == chain,
                Wallet.wallet_type == WalletType.COLD,
                Wallet.user_id == None,  # noqa: E711
                Wallet.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_frozen_balance(self, user_id: int) -> Decimal:
        """Get user's frozen balance from pending withdrawals.

        Frozen balance = sum of pending/processing withdrawal amounts.
        """
        result = await self._db.execute(
            select(func.sum(Order.amount)).where(
                Order.user_id == user_id,
                Order.order_type == OrderType.WITHDRAWAL,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING]),
            )
        )
        frozen = result.scalar()
        return frozen if frozen else Decimal("0")

    async def get_available_balance(self, user_id: int) -> Decimal:
        """Get user's available balance (total - frozen)."""
        total = await self.get_user_balance(user_id)
        frozen = await self.get_frozen_balance(user_id)
        return total - frozen

    async def confirm_withdrawal(self, order_id: int) -> Order | None:
        """Mark a processing withdrawal as confirmed/success.

        Called by block scanner when tx reaches required confirmations.
        """
        result = await self._db.execute(
            select(Order).where(
                Order.id == order_id,
                Order.status == OrderStatus.PROCESSING,
            )
        )
        order = result.scalar_one_or_none()

        if not order:
            return None

        order.status = OrderStatus.SUCCESS
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()

        await self._db.commit()
        await self._db.refresh(order)

        return order

    async def _create_ledger_entry(
        self,
        user_id: int,
        tx_type: TransactionType,
        direction: TransactionDirection,
        amount: Decimal,
        description: str,
        wallet_id: int | None = None,
        order_id: int | None = None,
    ) -> Transaction:
        """Create a ledger entry for balance tracking.

        All balance changes must go through this method.
        """
        # Get current balance
        pre_balance = await self.get_user_balance(user_id)

        # Calculate post balance
        if direction == TransactionDirection.CREDIT:
            post_balance = pre_balance + amount
        else:
            post_balance = pre_balance - amount

        tx = Transaction(
            user_id=user_id,
            wallet_id=wallet_id,
            order_id=order_id,
            tx_type=tx_type,
            direction=direction,
            amount=amount,
            pre_balance=pre_balance,
            post_balance=post_balance,
            description=description,
        )

        self._db.add(tx)
        await self._db.commit()
        return tx

    async def get_order(self, order_id: int, user_id: int | None = None) -> Order | None:
        """Get order by ID.

        Args:
            order_id: Order ID
            user_id: Optional user filter (for security)

        Returns:
            Order if found
        """
        query = select(Order).where(Order.id == order_id)
        if user_id:
            query = query.where(Order.user_id == user_id)

        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def get_order_by_no(self, order_no: str, user_id: int | None = None) -> Order | None:
        """Get order by order number."""
        query = select(Order).where(Order.order_no == order_no)
        if user_id:
            query = query.where(Order.user_id == user_id)

        result = await self._db.execute(query)
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        user_id: int,
        order_type: OrderType | None = None,
        status: OrderStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Order], int]:
        """List orders with pagination.

        Returns:
            Tuple of (orders, total_count)
        """
        query = select(Order).where(Order.user_id == user_id)

        if order_type:
            query = query.where(Order.order_type == order_type)
        if status:
            query = query.where(Order.status == status)

        # Count total
        count_result = await self._db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar() or 0

        # Paginate
        query = query.order_by(Order.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self._db.execute(query)
        orders = list(result.scalars().all())

        return orders, total

    async def expire_order_by_no(self, order_no: str) -> bool:
        """Expire a specific order by order number.

        Called by delayed Celery task when order reaches expiry time.
        Only expires if order is still in PENDING status.

        Args:
            order_no: Order number to expire

        Returns:
            True if order was expired, False otherwise
        """
        now = datetime.utcnow()

        result = await self._db.execute(
            select(Order).where(
                Order.order_no == order_no,
                Order.order_type == OrderType.DEPOSIT,
                Order.status == OrderStatus.PENDING,
            )
        )
        order = result.scalar_one_or_none()

        if not order:
            # Order not found or already processed
            return False

        # Verify expiry time has passed
        expire_time_str = order.chain_metadata.get("expire_time")
        if expire_time_str:
            expire_time = datetime.fromisoformat(expire_time_str)
            if now < expire_time:
                # Not yet expired, shouldn't happen but be safe
                return False

        # Expire the order
        order.status = OrderStatus.EXPIRED
        order.updated_at = now
        order.completed_at = now
        order.chain_metadata = {
            **order.chain_metadata,
            "expired_at": now.isoformat(),
            "expired_reason": "timeout",
        }

        await self._db.commit()
        return True
