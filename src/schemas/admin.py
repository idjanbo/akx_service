"""AKX Crypto Payment Gateway - Admin API schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from src.models.user import UserRole
from src.models.wallet import Chain, WalletType

# ============ User Management Schemas ============


class UserResponse(BaseModel):
    """Admin view of user."""

    id: int
    clerk_id: str
    email: str
    role: UserRole
    is_active: bool
    has_totp: bool  # Whether Google Auth is set up
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated user list."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class UpdateUserRequest(BaseModel):
    """Request to update user."""

    role: UserRole | None = None
    is_active: bool | None = None


# ============ System Wallet Schemas ============


class CreateSystemWalletRequest(BaseModel):
    """Request to create a system wallet (gas/cold)."""

    chain: Chain
    wallet_type: WalletType = Field(
        ..., description="Must be GAS or COLD"
    )
    label: str | None = None


class SystemWalletResponse(BaseModel):
    """System wallet response."""

    id: int
    chain: Chain
    address: str
    wallet_type: WalletType
    label: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportWalletRequest(BaseModel):
    """Request to import existing wallet with private key."""

    chain: Chain
    address: str = Field(..., min_length=20, max_length=100)
    private_key: str = Field(..., min_length=20)
    wallet_type: WalletType
    label: str | None = None


# ============ Fee Configuration Schemas ============


class FeeConfigResponse(BaseModel):
    """Fee configuration response."""

    id: int
    chain: Chain
    fee_percentage: Decimal
    fixed_fee: Decimal
    min_withdrawal: Decimal
    is_active: bool
    updated_at: datetime


class UpdateFeeConfigRequest(BaseModel):
    """Request to update fee configuration."""

    fee_percentage: Decimal | None = Field(default=None, ge=0, le=1)
    fixed_fee: Decimal | None = Field(default=None, ge=0)
    min_withdrawal: Decimal | None = Field(default=None, ge=0)


# ============ Dashboard Schemas ============


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics."""

    total_users: int
    active_merchants: int
    total_deposits_24h: Decimal
    total_withdrawals_24h: Decimal
    pending_orders: int
    success_rate_7d: Decimal  # Percentage


class ChainStatsResponse(BaseModel):
    """Per-chain statistics."""

    chain: Chain
    total_deposit_wallets: int
    total_deposit_volume: Decimal
    total_withdrawal_volume: Decimal
    cold_wallet_balance: Decimal
    gas_wallet_balance: Decimal


class OrderStatsResponse(BaseModel):
    """Order statistics for charts."""

    date: str  # YYYY-MM-DD
    deposits: int
    withdrawals: int
    deposit_volume: Decimal
    withdrawal_volume: Decimal


# ============ Audit Log Schemas ============


class AuditLogResponse(BaseModel):
    """Audit log entry."""

    id: int
    user_id: int
    action: str
    resource_type: str
    resource_id: str | None
    details: dict | None
    ip_address: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated audit logs."""

    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
