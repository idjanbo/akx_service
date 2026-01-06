"""Schemas module - Pydantic DTOs for request/response."""

from src.schemas.fee_config import (
    FeeCalculationRequest,
    FeeCalculationResponse,
    FeeConfigCreate,
    FeeConfigResponse,
    FeeConfigUpdate,
)
from src.schemas.ledger import (
    BalanceLedgerListResponse,
    BalanceLedgerQueryParams,
    BalanceLedgerResponse,
    ManualBalanceAdjustRequest,
)
from src.schemas.payment import (
    CallbackPayload,
    CreateDepositRequest,
    CreateDepositResponse,
    CreateWithdrawRequest,
    CreateWithdrawResponse,
    OrderDetailResponse,
    OrderTypeEnum,
    PaymentErrorCode,
    PaymentErrorResponse,
    QueryOrderByOutTradeNoRequest,
    QueryOrderRequest,
)

__all__: list[str] = [
    # Fee Config
    "FeeConfigCreate",
    "FeeConfigUpdate",
    "FeeConfigResponse",
    "FeeCalculationRequest",
    "FeeCalculationResponse",
    # Ledger
    "BalanceLedgerResponse",
    "BalanceLedgerListResponse",
    "BalanceLedgerQueryParams",
    "ManualBalanceAdjustRequest",
    # Payment
    "CreateDepositRequest",
    "CreateDepositResponse",
    "CreateWithdrawRequest",
    "CreateWithdrawResponse",
    "QueryOrderRequest",
    "QueryOrderByOutTradeNoRequest",
    "OrderDetailResponse",
    "OrderTypeEnum",
    "CallbackPayload",
    "PaymentErrorResponse",
    "PaymentErrorCode",
]
