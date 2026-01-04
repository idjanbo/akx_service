"""AKX Crypto Payment Gateway - Fee configuration schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class FeeConfigBase(BaseModel):
    """Base fee configuration schema."""

    name: str = Field(..., max_length=100, description="Configuration name")
    deposit_fee_percent: Decimal = Field(
        ...,
        ge=0,
        le=100,
        decimal_places=4,
        description="Deposit fee percentage (0-100)",
    )
    withdraw_fee_fixed: Decimal = Field(
        ...,
        ge=0,
        decimal_places=8,
        description="Fixed withdrawal fee in USDT",
    )
    withdraw_fee_percent: Decimal = Field(
        ...,
        ge=0,
        le=100,
        decimal_places=4,
        description="Withdrawal fee percentage (0-100)",
    )
    is_default: bool = Field(default=False, description="Whether this is the default config")


class FeeConfigCreate(FeeConfigBase):
    """Schema for creating fee configuration."""

    pass


class FeeConfigUpdate(BaseModel):
    """Schema for updating fee configuration."""

    name: str | None = Field(None, max_length=100)
    deposit_fee_percent: Decimal | None = Field(None, ge=0, le=100, decimal_places=4)
    withdraw_fee_fixed: Decimal | None = Field(None, ge=0, decimal_places=8)
    withdraw_fee_percent: Decimal | None = Field(None, ge=0, le=100, decimal_places=4)
    is_default: bool | None = None


class FeeConfigResponse(FeeConfigBase):
    """Schema for fee configuration response."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class FeeCalculationRequest(BaseModel):
    """Schema for fee calculation request."""

    amount: Decimal = Field(..., gt=0, decimal_places=8, description="Transaction amount")
    transaction_type: str = Field(..., pattern="^(deposit|withdraw)$")


class FeeCalculationResponse(BaseModel):
    """Schema for fee calculation response."""

    amount: Decimal
    fee: Decimal
    total: Decimal
    fee_config_name: str
