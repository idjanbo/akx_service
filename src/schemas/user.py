"""User management schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field, PlainSerializer

from src.models.user import UserRole

# 自定义 Decimal 序列化器，避免科学计数法
DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda x: f"{x:.8f}".rstrip("0").rstrip(".") if x else "0", return_type=str),
]


# Generic pagination response
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class FeeConfigBrief(BaseModel):
    """Brief fee config info for user response."""

    id: int
    name: str

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """User response schema."""

    id: int
    clerk_id: str
    email: str
    username: str | None = None
    role: UserRole
    is_active: bool

    # TOTP (Google Authenticator) 绑定状态
    totp_enabled: bool = False

    # Support user fields (子账号)
    parent_id: int | None = None  # Parent merchant ID (for support users)
    permissions: list[str] = []  # Granted permissions (for support users)

    # Merchant fields (visible when role is merchant)
    balance: DecimalStr
    credit_limit: DecimalStr
    deposit_key: str | None = None
    withdraw_key: str | None = None
    fee_config: FeeConfigBrief | None = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListParams(BaseModel):
    """Query parameters for user list."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    search: str | None = Field(default=None, description="Search by email")
    role: UserRole | None = Field(default=None, description="Filter by role")
    is_active: bool | None = Field(default=None, description="Filter by status")


class UpdateUserRoleRequest(BaseModel):
    """Update user role request."""

    role: UserRole


class UpdateUserStatusRequest(BaseModel):
    """Update user status request."""

    is_active: bool


class UpdateUserBalanceRequest(BaseModel):
    """Update user balance request."""

    balance: Decimal


class UpdateUserCreditLimitRequest(BaseModel):
    """Update user credit limit request."""

    credit_limit: Decimal


class UpdateUserFeeConfigRequest(BaseModel):
    """Update user fee config request."""

    fee_config_id: int | None


class ResetKeyResponse(BaseModel):
    """Response after resetting API key."""

    key: str


class ResetGoogleSecretResponse(BaseModel):
    """Response after resetting Google authenticator."""

    secret: str
    qr_uri: str  # otpauth:// URI for QR code


# ============ Support User Management Schemas ============


class AddSupportUserRequest(BaseModel):
    """Request to add a user as support."""

    user_id: int = Field(description="User ID to add as support")
    permissions: list[str] = Field(
        default=[],
        description="List of permission strings (e.g., 'view_wallets', 'view_orders')",
    )


class UpdateSupportPermissionsRequest(BaseModel):
    """Request to update support user permissions."""

    permissions: list[str] = Field(
        description="New list of permission strings",
    )


class SupportUserResponse(BaseModel):
    """Response for support user."""

    id: int
    email: str
    username: str | None = None
    is_active: bool
    permissions: list[str] = []
    created_at: datetime

    class Config:
        from_attributes = True


class SearchUserResponse(BaseModel):
    """Response for user search (minimal info)."""

    id: int
    email: str
    username: str | None = None

    class Config:
        from_attributes = True


class CurrentUserResponse(BaseModel):
    """Response for /auth/me endpoint."""

    id: int
    clerk_id: str
    email: str
    role: str  # String value for frontend
    is_active: bool
    totp_enabled: bool
    created_at: str  # ISO format
    updated_at: str  # ISO format
