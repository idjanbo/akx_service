"""AKX Crypto Payment Gateway - Payment schemas.

Schemas for payment API (deposit/withdrawal order creation and query).
Uses HMAC-SHA256 signature for authentication.

Payment method is uniquely identified by: chain + token
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from src.models.order import OrderStatus, OrderType
from src.models.wallet import Chain, Token

# ============ Signature Schemas ============


class SignedRequest(BaseModel):
    """Base class for signed API requests.

    All payment API requests must include:
    - merchant_no: Merchant identifier
    - timestamp: Request timestamp (Unix milliseconds)
    - nonce: Random string to prevent replay attacks
    - sign: HMAC-SHA256 signature
    """

    merchant_no: str = Field(..., description="Merchant number")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    nonce: str = Field(..., min_length=16, max_length=32, description="Random string")
    sign: str = Field(..., description="HMAC-SHA256 signature")


# ============ Deposit Order Schemas ============


class CreateDepositOrderRequest(SignedRequest):
    """Request to create a deposit order.

    Payment method: chain + token (e.g., TRON + USDT, Ethereum + USDC)

    Signed fields (in order):
        merchant_no + timestamp + nonce + merchant_ref + chain + token + amount + callback_url
    """

    merchant_ref: str = Field(..., max_length=64, description="Merchant's order reference")
    chain: Chain = Field(..., description="Blockchain network")
    token: Token = Field(default=Token.USDT, description="Token/currency")
    amount: Decimal = Field(..., gt=0, decimal_places=8, description="Expected deposit amount")
    callback_url: str = Field(..., max_length=512, description="Webhook callback URL")
    extra_data: str | None = Field(
        default=None, max_length=1024, description="Extra data to return in callback"
    )


class CreateDepositOrderResponse(BaseModel):
    """Response for deposit order creation."""

    success: bool = True
    order_no: str = Field(..., description="System order number")
    merchant_ref: str = Field(..., description="Merchant's order reference")
    chain: str = Field(..., description="Blockchain network")
    token: str = Field(..., description="Token/currency")
    amount: str = Field(..., description="Expected deposit amount")
    wallet_address: str = Field(..., description="Deposit wallet address")
    expire_time: datetime = Field(..., description="Order expiration time")
    created_at: datetime = Field(..., description="Order creation time")


# ============ Withdrawal Order Schemas ============


class CreateWithdrawOrderRequest(SignedRequest):
    """Request to create a withdrawal order.

    Payment method: chain + token (e.g., TRON + USDT, Ethereum + USDC)

    Signed fields (in order):
        merchant_no + timestamp + nonce + merchant_ref
        + chain + token + amount + to_address + callback_url
    """

    merchant_ref: str = Field(..., max_length=64, description="Merchant's order reference")
    chain: Chain = Field(..., description="Blockchain network")
    token: Token = Field(default=Token.USDT, description="Token/currency")
    amount: Decimal = Field(..., gt=0, decimal_places=8, description="Withdrawal amount")
    to_address: str = Field(..., max_length=100, description="Destination wallet address")
    callback_url: str = Field(..., max_length=512, description="Webhook callback URL")
    extra_data: str | None = Field(
        default=None, max_length=1024, description="Extra data to return in callback"
    )


class CreateWithdrawOrderResponse(BaseModel):
    """Response for withdrawal order creation."""

    success: bool = True
    order_no: str = Field(..., description="System order number")
    merchant_ref: str = Field(..., description="Merchant's order reference")
    chain: str = Field(..., description="Blockchain network")
    token: str = Field(..., description="Token/currency")
    amount: str = Field(..., description="Withdrawal amount")
    fee: str = Field(..., description="Fee amount")
    net_amount: str = Field(..., description="Net amount after fee")
    to_address: str = Field(..., description="Destination wallet address")
    status: str = Field(..., description="Order status")
    created_at: datetime = Field(..., description="Order creation time")


# ============ Order Query Schemas ============


class QueryOrderRequest(SignedRequest):
    """Request to query an order.

    Signed fields (in order):
        merchant_no + timestamp + nonce + order_no
    """

    order_no: str = Field(..., description="System order number to query")


class QueryOrderByRefRequest(SignedRequest):
    """Request to query an order by merchant reference.

    Signed fields (in order):
        merchant_no + timestamp + nonce + merchant_ref + order_type
    """

    merchant_ref: str = Field(..., description="Merchant's order reference")
    order_type: Literal["deposit", "withdrawal"] = Field(..., description="Order type")


class OrderQueryResponse(BaseModel):
    """Response for order query."""

    success: bool = True
    order_no: str
    merchant_ref: str | None
    order_type: OrderType
    chain: str
    token: str
    amount: str
    fee: str
    net_amount: str
    status: OrderStatus
    wallet_address: str
    tx_hash: str | None
    confirmations: int
    created_at: datetime
    completed_at: datetime | None
    extra_data: str | None = None


# ============ Callback Schemas ============


class OrderCallbackPayload(BaseModel):
    """Webhook callback payload sent to merchant.

    The callback includes a signature for verification:
        sign = HMAC-SHA256(merchant_no + order_no + status + amount, deposit_key or withdraw_key)
    """

    merchant_no: str
    order_no: str
    merchant_ref: str | None
    order_type: str
    chain: str
    token: str
    amount: str
    fee: str
    net_amount: str
    status: str
    wallet_address: str
    tx_hash: str | None
    confirmations: int
    completed_at: str | None
    extra_data: str | None
    timestamp: int
    sign: str


# ============ Error Response ============


class PaymentErrorResponse(BaseModel):
    """Error response for payment API."""

    success: bool = False
    error_code: str
    error_message: str
