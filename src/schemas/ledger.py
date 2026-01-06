"""Ledger schemas - Request/Response DTOs for balance ledger records."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.models.ledger import BalanceChangeType

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
