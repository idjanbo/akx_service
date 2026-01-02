"""AKX Crypto Payment Gateway - Request/Response schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.models.order import OrderStatus, OrderType
from src.models.wallet import Chain, WalletType

# ============ Wallet Schemas ============


class WalletResponse(BaseModel):
    """Wallet response (excludes private key)."""

    id: int
    chain: Chain
    address: str
    wallet_type: WalletType
    is_active: bool
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateWalletRequest(BaseModel):
    """Request to create a new wallet."""

    chain: Chain
    label: str | None = None


class DepositAddressRequest(BaseModel):
    """Request for deposit address."""

    chain: Chain


class DepositAddressResponse(BaseModel):
    """Deposit address response."""

    chain: Chain
    address: str
    label: str | None


# ============ Order Schemas ============


class CreateWithdrawalRequest(BaseModel):
    """Request to create a withdrawal order."""

    chain: Chain
    to_address: str = Field(..., min_length=20, max_length=100)
    amount: Decimal = Field(..., gt=0, decimal_places=8)
    merchant_ref: str | None = Field(default=None, max_length=255)


class OrderResponse(BaseModel):
    """Order response."""

    id: int
    order_no: str
    merchant_ref: str | None
    order_type: OrderType
    chain: str
    amount: Decimal
    fee: Decimal
    net_amount: Decimal
    status: OrderStatus
    wallet_address: str
    tx_hash: str | None
    confirmations: int
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    """Paginated order list response."""

    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


# ============ Balance Schemas ============


class BalanceResponse(BaseModel):
    """User balance response."""

    user_id: int
    available_balance: Decimal
    frozen_balance: Decimal
    total_balance: Decimal


class ChainBalanceResponse(BaseModel):
    """On-chain wallet balance."""

    chain: Chain
    address: str
    native_balance: Decimal
    usdt_balance: Decimal


# ============ Common Schemas ============


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: str = "OK"


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = False
    error: str
    details: dict | None = None
