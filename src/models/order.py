"""AKX Crypto Payment Gateway - Order model."""

import secrets
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.user import User


class OrderType(str, Enum):
    """Order type."""

    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"


class OrderStatus(str, Enum):
    """Order status.

    State transitions:
    - Deposit: pending -> confirming -> success / expired
    - Withdraw: pending -> processing -> success / failed
    """

    PENDING = "pending"  # 等待支付（充值）/ 等待处理（提现）
    CONFIRMING = "confirming"  # 已检测到交易，等待确认
    PROCESSING = "processing"  # 提现处理中
    SUCCESS = "success"  # 已完成
    FAILED = "failed"  # 提现失败
    EXPIRED = "expired"  # 充值超时


class CallbackStatus(str, Enum):
    """Callback notification status."""

    PENDING = "pending"  # 待发送
    SUCCESS = "success"  # 发送成功
    FAILED = "failed"  # 发送失败（已达最大重试次数）


def generate_order_no(order_type: OrderType) -> str:
    """Generate a unique order number.

    Format: PREFIX + timestamp_ms + random_hex(8)
    - Deposit: DEP1702345678000ABC12345
    - Withdraw: WIT1702345678000ABC12345
    """
    timestamp = int(time.time() * 1000)
    random_suffix = secrets.token_hex(5).upper()
    prefix = "DEP" if order_type == OrderType.DEPOSIT else "WIT"
    return f"{prefix}{timestamp}{random_suffix}"


class Order(SQLModel, table=True):
    """Payment order model.

    Stores both deposit and withdrawal orders with their full lifecycle.

    Attributes:
        id: Auto-increment primary key
        order_no: System-generated unique order number
        out_trade_no: External trade number from merchant system
        order_type: deposit or withdraw
        merchant_id: Reference to merchant (user)

        # Payment details
        token: Token code (e.g., 'USDT')
        chain: Chain code (e.g., 'tron')
        amount: Order amount
        fee: Transaction fee
        net_amount: Amount after fee (amount - fee for withdraw, amount for deposit)

        # Address info
        wallet_address: Deposit address or source address for withdraw
        to_address: Destination address (withdraw only)

        # Blockchain info
        tx_hash: Transaction hash on blockchain
        confirmations: Current confirmation count

        # Callback
        callback_url: Merchant callback URL
        callback_status: Callback delivery status
        callback_retry_count: Number of callback retries
        last_callback_at: Last callback attempt time

        # Extra
        extra_data: Merchant extra data (returned in callback)
        remark: Internal remarks

        # Timestamps
        expire_time: Order expiration time (deposit only)
        completed_at: Order completion time
        created_at: Order creation time
        updated_at: Last update time
    """

    __tablename__ = "orders"

    id: int | None = Field(default=None, primary_key=True)
    order_no: str = Field(
        max_length=64,
        unique=True,
        index=True,
        description="System order number (DEP/WIT prefix)",
    )
    out_trade_no: str = Field(
        max_length=64,
        index=True,
        description="External trade number from merchant",
    )
    order_type: OrderType = Field(description="Order type: deposit or withdraw")
    merchant_id: int = Field(foreign_key="users.id", index=True)

    # Payment details
    token: str = Field(max_length=20, index=True, description="Token code (uppercase)")
    chain: str = Field(max_length=20, index=True, description="Chain code (lowercase)")
    amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Order amount",
    )
    fee: Decimal = Field(
        default=Decimal("0"),
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False, default=Decimal("0")),
        description="Transaction fee",
    )
    net_amount: Decimal = Field(
        sa_column=sa.Column(sa.DECIMAL(32, 8), nullable=False),
        description="Net amount after fee",
    )

    # Address info
    wallet_address: str | None = Field(
        default=None,
        max_length=200,
        description="Deposit address or source for withdraw",
    )
    to_address: str | None = Field(
        default=None,
        max_length=200,
        description="Destination address (withdraw only)",
    )

    # Blockchain info
    tx_hash: str | None = Field(
        default=None,
        max_length=200,
        index=True,
        description="Transaction hash",
    )
    confirmations: int = Field(default=0, description="Current confirmations")

    # Status
    status: OrderStatus = Field(
        default=OrderStatus.PENDING,
        index=True,
        description="Order status",
    )

    # Callback
    callback_url: str = Field(max_length=500, description="Merchant callback URL")
    callback_status: CallbackStatus = Field(
        default=CallbackStatus.PENDING,
        description="Callback delivery status",
    )
    callback_retry_count: int = Field(
        default=0,
        description="Callback retry count",
    )
    last_callback_at: datetime | None = Field(
        default=None,
        description="Last callback attempt time",
    )

    # Extra data
    extra_data: str | None = Field(
        default=None,
        max_length=1024,
        description="Merchant extra data",
    )
    remark: str | None = Field(
        default=None,
        max_length=500,
        description="Internal remarks",
    )

    # Timestamps
    expire_time: datetime | None = Field(
        default=None,
        description="Order expiration time",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Order completion time",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships - use selectin to avoid async lazy-load issues
    merchant: Optional["User"] = Relationship(sa_relationship_kwargs={"lazy": "selectin"})

    # Composite unique constraint for merchant + out_trade_no
    __table_args__ = (
        sa.UniqueConstraint("merchant_id", "out_trade_no", name="uq_merchant_out_trade_no"),
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "order_no": "DEP1702345678000ABC12345",
                "out_trade_no": "ORDER20231212001",
                "order_type": "deposit",
                "token": "USDT",
                "chain": "tron",
                "amount": "100.00",
                "fee": "0.00",
                "net_amount": "100.00",
                "wallet_address": "TXyz...abc",
                "status": "pending",
                "callback_url": "https://example.com/callback",
            }
        }
