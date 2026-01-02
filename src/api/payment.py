"""AKX Crypto Payment Gateway - Payment API routes.

Public API for merchants to create and query orders.
Uses HMAC-SHA256 signature for authentication.
"""

import hashlib
import hmac
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from src.db import get_session
from src.models.merchant import Merchant
from src.models.order import Order, OrderStatus, OrderType
from src.models.wallet import Wallet, WalletType, get_payment_method_expiry
from src.schemas.payment import (
    CreateDepositOrderRequest,
    CreateDepositOrderResponse,
    CreateWithdrawOrderRequest,
    CreateWithdrawOrderResponse,
    OrderQueryResponse,
    PaymentErrorResponse,
    QueryOrderByRefRequest,
    QueryOrderRequest,
)
from src.services.order_service import OrderService

router = APIRouter()

# Signature expiration time (5 minutes)
SIGNATURE_EXPIRY_MS = 5 * 60 * 1000


def verify_signature(
    message: str,
    signature: str,
    secret_key: str,
) -> bool:
    """Verify HMAC-SHA256 signature.

    Args:
        message: Concatenated string of signed fields
        signature: Hex-encoded signature to verify
        secret_key: Merchant's secret key

    Returns:
        True if signature is valid
    """
    expected = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected.lower(), signature.lower())


def generate_order_no() -> str:
    """Generate a unique order number."""
    timestamp = int(time.time() * 1000)
    random_suffix = uuid.uuid4().hex[:8].upper()
    return f"ORD{timestamp}{random_suffix}"


async def get_merchant_by_no(merchant_no: str) -> Merchant | None:
    """Get merchant by merchant number."""
    async with get_session() as db:
        result = await db.execute(
            select(Merchant).where(
                Merchant.merchant_no == merchant_no,
                Merchant.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()


async def validate_request_timestamp(timestamp: int) -> None:
    """Validate request timestamp is within acceptable range."""
    current_time = int(time.time() * 1000)
    if abs(current_time - timestamp) > SIGNATURE_EXPIRY_MS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "TIMESTAMP_EXPIRED",
                "error_message": "Request timestamp expired",
            },
        )


# ============ Deposit Order API ============


@router.post(
    "/deposit/create",
    response_model=CreateDepositOrderResponse,
    responses={400: {"model": PaymentErrorResponse}},
    summary="Create deposit order",
    description="Create a new deposit order. Requires HMAC-SHA256 signature using deposit_key.",
)
async def create_deposit_order(request: CreateDepositOrderRequest):
    """Create a new deposit order.

    Payment method is uniquely identified by: chain + token

    Signature message format:
        merchant_no + timestamp + nonce + merchant_ref + chain + token + amount + callback_url

    Example:
        message = (merchant_no + timestamp + nonce + merchant_ref
                   + chain + token + amount + callback_url)
        sign = HMAC-SHA256(message, deposit_key)
    """
    # Validate timestamp
    await validate_request_timestamp(request.timestamp)

    # Get merchant
    merchant = await get_merchant_by_no(request.merchant_no)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_MERCHANT",
                "error_message": "Invalid merchant",
            },
        )

    # Build signature message (include token)
    sign_message = (
        request.merchant_no
        + str(request.timestamp)
        + request.nonce
        + request.merchant_ref
        + request.chain.value
        + request.token.value
        + str(request.amount)
        + request.callback_url
    )

    # Verify signature using deposit_key
    if not verify_signature(sign_message, request.sign, merchant.deposit_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_SIGNATURE",
                "error_message": "Invalid signature",
            },
        )

    async with get_session() as db:
        # Check for duplicate merchant_ref
        existing = await db.execute(
            select(Order).where(
                Order.merchant_ref == request.merchant_ref,
                Order.user_id == merchant.user_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "DUPLICATE_REF",
                    "error_message": "Duplicate merchant reference",
                },
            )

        # Get or create deposit wallet
        result = await db.execute(
            select(Wallet).where(
                Wallet.user_id == merchant.user_id,
                Wallet.chain == request.chain,
                Wallet.wallet_type == WalletType.DEPOSIT,
                Wallet.is_active == True,  # noqa: E712
            )
        )
        wallet = result.scalar_one_or_none()

        if not wallet:
            # Create new deposit wallet
            from src.services.wallet_service import WalletService

            wallet_service = WalletService(db)
            wallet = await wallet_service.create_wallet(
                user_id=merchant.user_id,
                chain=request.chain,
                wallet_type=WalletType.DEPOSIT,
            )

        # Create order with payment method specific expiry time
        order_no = generate_order_no()
        expiry_minutes = get_payment_method_expiry(request.chain, request.token)
        expire_time = datetime.utcnow() + timedelta(minutes=expiry_minutes)

        order = Order(
            order_no=order_no,
            merchant_ref=request.merchant_ref,
            user_id=merchant.user_id,
            order_type=OrderType.DEPOSIT,
            chain=request.chain.value,
            token=request.token.value,
            amount=request.amount,
            fee=Decimal("0"),
            net_amount=request.amount,
            status=OrderStatus.PENDING,
            wallet_address=wallet.address,
            chain_metadata={
                "callback_url": request.callback_url,
                "extra_data": request.extra_data,
                "expire_time": expire_time.isoformat(),
            },
        )

        db.add(order)
        await db.commit()

        # Schedule delayed task to expire this order
        from src.workers.tasks.order_expiry import schedule_order_expiry

        schedule_order_expiry(order_no, expiry_minutes * 60)

        return CreateDepositOrderResponse(
            order_no=order_no,
            merchant_ref=request.merchant_ref,
            chain=request.chain.value,
            token=request.token.value,
            amount=str(request.amount),
            wallet_address=wallet.address,
            expire_time=expire_time,
            created_at=order.created_at,
        )


