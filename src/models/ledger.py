"""AKX Crypto Payment Gateway - Ledger models.

This module defines the Balance Ledger model for tracking all user balance changes.
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


# =============================================================================
# Balance Ledger (积分明细) - 唯一的余额变动记录表
# =============================================================================


class BalanceChangeType(str, Enum):
    """Balance change type (账变类型)."""

    # 充值类
    ONLINE_RECHARGE = "online_recharge"  # 在线充值
    MANUAL_RECHARGE = "manual_recharge"  # 人工充值

    # 扣款类
    MANUAL_DEDUCT = "manual_deduct"  # 人工扣款

    # 手续费类
    FEE_FREEZE = "fee_freeze"  # 手续费冻结
    FEE_UNFREEZE = "fee_unfreeze"  # 手续费解冻
    FEE_SETTLE = "fee_settle"  # 手续费结算

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
