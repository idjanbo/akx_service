"""AKX Crypto Payment Gateway - Fee configuration model."""

from datetime import datetime
from decimal import Decimal

from sqlmodel import Field, SQLModel

from src.models.wallet import Chain


class FeeConfig(SQLModel, table=True):
    """Fee configuration per chain.

    Stores dynamic fee settings that can be adjusted by admins.
    Each chain has its own fee structure.

    Attributes:
        id: Auto-increment primary key
        chain: Blockchain network
        fee_percentage: Percentage fee (0.01 = 1%)
        fixed_fee: Fixed fee per transaction in USDT
        min_withdrawal: Minimum withdrawal amount
        min_deposit: Minimum deposit amount
        is_active: Whether this chain is enabled
    """

    __tablename__ = "fee_configs"

    id: int | None = Field(default=None, primary_key=True)
    chain: Chain = Field(unique=True, index=True)

    # Fee structure
    fee_percentage: Decimal = Field(
        default=Decimal("0.01"),
        max_digits=10,
        decimal_places=6,
        description="Fee percentage (0.01 = 1%)",
    )
    fixed_fee: Decimal = Field(
        default=Decimal("1.0"),
        max_digits=32,
        decimal_places=8,
        description="Fixed fee in USDT",
    )

    # Limits
    min_withdrawal: Decimal = Field(
        default=Decimal("10.0"),
        max_digits=32,
        decimal_places=8,
    )
    max_withdrawal: Decimal = Field(
        default=Decimal("100000.0"),
        max_digits=32,
        decimal_places=8,
    )
    min_deposit: Decimal = Field(
        default=Decimal("1.0"),
        max_digits=32,
        decimal_places=8,
    )

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
