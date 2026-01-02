"""Schemas module - Pydantic DTOs for request/response."""

from src.schemas.admin import (
    AuditLogListResponse,
    AuditLogResponse,
    ChainStatsResponse,
    CreateSystemWalletRequest,
    DashboardStatsResponse,
    FeeConfigResponse,
    ImportWalletRequest,
    OrderStatsResponse,
    SystemWalletResponse,
    UpdateFeeConfigRequest,
    UpdateUserRequest,
    UserListResponse,
    UserResponse,
)
from src.schemas.merchant import (
    BalanceResponse,
    ChainBalanceResponse,
    CreateWalletRequest,
    CreateWithdrawalRequest,
    DepositAddressRequest,
    DepositAddressResponse,
    ErrorResponse,
    OrderListResponse,
    OrderResponse,
    SuccessResponse,
    WalletResponse,
)

__all__ = [
    # Merchant
    "WalletResponse",
    "CreateWalletRequest",
    "DepositAddressRequest",
    "DepositAddressResponse",
    "CreateWithdrawalRequest",
    "OrderResponse",
    "OrderListResponse",
    "BalanceResponse",
    "ChainBalanceResponse",
    "SuccessResponse",
    "ErrorResponse",
    # Admin
    "UserResponse",
    "UserListResponse",
    "UpdateUserRequest",
    "SystemWalletResponse",
    "CreateSystemWalletRequest",
    "ImportWalletRequest",
    "FeeConfigResponse",
    "UpdateFeeConfigRequest",
    "DashboardStatsResponse",
    "ChainStatsResponse",
    "OrderStatsResponse",
    "AuditLogResponse",
    "AuditLogListResponse",
]