# ============ Withdrawal Order API ============


@router.post(
    "/withdraw/create",
    response_model=CreateWithdrawOrderResponse,
    responses={400: {"model": PaymentErrorResponse}},
    summary="Create withdrawal order",
    description="Create a new withdrawal order. Requires HMAC-SHA256 signature using withdraw_key.",
)
async def create_withdraw_order(request: CreateWithdrawOrderRequest):
    """Create a new withdrawal order.

    Payment method is uniquely identified by: chain + token

    Signature message format:
        merchant_no + timestamp + nonce + merchant_ref
        + chain + token + amount + to_address + callback_url

    Example:
        message = (merchant_no + timestamp + nonce + merchant_ref
                   + chain + token + amount + to_address + callback_url)
        sign = HMAC-SHA256(message, withdraw_key)
    """
    # Validate timestamp
    await validate_request_timestamp(request.timestamp)

    # Get merchant
    merchant = await get_merchant_by_no(request.merchant_no)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_MERCHANT",
                "error_message": "Invalid merchant",
            },
        )

    # Build signature message (include token)
    sign_message = (
        request.merchant_no
        + str(request.timestamp)
        + request.nonce
        + request.merchant_ref
        + request.chain.value
        + request.token.value
        + str(request.amount)
        + request.to_address
        + request.callback_url
    )

    # Verify signature using withdraw_key
    if not verify_signature(sign_message, request.sign, merchant.withdraw_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_SIGNATURE",
                "error_message": "Invalid signature",
            },
        )

    async with get_session() as db:
        # Check for duplicate merchant_ref
        existing = await db.execute(
            select(Order).where(
                Order.merchant_ref == request.merchant_ref,
                Order.user_id == merchant.user_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "DUPLICATE_REF",
                    "error_message": "Duplicate merchant reference",
                },
            )

        # Use order service to create withdrawal
        order_service = OrderService(db)

        try:
            order = await order_service.create_withdrawal(
                user_id=merchant.user_id,
                chain=request.chain,
                to_address=request.to_address,
                amount=request.amount,
                merchant_ref=request.merchant_ref,
                token=request.token,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "INSUFFICIENT_BALANCE",
                    "error_message": str(e),
                },
            )

        # Store callback URL
        order.chain_metadata = {
            **order.chain_metadata,
            "callback_url": request.callback_url,
            "extra_data": request.extra_data,
        }
        await db.commit()

        return CreateWithdrawOrderResponse(
            order_no=order.order_no,
            merchant_ref=request.merchant_ref,
            chain=request.chain.value,
            token=request.token.value,
            amount=str(order.amount),
            fee=str(order.fee),
            net_amount=str(order.net_amount),
            to_address=request.to_address,
            status=order.status.value,
            created_at=order.created_at,
        )


