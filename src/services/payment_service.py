"""Payment Service - Business logic for payment operations."""

import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.chain import Chain
from src.models.fee_config import FeeConfig
from src.models.order import (
    CallbackStatus,
    Order,
    OrderStatus,
    OrderType,
    generate_order_no,
)
from src.models.token import Token, TokenChainSupport
from src.models.user import User, UserRole
from src.models.wallet import Wallet, WalletType
from src.schemas.payment import PaymentErrorCode
from src.utils.helpers import format_utc_datetime

if TYPE_CHECKING:
    from src.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    """Custom payment error with error code."""

    def __init__(self, code: PaymentErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class PaymentService:
    """Service for payment-related business logic."""

    def __init__(self, db: AsyncSession, ledger_service: "LedgerService | None" = None):
        self.db = db
        self._ledger_service = ledger_service
        # Load settings for configurable values
        from src.core.config import get_settings

        settings = get_settings()
        self.deposit_expiry_seconds = settings.deposit_expiry_seconds
        self.timestamp_validity_ms = settings.timestamp_validity_minutes * 60 * 1000

    @property
    def ledger_service(self) -> "LedgerService":
        """Get LedgerService instance (lazy initialization)."""
        if self._ledger_service is None:
            from src.services.ledger_service import LedgerService

            self._ledger_service = LedgerService(self.db)
        return self._ledger_service

    # ============ Signature Verification ============

    def generate_signature(self, message: str, secret_key: str) -> str:
        """Generate HMAC-SHA256 signature.

        Args:
            message: Message to sign
            secret_key: Secret key (deposit_key or withdraw_key)

        Returns:
            Lowercase hex signature
        """
        return hmac.new(
            secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(self, message: str, signature: str, secret_key: str) -> bool:
        """Verify HMAC-SHA256 signature.

        Args:
            message: Original message
            signature: Signature to verify
            secret_key: Secret key

        Returns:
            True if signature is valid
        """
        expected = self.generate_signature(message, secret_key)
        return hmac.compare_digest(expected.lower(), signature.lower())

    def verify_timestamp(self, timestamp: int) -> bool:
        """Verify request timestamp is within valid window.

        Args:
            timestamp: Request timestamp in milliseconds

        Returns:
            True if timestamp is valid
        """
        current_time = int(time.time() * 1000)
        return abs(current_time - timestamp) <= self.timestamp_validity_ms

    # ============ Merchant Authentication ============

    async def get_merchant_by_no(self, merchant_no: str) -> User | None:
        """Get merchant by merchant number (deposit_key prefix).

        In this system, merchant_no is the unique identifier.
        For simplicity, we use user.id with prefix 'M'.

        Args:
            merchant_no: Merchant number (e.g., 'M1234')

        Returns:
            User or None
        """
        # Extract ID from merchant_no (e.g., 'M123' -> 123)
        if not merchant_no.startswith("M"):
            return None
        try:
            user_id = int(merchant_no[1:])
        except ValueError:
            return None

        user = await self.db.get(User, user_id)
        if user and user.role == UserRole.MERCHANT and user.is_active:
            return user
        return None

    async def authenticate_deposit_request(
        self,
        merchant_no: str,
        timestamp: int,
        nonce: str,
        signature: str,
        signature_message: str,
    ) -> User:
        """Authenticate a deposit API request.

        Args:
            merchant_no: Merchant number
            timestamp: Request timestamp (ms)
            nonce: Random nonce
            signature: Request signature
            signature_message: Message that was signed

        Returns:
            Authenticated merchant user

        Raises:
            PaymentError: On authentication failure
        """
        # Verify timestamp
        if not self.verify_timestamp(timestamp):
            raise PaymentError(
                PaymentErrorCode.TIMESTAMP_EXPIRED,
                "Request timestamp expired",
            )

        # Get merchant
        merchant = await self.get_merchant_by_no(merchant_no)
        if not merchant or not merchant.deposit_key:
            raise PaymentError(
                PaymentErrorCode.INVALID_MERCHANT,
                "Invalid merchant",
            )

        # Verify signature
        if not self.verify_signature(signature_message, signature, merchant.deposit_key):
            raise PaymentError(
                PaymentErrorCode.INVALID_SIGNATURE,
                "Invalid signature",
            )

        return merchant

    async def authenticate_withdraw_request(
        self,
        merchant_no: str,
        timestamp: int,
        nonce: str,
        signature: str,
        signature_message: str,
    ) -> User:
        """Authenticate a withdraw API request.

        Args:
            merchant_no: Merchant number
            timestamp: Request timestamp (ms)
            nonce: Random nonce
            signature: Request signature
            signature_message: Message that was signed

        Returns:
            Authenticated merchant user

        Raises:
            PaymentError: On authentication failure
        """
        # Verify timestamp
        if not self.verify_timestamp(timestamp):
            raise PaymentError(
                PaymentErrorCode.TIMESTAMP_EXPIRED,
                "Request timestamp expired",
            )

        # Get merchant
        merchant = await self.get_merchant_by_no(merchant_no)
        if not merchant or not merchant.withdraw_key:
            raise PaymentError(
                PaymentErrorCode.INVALID_MERCHANT,
                "Invalid merchant",
            )

        # Verify signature
        if not self.verify_signature(signature_message, signature, merchant.withdraw_key):
            raise PaymentError(
                PaymentErrorCode.INVALID_SIGNATURE,
                "Invalid signature",
            )

        return merchant

    # ============ Token/Chain Validation ============

    async def validate_token_chain(
        self, token_code: str, chain_code: str
    ) -> tuple[Token, Chain, TokenChainSupport]:
        """Validate token and chain combination.

        Args:
            token_code: Token code (uppercase, e.g., 'USDT')
            chain_code: Chain code (lowercase, e.g., 'tron')

        Returns:
            Tuple of (Token, Chain, TokenChainSupport)

        Raises:
            PaymentError: If token/chain is invalid or not supported
        """
        # Get token
        result = await self.db.execute(
            select(Token).where(
                Token.code == token_code.upper(),
                Token.is_enabled == True,  # noqa: E712
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            raise PaymentError(
                PaymentErrorCode.INVALID_TOKEN_CHAIN,
                f"Token '{token_code}' is not supported or disabled",
            )

        # Get chain
        result = await self.db.execute(
            select(Chain).where(
                Chain.code == chain_code.upper(),
                Chain.is_enabled == True,  # noqa: E712
            )
        )
        chain = result.scalar_one_or_none()
        if not chain:
            raise PaymentError(
                PaymentErrorCode.INVALID_TOKEN_CHAIN,
                f"Chain '{chain_code}' is not supported or disabled",
            )

        # Check token-chain support
        result = await self.db.execute(
            select(TokenChainSupport).where(
                TokenChainSupport.token_id == token.id,
                TokenChainSupport.chain_id == chain.id,
                TokenChainSupport.is_enabled == True,  # noqa: E712
            )
        )
        support = result.scalar_one_or_none()
        if not support:
            raise PaymentError(
                PaymentErrorCode.INVALID_TOKEN_CHAIN,
                f"Token '{token_code}' is not supported on chain '{chain_code}'",
            )

        return token, chain, support

    async def get_token_chain_support(
        self, token_id: int, chain_id: int
    ) -> TokenChainSupport | None:
        """Get token-chain support configuration.

        Args:
            token_id: Token ID
            chain_id: Chain ID

        Returns:
            TokenChainSupport or None
        """
        result = await self.db.execute(
            select(TokenChainSupport).where(
                TokenChainSupport.token_id == token_id,
                TokenChainSupport.chain_id == chain_id,
            )
        )
        return result.scalar_one_or_none()

    # ============ Order Operations ============

    async def create_deposit_order(
        self,
        merchant: User,
        out_trade_no: str,
        token: Token,
        chain: Chain,
        support: TokenChainSupport,
        amount: Decimal,
        callback_url: str,
        extra_data: str | None = None,
        requested_currency: str = "USDT",
    ) -> Order:
        """Create a new deposit order.

        Args:
            merchant: Merchant user
            out_trade_no: External trade number
            token: Token
            chain: Chain
            support: Token-chain support config (pre-fetched from validate_token_chain)
            amount: Deposit amount (in requested_currency)
            callback_url: Callback URL
            extra_data: Extra data
            requested_currency: Currency of amount (USDT for crypto, CNY/USD for fiat)

        Returns:
            Created order

        Raises:
            PaymentError: On creation failure
            InsufficientBalanceError: If insufficient credits for fee
        """
        # Check duplicate out_trade_no
        result = await self.db.execute(
            select(Order).where(
                Order.merchant_id == merchant.id,
                Order.out_trade_no == out_trade_no,
            )
        )
        if result.scalar_one_or_none():
            raise PaymentError(
                PaymentErrorCode.DUPLICATE_REF,
                f"Order with out_trade_no '{out_trade_no}' already exists",
            )

        # Get available deposit wallet
        wallet = await self._get_available_deposit_wallet(merchant.id, chain.id, token.id)
        if not wallet:
            raise PaymentError(
                PaymentErrorCode.NO_AVAILABLE_ADDRESS,
                "No available deposit address",
            )

        # Calculate payment amount based on currency
        payment_amount = amount
        exchange_rate: Decimal | None = None
        requested_currency_upper = requested_currency.upper()

        if requested_currency_upper != token.code.upper():
            # Need to convert from fiat to crypto
            from src.services.exchange_rate_service import ExchangeRateService

            rate_service = ExchangeRateService(self.db)
            calc_result = await rate_service.calculate_payment_amount(
                user_id=merchant.id,  # type: ignore
                requested_amount=amount,
                requested_currency=requested_currency_upper,
                payment_currency=token.code.upper(),
            )
            if not calc_result:
                raise PaymentError(
                    PaymentErrorCode.INVALID_REQUEST,
                    f"无法获取 {token.code}/{requested_currency_upper} 汇率",
                )
            payment_amount = calc_result["payment_amount"]
            exchange_rate = calc_result["exchange_rate"]

        # Check minimum deposit (support already passed in)
        if support.min_deposit:
            min_amount = Decimal(support.min_deposit)
            if payment_amount < min_amount:
                raise PaymentError(
                    PaymentErrorCode.AMOUNT_TOO_SMALL,
                    f"Amount must be at least {min_amount} {token.code}",
                )

        # Get fee config once and calculate deposit fee
        fee_config = await self._get_fee_config(merchant)
        fee = self._calculate_deposit_fee(payment_amount, fee_config)

        # Get merchant-specific deposit expiry time
        from src.services.merchant_setting_service import MerchantSettingService

        merchant_setting_service = MerchantSettingService(self.db)
        deposit_expiry_seconds = await merchant_setting_service.get_deposit_expiry_seconds(
            merchant.id, default=self.deposit_expiry_seconds
        )

        # Generate unique payment amount to avoid collisions
        from src.utils.amount import generate_unique_amount

        try:
            unique_amount = await generate_unique_amount(
                wallet.address,
                payment_amount,
                ttl_seconds=deposit_expiry_seconds + 60,  # TTL slightly longer than order expiry
            )
        except ValueError as e:
            raise PaymentError(
                PaymentErrorCode.WALLET_NOT_AVAILABLE,
                str(e),
            ) from e

        # Create order first to get order_id for ledger
        expire_time = datetime.now(UTC) + timedelta(seconds=deposit_expiry_seconds)
        order = Order(
            order_no=generate_order_no(OrderType.DEPOSIT),
            out_trade_no=out_trade_no,
            order_type=OrderType.DEPOSIT,
            merchant_id=merchant.id,
            token=token.code,
            chain=chain.code.lower(),
            requested_amount=amount,  # 商户请求的原始金额（可能是法币）
            requested_currency=requested_currency_upper,  # 请求金额的币种
            exchange_rate=exchange_rate,  # 下单时使用的汇率
            amount=unique_amount,  # 用户实际支付金额（加密货币，含尾数）
            fee=fee,
            net_amount=unique_amount - fee,  # 用户实际到账 = 实付金额 - 手续费
            wallet_address=wallet.address,
            callback_url=callback_url,
            extra_data=extra_data,
            expire_time=expire_time,
            status=OrderStatus.PENDING,
        )

        self.db.add(order)
        await self.db.flush()  # Get order.id without committing

        # Freeze fee from merchant credits
        # Raises InsufficientBalanceError if balance insufficient
        await self.db.refresh(merchant)  # Refresh to get latest balance
        await self.ledger_service.freeze_fee(
            user=merchant,
            amount=fee,
            order_id=order.id,
            remark=f"充值订单手续费冻结 - {order.order_no}",
        )

        await self.db.commit()
        await self.db.refresh(order)

        # Schedule order expiration task
        from src.tasks.orders import expire_order

        expire_order.apply_async(
            args=[order.id],
            countdown=deposit_expiry_seconds,
            queue="orders",  # Send to orders queue
        )

        return order

    async def create_withdraw_order(
        self,
        merchant: User,
        out_trade_no: str,
        token: Token,
        chain: Chain,
        support: TokenChainSupport,
        amount: Decimal,
        to_address: str,
        callback_url: str,
        extra_data: str | None = None,
    ) -> Order:
        """Create a new withdrawal order.

        Args:
            merchant: Merchant user
            out_trade_no: External trade number
            token: Token
            chain: Chain
            support: Token-chain support config (pre-fetched from validate_token_chain)
            amount: Withdrawal amount
            to_address: Destination address
            callback_url: Callback URL
            extra_data: Extra data

        Returns:
            Created order

        Raises:
            PaymentError: On creation failure
            InsufficientBalanceError: If insufficient credits for fee
        """
        # Check duplicate out_trade_no
        result = await self.db.execute(
            select(Order).where(
                Order.merchant_id == merchant.id,
                Order.out_trade_no == out_trade_no,
            )
        )
        if result.scalar_one_or_none():
            raise PaymentError(
                PaymentErrorCode.DUPLICATE_REF,
                f"Order with out_trade_no '{out_trade_no}' already exists",
            )

        # Validate address format (basic check)
        if not self._validate_address(to_address, chain.code):
            raise PaymentError(
                PaymentErrorCode.INVALID_ADDRESS,
                "Invalid wallet address",
            )

        # Check minimum withdrawal (support already passed in)
        if support.min_withdrawal:
            min_amount = Decimal(support.min_withdrawal)
            if amount < min_amount:
                raise PaymentError(
                    PaymentErrorCode.AMOUNT_TOO_SMALL,
                    f"Withdrawal amount must be at least {min_amount}",
                )

        # Get fee config once and calculate withdrawal fee
        fee_config = await self._get_fee_config(merchant)
        fee = self._calculate_withdraw_fee(amount, support, fee_config)

        # Create order first to get order_id for ledger
        net_amount = amount  # User receives full amount, fee is separate
        order = Order(
            order_no=generate_order_no(OrderType.WITHDRAW),
            out_trade_no=out_trade_no,
            order_type=OrderType.WITHDRAW,
            merchant_id=merchant.id,
            token=token.code,
            chain=chain.code.lower(),
            requested_amount=amount,  # 提现无金额修改，原始金额=实际金额
            amount=amount,
            fee=fee,
            net_amount=net_amount,
            to_address=to_address,
            callback_url=callback_url,
            extra_data=extra_data,
            status=OrderStatus.PENDING,
        )

        self.db.add(order)
        await self.db.flush()  # Get order.id without committing

        # Freeze fee from merchant credits
        # Raises InsufficientBalanceError if balance insufficient
        await self.db.refresh(merchant)  # Refresh to get latest balance
        await self.ledger_service.freeze_fee(
            user=merchant,
            amount=fee,
            order_id=order.id,
            remark=f"提现订单手续费冻结 - {order.order_no}",
        )

        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def get_order_by_no(self, order_no: str, merchant_id: int) -> Order | None:
        """Get order by system order number.

        Args:
            order_no: System order number
            merchant_id: Merchant ID

        Returns:
            Order or None
        """
        result = await self.db.execute(
            select(Order).where(
                Order.order_no == order_no,
                Order.merchant_id == merchant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_order_by_out_trade_no(
        self,
        out_trade_no: str,
        merchant_id: int,
        order_type: OrderType,
    ) -> Order | None:
        """Get order by external trade number.

        Args:
            out_trade_no: External trade number
            merchant_id: Merchant ID
            order_type: Order type

        Returns:
            Order or None
        """
        result = await self.db.execute(
            select(Order).where(
                Order.out_trade_no == out_trade_no,
                Order.merchant_id == merchant_id,
                Order.order_type == order_type,
            )
        )
        return result.scalar_one_or_none()

    def order_to_response(self, order: Order, merchant_no: str) -> dict[str, Any]:
        """Convert order to response dict.

        Args:
            order: Order model
            merchant_no: Merchant number

        Returns:
            Response dict
        """
        return {
            "success": True,
            "order_no": order.order_no,
            "out_trade_no": order.out_trade_no,
            "order_type": order.order_type.value,
            "token": order.token,
            "chain": order.chain,
            "amount": str(order.amount),
            "fee": str(order.fee),
            "net_amount": str(order.net_amount),
            "status": order.status.value,
            "wallet_address": order.wallet_address,
            "to_address": order.to_address,
            "tx_hash": order.tx_hash,
            "confirmations": order.confirmations,
            "created_at": format_utc_datetime(order.created_at),
            "completed_at": format_utc_datetime(order.completed_at),
            "extra_data": order.extra_data,
        }

    # ============ Order Status Updates ============

    async def update_order_status(
        self,
        order: Order,
        new_status: OrderStatus,
        tx_hash: str | None = None,
        confirmations: int | None = None,
    ) -> Order:
        """Update order status.

        Args:
            order: Order to update
            new_status: New status
            tx_hash: Transaction hash (if available)
            confirmations: Confirmation count (if available)

        Returns:
            Updated order
        """
        order.status = new_status
        if tx_hash:
            order.tx_hash = tx_hash
        if confirmations is not None:
            order.confirmations = confirmations
        if new_status in (OrderStatus.SUCCESS, OrderStatus.FAILED, OrderStatus.EXPIRED):
            order.completed_at = datetime.now(UTC)

            # Release unique amount suffix for deposit orders
            if order.order_type == OrderType.DEPOSIT and order.wallet_address and order.amount:
                from src.utils.amount import release_amount_suffix

                try:
                    await release_amount_suffix(order.wallet_address, order.amount)
                except Exception as e:
                    # Log but don't fail the status update
                    logger.warning(
                        f"Failed to release amount suffix for order {order.order_no}: {e}"
                    )

        order.updated_at = datetime.now(UTC)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    # ============ Callback ============

    def build_callback_signature_message(self, order: Order, merchant_no: str) -> str:
        """Build signature message for callback.

        Signature order: merchant_no + order_no + status + amount

        Args:
            order: Order
            merchant_no: Merchant number

        Returns:
            Signature message
        """
        return f"{merchant_no}{order.order_no}{order.status.value}{order.amount}"

    async def build_callback_payload(self, order: Order) -> dict[str, Any]:
        """Build callback payload for an order.

        Args:
            order: Order

        Returns:
            Callback payload dict
        """
        merchant = await self.db.get(User, order.merchant_id)
        if not merchant:
            raise PaymentError(PaymentErrorCode.INVALID_MERCHANT, "Merchant not found")

        merchant_no = f"M{merchant.id}"

        # Determine signing key
        if order.order_type == OrderType.DEPOSIT:
            sign_key = merchant.deposit_key
        else:
            sign_key = merchant.withdraw_key

        if not sign_key:
            raise PaymentError(PaymentErrorCode.INVALID_MERCHANT, "Merchant key not configured")

        # Build signature
        sign_message = self.build_callback_signature_message(order, merchant_no)
        signature = self.generate_signature(sign_message, sign_key)

        timestamp = int(time.time() * 1000)

        return {
            "merchant_no": merchant_no,
            "order_no": order.order_no,
            "out_trade_no": order.out_trade_no,
            "order_type": order.order_type.value,
            "token": order.token,
            "chain": order.chain,
            "amount": str(order.amount),
            "fee": str(order.fee),
            "net_amount": str(order.net_amount),
            "status": order.status.value,
            "wallet_address": order.wallet_address,
            "to_address": order.to_address,
            "tx_hash": order.tx_hash,
            "confirmations": order.confirmations,
            "completed_at": format_utc_datetime(order.completed_at),
            "extra_data": order.extra_data,
            "timestamp": timestamp,
            "sign": signature,
        }

    async def mark_callback_success(self, order: Order) -> Order:
        """Mark callback as successfully delivered.

        Args:
            order: Order

        Returns:
            Updated order
        """
        order.callback_status = CallbackStatus.SUCCESS
        order.last_callback_at = datetime.now(UTC)
        order.updated_at = datetime.now(UTC)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def mark_callback_failed(
        self, order: Order, increment_retry: bool = True, max_retries: int | None = None
    ) -> Order:
        """Mark callback as failed.

        Args:
            order: Order
            increment_retry: Whether to increment retry count
            max_retries: Max retry count (if None, uses merchant setting)

        Returns:
            Updated order
        """
        if increment_retry:
            order.callback_retry_count += 1

        # Get max retries from merchant settings if not provided
        if max_retries is None:
            from src.services.merchant_setting_service import MerchantSettingService

            merchant_setting_service = MerchantSettingService(self.db)
            max_retries = await merchant_setting_service.get_callback_retry_count(
                order.merchant_id, default=3
            )

        # Mark as permanently failed after max retries
        if order.callback_retry_count >= max_retries:
            order.callback_status = CallbackStatus.FAILED
        order.last_callback_at = datetime.now(UTC)
        order.updated_at = datetime.now(UTC)
        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    # ============ Private Helpers ============

    async def _get_available_deposit_wallet(
        self,
        merchant_id: int,
        chain_id: int,
        token_id: int | None,
    ) -> Wallet | None:
        """Get an available deposit wallet using round-robin allocation with row locking.

        Selection logic:
        1. Wallets with NULL last_used_at are prioritized (never used)
        2. Then sorted by last_used_at ascending (least recently used first)
        3. On selection, update last_used_at to current time
        4. Uses FOR UPDATE SKIP LOCKED to handle concurrent requests

        This ensures each wallet is used in rotation before repeating,
        and concurrent requests will get different wallets.

        Args:
            merchant_id: Merchant ID
            chain_id: Chain ID
            token_id: Token ID (optional)

        Returns:
            Available wallet or None
        """
        from sqlalchemy import case

        # MySQL doesn't support NULLS FIRST, use CASE expression instead
        # NULL values get 0 (sorted first), non-NULL get 1 (sorted after)
        null_first_expr = case(
            (Wallet.last_used_at.is_(None), 0),
            else_=1,
        )

        query = (
            select(Wallet)
            .where(
                Wallet.user_id == merchant_id,
                Wallet.chain_id == chain_id,
                Wallet.is_active == True,  # noqa: E712
                Wallet.wallet_type == WalletType.MERCHANT,
            )
            .order_by(
                null_first_expr,  # NULL first (unused wallets)
                Wallet.last_used_at,  # Then by last_used_at ascending
                Wallet.created_at,  # Then by creation time
            )
            .limit(1)
            .with_for_update(skip_locked=True)  # Row lock, skip already locked rows
        )

        # If token_id specified, filter by it
        if token_id:
            query = query.where(Wallet.token_id == token_id)

        result = await self.db.execute(query)
        wallet = result.scalar_one_or_none()

        # Update last_used_at for round-robin rotation
        if wallet:
            wallet.last_used_at = datetime.now(UTC)
            self.db.add(wallet)
            # Note: commit is handled by caller (create_deposit_order)

        return wallet

    async def _get_fee_config(self, merchant: User) -> FeeConfig | None:
        """Get fee config for merchant (merchant-specific or default).

        Args:
            merchant: Merchant user

        Returns:
            FeeConfig or None
        """
        # Try merchant's fee config first
        if merchant.fee_config_id:
            fee_config = await self.db.get(FeeConfig, merchant.fee_config_id)
            if fee_config:
                return fee_config

        # Fall back to default fee config
        result = await self.db.execute(
            select(FeeConfig).where(FeeConfig.is_default == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    def _calculate_deposit_fee(
        self,
        amount: Decimal,
        fee_config: FeeConfig | None,
    ) -> Decimal:
        """Calculate deposit fee.

        Args:
            amount: Deposit amount
            fee_config: Fee configuration (pre-fetched)

        Returns:
            Fee amount
        """
        if fee_config:
            return fee_config.calculate_deposit_fee(amount)
        return Decimal("0")

    def _calculate_withdraw_fee(
        self,
        amount: Decimal,
        support: TokenChainSupport | None,
        fee_config: FeeConfig | None,
    ) -> Decimal:
        """Calculate withdrawal fee.

        Args:
            amount: Withdrawal amount
            support: Token-chain support config
            fee_config: Fee configuration (pre-fetched)

        Returns:
            Fee amount
        """
        # Try to get fee from token-chain support first
        if support and support.withdrawal_fee:
            return Decimal(support.withdrawal_fee)

        # Fall back to fee config
        if fee_config:
            return fee_config.calculate_withdraw_fee(amount)

        return Decimal("0")

    def _validate_address(self, address: str, chain_code: str) -> bool:
        """Basic address format validation.

        Args:
            address: Wallet address
            chain_code: Chain code

        Returns:
            True if address format is valid
        """
        chain_upper = chain_code.upper()
        if not address:
            return False

        if chain_upper == "TRON":
            # TRON addresses start with T and are 34 chars
            return address.startswith("T") and len(address) == 34
        elif chain_upper == "ETHEREUM":
            # ETH addresses start with 0x and are 42 chars
            return address.startswith("0x") and len(address) == 42
        elif chain_upper == "SOLANA":
            # Solana addresses are 32-44 chars base58
            return 32 <= len(address) <= 44

        return True  # Unknown chain, skip validation
