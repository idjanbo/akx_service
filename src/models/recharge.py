"""AKX Crypto Payment Gateway - Recharge models.

This module defines models for merchant online recharge (商户在线充值) system:
1. RechargeAddress - Merchant-assigned recharge addresses from address pool
2. RechargeOrder - Recharge orders tracking merchant balance top-up requests
3. CollectTask - Fund collection tasks from recharge addresses to hot wallet

Note: This is different from Orders.deposit which handles merchant's customer deposits.
- Recharge: Merchant tops up their platform balance (商户向平台充值)
- Deposit Order: Merchant's customer pays merchant (商户客户向商户充值)
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.chain import Chain
    from src.models.token import Token
    from src.models.user import User
    from src.models.wallet import Wallet


# =============================================================================
# 1. Recharge Address (商户充值地址)
# =============================================================================


class RechargeAddressStatus(str, Enum):
    """Recharge address status."""

    AVAILABLE = "available"  # 可用（地址池中未分配）
    ASSIGNED = "assigned"  # 已分配给商户
    LOCKED = "locked"  # 锁定（正在处理中）
    DISABLED = "disabled"  # 禁用


class RechargeAddress(SQLModel, table=True):
    """Recharge address - tracks address pool and merchant assignments.

    Each merchant gets a unique recharge address for each chain+token combination.
    Addresses are pre-generated and assigned on-demand.

    Attributes:
        id: Auto-increment primary key
        wallet_id: Reference to Wallet (stores address and private key)
        chain_id: Blockchain network
        token_id: Token (e.g., USDT)
        user_id: Assigned merchant user (null if available in pool)

        status: Address status (available/assigned/locked/disabled)
        total_recharged: Total amount recharged to this address
        last_recharge_at: Last recharge time
        assigned_at: When the address was assigned to merchant

        created_at: Record creation time
        updated_at: Last update time
    """

    __tablename__ = "recharge_addresses"

    id: int | None = Field(default=None, primary_key=True)
    wallet_id: int = Field(foreign_key="wallets.id", index=True, unique=True)
    chain_id: int = Field(foreign_key="chains.id", index=True)
    token_id: int = Field(foreign_key="tokens.id", index=True)
    user_id: int | None = Field(default=None, foreign_key="users.id", index=True)

    status: RechargeAddressStatus = Field(
        default=RechargeAddressStatus.AVAILABLE,
        index=True,
    )
    total_recharged: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
    )
    last_recharge_at: datetime | None = Field(default=None)
    assigned_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships - use selectin to avoid async lazy-load issues
    wallet: Optional["Wallet"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    chain: Optional["Chain"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    token: Optional["Token"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    user: Optional["User"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})

    # Composite index for user+chain+token lookup
    __table_args__ = (
        sa.Index("ix_recharge_addresses_user_chain_token", "user_id", "chain_id", "token_id"),
        sa.Index("ix_recharge_addresses_status_chain", "status", "chain_id"),
    )


# =============================================================================
# 2. Recharge Order (商户充值订单)
# =============================================================================


class RechargeOrderStatus(str, Enum):
    """Recharge order status."""

    PENDING = "pending"  # 待支付（等待商户转账）
    DETECTED = "detected"  # 已检测到（链上检测到交易，待确认）
    CONFIRMING = "confirming"  # 确认中（等待足够确认数）
    SUCCESS = "success"  # 成功（已到账）
    EXPIRED = "expired"  # 已过期（超时未支付）
    FAILED = "failed"  # 失败


class RechargeOrder(SQLModel, table=True):
    """Recharge order - tracks merchant balance top-up requests.

    When a merchant initiates online recharge:
    1. System assigns a recharge address to merchant
    2. Creates a recharge order with expected amount
    3. Monitors blockchain for incoming transactions
    4. On detection, updates status and credits merchant balance

    Attributes:
        id: Auto-increment primary key
        order_no: Unique order number (for display)
        user_id: Merchant user making the recharge
        recharge_address_id: Assigned recharge address

        chain_id: Blockchain network
        token_id: Token (e.g., USDT)
        expected_amount: Expected recharge amount
        actual_amount: Actual received amount (may differ)

        status: Order status
        tx_hash: On-chain transaction hash (when detected)
        confirmations: Current confirmation count
        required_confirmations: Required confirmations for finality

        expires_at: Order expiration time
        detected_at: When transaction was detected on-chain
        confirmed_at: When transaction was fully confirmed
        credited_at: When merchant balance was credited

        created_at: Order creation time
        updated_at: Last update time
    """

    __tablename__ = "recharge_orders"

    id: int | None = Field(default=None, primary_key=True)
    order_no: str = Field(max_length=32, unique=True, index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    recharge_address_id: int = Field(foreign_key="recharge_addresses.id", index=True)

    chain_id: int = Field(foreign_key="chains.id", index=True)
    token_id: int = Field(foreign_key="tokens.id", index=True)
    expected_amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
    )
    actual_amount: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=True),
    )

    status: RechargeOrderStatus = Field(
        default=RechargeOrderStatus.PENDING,
        index=True,
    )
    tx_hash: str | None = Field(default=None, max_length=128, index=True)
    confirmations: int = Field(default=0)
    required_confirmations: int = Field(default=19)  # TRON requires 19

    expires_at: datetime = Field(index=True)
    detected_at: datetime | None = Field(default=None)
    confirmed_at: datetime | None = Field(default=None)
    credited_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships - use selectin to avoid async lazy-load issues
    user: Optional["User"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    recharge_address: Optional["RechargeAddress"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    chain: Optional["Chain"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    token: Optional["Token"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})

    # Indexes
    __table_args__ = (
        sa.Index("ix_recharge_orders_user_status", "user_id", "status"),
        sa.Index("ix_recharge_orders_status_expires", "status", "expires_at"),
    )


# =============================================================================
# 3. Collect Task (归集任务)
# =============================================================================


class CollectTaskStatus(str, Enum):
    """Collect task status."""

    PENDING = "pending"  # 待执行
    PROCESSING = "processing"  # 执行中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过（余额不足阈值等）


class CollectTask(SQLModel, table=True):
    """Collect task - tracks fund collection from recharge addresses to hot wallet.

    After merchant recharges, funds need to be collected to hot wallet for:
    - Centralized management
    - Easier withdrawal processing
    - Security (hot wallet has rate limits)

    Attributes:
        id: Auto-increment primary key
        recharge_address_id: Source address
        hot_wallet_id: Destination hot wallet

        chain_id: Blockchain network
        token_id: Token being collected
        amount: Amount to collect

        status: Task status
        tx_hash: Collection transaction hash
        gas_used: Actual gas used
        gas_price: Gas price at execution

        error_message: Error message if failed
        retry_count: Number of retries
        max_retries: Maximum retry attempts

        scheduled_at: When to execute (for batch scheduling)
        executed_at: When actually executed
        completed_at: When completed (success or final failure)

        created_at: Task creation time
    """

    __tablename__ = "collect_tasks"

    id: int | None = Field(default=None, primary_key=True)
    recharge_address_id: int = Field(foreign_key="recharge_addresses.id", index=True)
    hot_wallet_id: int = Field(foreign_key="wallets.id", index=True)

    chain_id: int = Field(foreign_key="chains.id", index=True)
    token_id: int = Field(foreign_key="tokens.id", index=True)
    amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
    )

    status: CollectTaskStatus = Field(
        default=CollectTaskStatus.PENDING,
        index=True,
    )
    tx_hash: str | None = Field(default=None, max_length=128, index=True)
    gas_used: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=True),
    )
    gas_price: Decimal | None = Field(
        default=None,
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=True),
    )

    error_message: str | None = Field(default=None, max_length=500)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)

    scheduled_at: datetime | None = Field(default=None, index=True)
    executed_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # Relationships - use selectin to avoid async lazy-load issues
    recharge_address: Optional["RechargeAddress"] = Relationship(
        sa_relationship_kwargs={"lazy": "selectin"}
    )
    hot_wallet: Optional["Wallet"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    chain: Optional["Chain"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})
    token: Optional["Token"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})

    # Indexes
    __table_args__ = (sa.Index("ix_collect_tasks_status_scheduled", "status", "scheduled_at"),)


# =============================================================================
# Helper Functions
# =============================================================================


def generate_recharge_order_no() -> str:
    """Generate unique recharge order number.

    Format: R + timestamp(10) + random(6)
    Example: R17042567891234567
    """
    import secrets
    import time

    timestamp = int(time.time())
    random_part = secrets.token_hex(3).upper()  # 6 hex chars
    return f"R{timestamp}{random_part}"
