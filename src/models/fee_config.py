"""AKX Crypto Payment Gateway - Fee configuration model."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.user import User


class FeeConfig(SQLModel, table=True):
    """Fee configuration for merchant transactions.

    Fee calculation:
    - Deposit fee: amount * deposit_fee_percent / 100
    - Withdrawal fee: withdraw_fee_fixed + (amount * withdraw_fee_percent / 100)

    Attributes:
        id: Primary key
        name: Configuration name (e.g., "Standard", "VIP", "Premium")
        deposit_fee_percent: Percentage fee for deposits (0-100)
        withdraw_fee_fixed: Fixed fee per withdrawal (USDT)
        withdraw_fee_percent: Percentage fee for withdrawals (0-100)
        is_default: Whether this is the default config for new merchants
    """

    __tablename__ = "fee_configs"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, unique=True)
    deposit_fee_percent: Decimal = Field(
        default=Decimal("1.0"),
        sa_column=sa.Column(sa.DECIMAL(10, 4), nullable=False, default=Decimal("1.0")),
    )
    withdraw_fee_fixed: Decimal = Field(
        default=Decimal("1.0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("1.0")),
    )
    withdraw_fee_percent: Decimal = Field(
        default=Decimal("0.5"),
        sa_column=sa.Column(sa.DECIMAL(10, 4), nullable=False, default=Decimal("0.5")),
    )
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    users: list["User"] = Relationship(back_populates="fee_config")

    def calculate_deposit_fee(self, amount: Decimal) -> Decimal:
        """Calculate deposit fee for given amount."""
        return amount * self.deposit_fee_percent / Decimal("100")

    def calculate_withdraw_fee(self, amount: Decimal) -> Decimal:
        """Calculate withdrawal fee for given amount."""
        return self.withdraw_fee_fixed + (amount * self.withdraw_fee_percent / Decimal("100"))
