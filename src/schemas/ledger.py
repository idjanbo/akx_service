"""Ledger schemas - Request/Response DTOs for transaction records."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.models.ledger import (
    AddressTransactionType,
    BalanceChangeType,
    RechargeStatus,
    RechargeType,
)

# =============================================================================
# Address Transaction Schemas (地址历史记录)
# =============================================================================


class AddressTransactionResponse(BaseModel):
    """Address transaction response."""

    id: int
    user_id: int
    wallet_id: int | None = None
    order_id: int | None = None

    tx_type: AddressTransactionType
    token: str
    chain: str
    amount: Decimal
    address: str
    tx_hash: str | None = None

    created_at: datetime

    # Joined fields
    order_no: str | None = None
    user_email: str | None = None

    class Config:
        from_attributes = True


class AddressTransactionListResponse(BaseModel):
    """Paginated address transaction list response."""

    items: list[AddressTransactionResponse]
    total: int
    page: int
    page_size: int


class AddressTransactionQueryParams(BaseModel):
    """Query parameters for address transactions."""

    user_id: int | None = None
    wallet_id: int | None = None
    address: str | None = None
    tx_type: AddressTransactionType | None = None
    token: str | None = None
    chain: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# =============================================================================
# Balance Ledger Schemas (积分明细)
# =============================================================================


class BalanceLedgerResponse(BaseModel):
    """Balance ledger response."""

    id: int
    user_id: int
    order_id: int | None = None

    change_type: BalanceChangeType
    amount: Decimal
    pre_balance: Decimal
    post_balance: Decimal

    frozen_amount: Decimal
    pre_frozen: Decimal
    post_frozen: Decimal

    remark: str | None = None
    operator_id: int | None = None

    created_at: datetime

    # Joined fields
    order_no: str | None = None
    user_email: str | None = None
    operator_email: str | None = None

    class Config:
        from_attributes = True


class BalanceLedgerListResponse(BaseModel):
    """Paginated balance ledger list response."""

    items: list[BalanceLedgerResponse]
    total: int
    page: int
    page_size: int


class BalanceLedgerQueryParams(BaseModel):
    """Query parameters for balance ledger."""

    user_id: int | None = None
    change_type: BalanceChangeType | None = None
    order_id: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ManualBalanceAdjustRequest(BaseModel):
    """Request to manually adjust user balance."""

    user_id: int
    amount: Decimal = Field(description="Amount to add (positive) or deduct (negative)")
    remark: str = Field(min_length=1, max_length=500, description="Reason for adjustment")


# =============================================================================
# Recharge Record Schemas (充值记录)
# =============================================================================


class RechargeRecordResponse(BaseModel):
    """Recharge record response."""

    id: int
    user_id: int
    ledger_id: int | None = None

    recharge_type: RechargeType
    status: RechargeStatus
    amount: Decimal
    payment_method: str | None = None

    remark: str | None = None

    created_at: datetime
    completed_at: datetime | None = None

    # Joined fields
    user_email: str | None = None
    post_balance: Decimal | None = None  # 账变后余额，从关联的 BalanceLedger 获取

    class Config:
        from_attributes = True


class RechargeRecordListResponse(BaseModel):
    """Paginated recharge record list response."""

    items: list[RechargeRecordResponse]
    total: int
    page: int
    page_size: int


class RechargeRecordQueryParams(BaseModel):
    """Query parameters for recharge records."""

    user_id: int | None = None
    recharge_type: RechargeType | None = None
    status: RechargeStatus | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CreateRechargeRequest(BaseModel):
    """Request to create a manual recharge/deduction."""

    user_id: int
    amount: Decimal = Field(description="Amount (positive for add, negative for deduct)")
    remark: str = Field(min_length=1, max_length=500, description="Reason")
