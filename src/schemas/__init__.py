"""Schemas module - Pydantic DTOs for request/response."""

from src.schemas.fee_config import (
    FeeCalculationRequest,
    FeeCalculationResponse,
    FeeConfigCreate,
    FeeConfigResponse,
    FeeConfigUpdate,
)
from src.schemas.ledger import (
    AddressTransactionListResponse,
    AddressTransactionQueryParams,
    AddressTransactionResponse,
    BalanceLedgerListResponse,
    BalanceLedgerQueryParams,
    BalanceLedgerResponse,
    CreateRechargeRequest,
    ManualBalanceAdjustRequest,
    RechargeRecordListResponse,
    RechargeRecordQueryParams,
    RechargeRecordResponse,
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
    "AddressTransactionResponse",
    "AddressTransactionListResponse",
    "AddressTransactionQueryParams",
    "BalanceLedgerResponse",
    "BalanceLedgerListResponse",
    "BalanceLedgerQueryParams",
    "ManualBalanceAdjustRequest",
    "RechargeRecordResponse",
    "RechargeRecordListResponse",
    "RechargeRecordQueryParams",
    "CreateRechargeRequest",
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
