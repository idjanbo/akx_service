"""Order schemas for API request/response."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.models.order import CallbackStatus, OrderStatus, OrderType

# ============ Order Response Schemas ============


class OrderResponse(BaseModel):
    """Schema for order response."""

    id: int
    order_no: str
    out_trade_no: str
    order_type: OrderType
    merchant_id: int
    merchant_name: str | None = None

    # Payment details
    token: str
    chain: str
    requested_amount: Decimal | None = None
    amount: Decimal
    fee: Decimal
    net_amount: Decimal

    # Address info
    wallet_address: str | None = None
    to_address: str | None = None

    # Blockchain info
    tx_hash: str | None = None
    confirmations: int

    # Status
    status: OrderStatus
    callback_status: CallbackStatus
    callback_retry_count: int
    last_callback_at: datetime | None = None

    # Extra
    extra_data: str | None = None
    remark: str | None = None

    # Timestamps
    expire_time: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Schema for paginated order list."""

    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


# ============ Order Query Schemas ============


class OrderQueryParams(BaseModel):
    """Schema for order query parameters."""

    order_no: str | None = None
    out_trade_no: str | None = None
    order_type: OrderType | None = None
    merchant_id: int | None = None
    token: str | None = None
    chain: str | None = None
    status: OrderStatus | None = None
    callback_status: CallbackStatus | None = None
    tx_hash: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


# ============ Order Action Schemas ============


class RetryCallbackRequest(BaseModel):
    """Schema for retry callback request."""

    pass  # No additional params needed


class ForceCompleteRequest(BaseModel):
    """补单请求。"""

    remark: str = Field(
        min_length=1,
        max_length=500,
        description="补单备注（必填）",
    )
    totp_code: str = Field(
        min_length=6,
        max_length=6,
        description="TOTP 验证码",
    )


class OrderActionResponse(BaseModel):
    """Schema for order action response."""

    success: bool
    message: str
    order: OrderResponse | None = None
