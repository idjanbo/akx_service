"""AKX Crypto Payment Gateway - Exchange Rate models.

This module defines:
- ExchangeRateSource: System-level exchange rate source configuration (admin only)
- ExchangeRate: Merchant-level exchange rate configuration
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.user import User


class ExchangeRateMode(str, Enum):
    """Merchant exchange rate mode."""

    SYSTEM = "system"  # 使用系统汇率
    ADJUSTMENT = "adjustment"  # 基于系统汇率浮动
    CUSTOM = "custom"  # 完全自定义汇率


class ExchangeRateSource(SQLModel, table=True):
    """System exchange rate source configuration.

    Managed by super admin. Defines where to fetch exchange rates from.

    Attributes:
        base_currency: Base currency (crypto), e.g., 'USDT'
        quote_currency: Quote currency (fiat), e.g., 'CNY', 'USD'
        source_name: Source identifier, e.g., 'okx_c2c', 'binance', 'manual'
        source_url: API URL to fetch rate from (null for manual)
        response_path: JSON path to extract rate, e.g., 'data.buy[0].price'
        sync_interval: Sync interval in seconds (0 for manual)
        current_rate: Latest synced rate
        last_synced_at: Last successful sync time
        is_enabled: Whether this source is active
    """

    __tablename__ = "exchange_rate_sources"

    id: int | None = Field(default=None, primary_key=True)
    base_currency: str = Field(
        max_length=20,
        index=True,
        description="Base currency (crypto): USDT, USDC",
    )
    quote_currency: str = Field(
        max_length=20,
        index=True,
        description="Quote currency (fiat): CNY, USD",
    )
    source_name: str = Field(
        max_length=50,
        description="Source name: okx_c2c, binance, manual",
    )
    source_url: str | None = Field(
        default=None,
        max_length=500,
        description="API URL for fetching rate",
    )
    response_path: str | None = Field(
        default=None,
        max_length=200,
        description="JSON path to rate value: data.buy[0].price",
    )
    sync_interval: int = Field(
        default=60,
        description="Sync interval in seconds (0 = manual only)",
    )
    current_rate: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.DECIMAL(20, 8), nullable=True),
        description="Current exchange rate",
    )
    last_synced_at: datetime | None = Field(
        default=None,
        description="Last sync timestamp",
    )
    is_enabled: bool = Field(default=True, description="Whether source is active")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"onupdate": datetime.utcnow},
        description="Last update timestamp",
    )

    # Unique constraint: one source per currency pair
    __table_args__ = (
        sa.UniqueConstraint("base_currency", "quote_currency", name="uq_source_currency_pair"),
    )


class ExchangeRate(SQLModel, table=True):
    """Merchant exchange rate configuration.

    Each merchant can customize their exchange rate behavior.

    Attributes:
        user_id: Merchant ID (foreign key to users)
        base_currency: Base currency (crypto): USDT
        quote_currency: Quote currency (fiat): CNY, USD
        mode: Rate mode: system / adjustment / custom
        rate: Custom rate (used when mode='custom')
        adjustment: Adjustment percentage (used when mode='adjustment')
                    e.g., +0.03 = 3% markup, -0.01 = 1% discount
        is_enabled: Whether this config is active
    """

    __tablename__ = "exchange_rates"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        foreign_key="users.id",
        index=True,
        description="Merchant ID",
    )
    base_currency: str = Field(
        max_length=20,
        index=True,
        description="Base currency (crypto): USDT",
    )
    quote_currency: str = Field(
        max_length=20,
        index=True,
        description="Quote currency (fiat): CNY, USD",
    )
    mode: ExchangeRateMode = Field(
        default=ExchangeRateMode.SYSTEM,
        description="Rate mode: system / adjustment / custom",
    )
    rate: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.DECIMAL(20, 8), nullable=True),
        description="Custom rate (for mode='custom')",
    )
    adjustment: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(10, 6), nullable=False, default=Decimal("0")),
        description="Adjustment percentage: +0.03 = 3% markup",
    )
    is_enabled: bool = Field(default=True, description="Whether config is active")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column_kwargs={"onupdate": datetime.utcnow},
        description="Last update timestamp",
    )

    # Relationship
    user: Optional["User"] = Relationship(back_populates="exchange_rates")

    # Unique constraint: one config per merchant + currency pair
    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "base_currency", "quote_currency", name="uq_merchant_currency_pair"
        ),
    )
