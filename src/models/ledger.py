"""AKX Crypto Payment Gateway - Ledger models.

This module defines transaction ledger models for tracking:
1. Address Transaction Records (地址历史记录) - On-chain transaction history per wallet address
2. Balance Ledger (积分明细) - User balance changes (freeze/unfreeze/income/expense/manual)
3. Recharge Records (充值记录) - Balance top-up records (subset of Balance Ledger)
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.order import Order
    from src.models.user import User
    from src.models.wallet import Wallet


# =============================================================================
# 1. Address Transaction Record (地址历史记录)
# =============================================================================


class AddressTransactionType(str, Enum):
    """Address transaction type."""

    INCOME = "income"  # 收入（充值到账）
    EXPENSE = "expense"  # 支出（提现转出）


class AddressTransaction(SQLModel, table=True):
    """Address transaction record - tracks on-chain transactions per wallet address.

    Records successful deposit/withdraw transactions associated with wallet addresses.
    Only records successful (completed) transactions.

    Attributes:
        id: Auto-increment primary key
        user_id: Owner of the wallet
        wallet_id: Associated wallet
        order_id: Related order (if any)

        tx_type: income (deposit) or expense (withdraw)
        token: Token code (e.g., 'USDT')
        chain: Chain code (e.g., 'tron')
        amount: Transaction amount
        address: Wallet address involved
        tx_hash: On-chain transaction hash

        created_at: Record creation time
    """

    __tablename__ = "address_transactions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    wallet_id: int | None = Field(default=None, foreign_key="wallets.id", index=True)
    order_id: int | None = Field(default=None, foreign_key="orders.id", index=True)

    tx_type: AddressTransactionType = Field(description="Transaction type: income/expense")
    token: str = Field(max_length=20, index=True, description="Token code (uppercase)")
    chain: str = Field(max_length=20, index=True, description="Chain code (lowercase)")
    amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Transaction amount",
    )
    address: str = Field(max_length=128, index=True, description="Wallet address")
    tx_hash: str | None = Field(
        default=None, max_length=128, index=True, description="On-chain transaction hash"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships
    user: Optional["User"] = Relationship()
    wallet: Optional["Wallet"] = Relationship()
    order: Optional["Order"] = Relationship()


# =============================================================================
# 2. Balance Ledger (积分明细)
# =============================================================================


class BalanceChangeType(str, Enum):
    """Balance change type (账变类型)."""

    # 收入类
    DEPOSIT_INCOME = "deposit_income"  # 充值收入（用户充值成功后，商户余额增加）
    RECHARGE = "recharge"  # 充值积分（后台充值/管理员手动添加）

    # 冻结/解冻
    FREEZE = "freeze"  # 冻结（提现申请时冻结金额）
    UNFREEZE = "unfreeze"  # 解冻（提现失败时解冻）

    # 支出类
    WITHDRAW_EXPENSE = "withdraw_expense"  # 提现支出（提现成功后扣除）
    WITHDRAW_FEE = "withdraw_fee"  # 提现手续费

    # 管理员操作
    MANUAL_ADD = "manual_add"  # 人工添加
    MANUAL_DEDUCT = "manual_deduct"  # 人工扣除

    # 其他
    REFUND = "refund"  # 退款
    ADJUSTMENT = "adjustment"  # 调账


class BalanceLedger(SQLModel, table=True):
    """Balance ledger - tracks all balance changes for users.

    Records every balance change including:
    - Deposit income (充值收入)
    - Recharge (积分充值)
    - Freeze/Unfreeze (冻结/解冻)
    - Withdraw expense (提现支出)
    - Manual add/deduct (人工添加/扣除)

    Attributes:
        id: Auto-increment primary key
        user_id: User whose balance changed
        order_id: Related order (if any)

        change_type: Type of balance change
        amount: Change amount (positive for add, negative for deduct)
        pre_balance: Balance before change
        post_balance: Balance after change
        frozen_amount: Frozen amount change (if freeze/unfreeze)
        pre_frozen: Frozen balance before change
        post_frozen: Frozen balance after change

        remark: Description/notes
        operator_id: Admin who performed manual operation (if any)

        created_at: Record creation time
    """

    __tablename__ = "balance_ledgers"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    order_id: int | None = Field(default=None, foreign_key="orders.id", index=True)

    change_type: BalanceChangeType = Field(index=True, description="Type of balance change")
    amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Change amount (positive=add, negative=deduct)",
    )
    pre_balance: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Balance before change",
    )
    post_balance: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Balance after change",
    )

    # Frozen amount tracking
    frozen_amount: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
        description="Frozen amount change",
    )
    pre_frozen: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
        description="Frozen balance before change",
    )
    post_frozen: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
        description="Frozen balance after change",
    )

    remark: str | None = Field(default=None, max_length=500, description="Notes/description")
    operator_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        description="Admin who performed operation",
    )

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships
    user: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[BalanceLedger.user_id]"}
    )
    order: Optional["Order"] = Relationship()
    operator: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[BalanceLedger.operator_id]"}
    )


# =============================================================================
# 3. Recharge Record (充值记录)
# =============================================================================


class RechargeStatus(str, Enum):
    """Recharge status."""

    PENDING = "pending"  # 待处理（在线充值待支付）
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class RechargeType(str, Enum):
    """Recharge type."""

    ONLINE = "online"  # 在线充值
    MANUAL = "manual"  # 人工充值
    DEDUCT = "deduct"  # 人工扣除


class RechargeRecord(SQLModel, table=True):
    """Recharge record - tracks balance top-up/deduction records.

    Records all recharge (积分充值) operations:
    - Online recharge (在线充值)
    - Manual add by admin (人工添加)
    - Manual deduct by admin (人工扣除)

    This is a detailed log for recharge operations, linked to BalanceLedger.

    Attributes:
        id: Auto-increment primary key
        user_id: User being recharged
        ledger_id: Related balance ledger entry

        recharge_type: online/manual/deduct
        status: pending/success/failed/cancelled
        amount: Recharge amount (positive for add, negative for deduct)
        payment_method: Payment method for online recharge

        remark: Description/notes
        operator_id: Admin who performed manual operation

        created_at: Record creation time
        completed_at: Completion time
    """

    __tablename__ = "recharge_records"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    ledger_id: int | None = Field(
        default=None, foreign_key="balance_ledgers.id", description="Related ledger entry"
    )

    recharge_type: RechargeType = Field(index=True, description="Recharge type")
    status: RechargeStatus = Field(default=RechargeStatus.PENDING, index=True)
    amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Recharge amount",
    )
    payment_method: str | None = Field(
        default=None, max_length=50, description="Payment method for online recharge"
    )

    remark: str | None = Field(default=None, max_length=500, description="Notes/description")
    operator_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        description="Admin who performed operation",
    )

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    completed_at: datetime | None = Field(default=None, description="Completion time")

    # Relationships
    user: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[RechargeRecord.user_id]"}
    )
    ledger: Optional["BalanceLedger"] = Relationship()
    operator: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[RechargeRecord.operator_id]"}
    )