# ============ Order Query API ============


@router.post(
    "/order/query",
    response_model=OrderQueryResponse,
    responses={400: {"model": PaymentErrorResponse}},
    summary="Query order by order number",
    description="Query order details by system order number. Requires HMAC-SHA256 signature.",
)
async def query_order(request: QueryOrderRequest):
    """Query order by system order number.

    For deposit orders, use deposit_key for signature.
    For withdrawal orders, use withdraw_key for signature.

    Signature message format:
        merchant_no + timestamp + nonce + order_no
    """
    # Validate timestamp
    await validate_request_timestamp(request.timestamp)

    # Get merchant
    merchant = await get_merchant_by_no(request.merchant_no)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_MERCHANT",
                "error_message": "Invalid merchant",
            },
        )

    async with get_session() as db:
        # Get order
        result = await db.execute(
            select(Order).where(
                Order.order_no == request.order_no,
                Order.user_id == merchant.user_id,
            )
        )
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "ORDER_NOT_FOUND",
                    "error_message": "Order not found",
                },
            )

        # Build signature message
        sign_message = (
            request.merchant_no + str(request.timestamp) + request.nonce + request.order_no
        )

        # Use appropriate key based on order type
        secret_key = (
            merchant.deposit_key if order.order_type == OrderType.DEPOSIT else merchant.withdraw_key
        )

        if not verify_signature(sign_message, request.sign, secret_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "INVALID_SIGNATURE",
                    "error_message": "Invalid signature",
                },
            )

        return OrderQueryResponse(
            order_no=order.order_no,
            merchant_ref=order.merchant_ref,
            order_type=order.order_type,
            chain=order.chain,
            token=order.token,
            amount=str(order.amount),
            fee=str(order.fee),
            net_amount=str(order.net_amount),
            status=order.status,
            wallet_address=order.wallet_address,
            tx_hash=order.tx_hash,
            confirmations=order.confirmations,
            created_at=order.created_at,
            completed_at=order.completed_at,
            extra_data=order.chain_metadata.get("extra_data"),
        )


@router.post(
    "/order/query-by-ref",
    response_model=OrderQueryResponse,
    responses={400: {"model": PaymentErrorResponse}},
    summary="Query order by merchant reference",
    description="Query order details by merchant reference. Requires HMAC-SHA256 signature.",
)
async def query_order_by_ref(request: QueryOrderByRefRequest):
    """Query order by merchant reference.

    Signature message format:
        merchant_no + timestamp + nonce + merchant_ref + order_type
    """
    # Validate timestamp
    await validate_request_timestamp(request.timestamp)

    # Get merchant
    merchant = await get_merchant_by_no(request.merchant_no)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_MERCHANT",
                "error_message": "Invalid merchant",
            },
        )

    # Build signature message
    sign_message = (
        request.merchant_no
        + str(request.timestamp)
        + request.nonce
        + request.merchant_ref
        + request.order_type
    )

    # Use appropriate key based on order type
    secret_key = merchant.deposit_key if request.order_type == "deposit" else merchant.withdraw_key

    if not verify_signature(sign_message, request.sign, secret_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error_code": "INVALID_SIGNATURE",
                "error_message": "Invalid signature",
            },
        )

    async with get_session() as db:
        # Get order
        order_type = OrderType.DEPOSIT if request.order_type == "deposit" else OrderType.WITHDRAWAL
        result = await db.execute(
            select(Order).where(
                Order.merchant_ref == request.merchant_ref,
                Order.user_id == merchant.user_id,
                Order.order_type == order_type,
            )
        )
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "ORDER_NOT_FOUND",
                    "error_message": "Order not found",
                },
            )

        return OrderQueryResponse(
            order_no=order.order_no,
            merchant_ref=order.merchant_ref,
            order_type=order.order_type,
            chain=order.chain,
            token=order.token,
            amount=str(order.amount),
            fee=str(order.fee),
            net_amount=str(order.net_amount),
            status=order.status,
            wallet_address=order.wallet_address,
            tx_hash=order.tx_hash,
            confirmations=order.confirmations,
            created_at=order.created_at,
            completed_at=order.completed_at,
            extra_data=order.chain_metadata.get("extra_data"),
        )
