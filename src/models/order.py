"""AKX Crypto Payment Gateway - Order model."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.mysql import JSON
from sqlmodel import Field, SQLModel


class OrderType(str, Enum):
    """Order direction."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class OrderStatus(str, Enum):
    """Order lifecycle states.

    State Machine:
        DEPOSIT:    PENDING -> CONFIRMING -> SUCCESS / EXPIRED
        WITHDRAWAL: PENDING -> PROCESSING -> SUCCESS / FAILED
    """

    PENDING = "pending"  # Awaiting action
    CONFIRMING = "confirming"  # Deposit detected, awaiting confirmations
    PROCESSING = "processing"  # Withdrawal being broadcast
    SUCCESS = "success"  # Completed successfully
    FAILED = "failed"  # Withdrawal failed
    EXPIRED = "expired"  # Deposit timeout


class Order(SQLModel, table=True):
    """Order model - deposit and withdrawal records.

    Money fields use DECIMAL(32, 8) for precision.
    Chain metadata stored in JSON field.

    Payment method is uniquely identified by: chain + token

    Attributes:
        id: Auto-increment primary key
        order_no: System-generated order number (indexed, unique)
        merchant_ref: Merchant's external reference ID
        user_id: Owner merchant
        order_type: deposit or withdrawal
        chain: Blockchain network (tron, ethereum, solana)
        token: Token/currency (usdt, usdc, eth, trx, sol)
        amount: Transaction amount in token
        fee: Calculated fee in token
        net_amount: amount - fee (for withdrawals) or amount (for deposits)
        status: Current order state
        wallet_address: Target address
        tx_hash: Blockchain transaction hash (nullable until broadcast)
        confirmations: Current confirmation count
        chain_metadata: Additional chain-specific data (JSON)
    """

    __tablename__ = "orders"

    id: int | None = Field(default=None, primary_key=True)
    order_no: str = Field(max_length=64, unique=True, index=True)
    merchant_ref: str | None = Field(default=None, max_length=255, index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    order_type: OrderType = Field(index=True)
    chain: str = Field(max_length=32, index=True)
    token: str = Field(max_length=32, default="usdt", index=True)  # Token/currency

    # Money fields - DECIMAL(32, 8)
    amount: Decimal = Field(default=Decimal("0"), max_digits=32, decimal_places=8)
    fee: Decimal = Field(default=Decimal("0"), max_digits=32, decimal_places=8)
    net_amount: Decimal = Field(default=Decimal("0"), max_digits=32, decimal_places=8)

    status: OrderStatus = Field(default=OrderStatus.PENDING, index=True)
    wallet_address: str = Field(max_length=255)
    tx_hash: str | None = Field(default=None, max_length=255, index=True)
    confirmations: int = Field(default=0)

    # Chain-specific metadata (block number, gas used, etc.)
    chain_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = Field(default=None)
