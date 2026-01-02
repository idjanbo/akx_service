"""AKX Crypto Payment Gateway - Transaction ledger model."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, SQLModel


class TransactionType(str, Enum):
    """Ledger entry types."""

    DEPOSIT = "deposit"  # Incoming deposit credited
    WITHDRAWAL = "withdrawal"  # Outgoing withdrawal debited
    FEE = "fee"  # Fee deducted
    SWEEP = "sweep"  # Funds swept to cold wallet
    ADJUSTMENT = "adjustment"  # Manual admin adjustment


class TransactionDirection(str, Enum):
    """Fund flow direction."""

    CREDIT = "credit"  # Increase balance
    DEBIT = "debit"  # Decrease balance


class Transaction(SQLModel, table=True):
    """Transaction ledger - immutable record of all balance changes.

    Every balance change MUST create a ledger entry with:
    - pre_balance: Balance before this transaction
    - change_amount: Amount added/subtracted
    - post_balance: Balance after (must equal pre + change for credits, pre - change for debits)

    This ensures full auditability and balance reconciliation.

    Attributes:
        id: Auto-increment primary key
        user_id: Merchant whose balance changed
        wallet_id: Related wallet (if applicable)
        order_id: Related order (if applicable)
        tx_type: Type of transaction
        direction: Credit or debit
        amount: Absolute change amount
        pre_balance: Balance before transaction
        post_balance: Balance after transaction
        description: Human-readable description
    """

    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    wallet_id: int | None = Field(default=None, foreign_key="wallets.id", index=True)
    order_id: int | None = Field(default=None, foreign_key="orders.id", index=True)

    tx_type: TransactionType = Field(index=True)
    direction: TransactionDirection

    # Money fields - DECIMAL(32, 8)
    amount: Decimal = Field(max_digits=32, decimal_places=8)
    pre_balance: Decimal = Field(max_digits=32, decimal_places=8)
    post_balance: Decimal = Field(max_digits=32, decimal_places=8)

    description: str | None = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
