"""AKX Crypto Payment Gateway - Webhook delivery model."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column
from sqlalchemy.dialects.mysql import JSON
from sqlmodel import Field, SQLModel


class WebhookEventType(str, Enum):
    """Webhook event types."""

    ORDER_CREATED = "order.created"
    ORDER_CONFIRMING = "order.confirming"
    ORDER_COMPLETED = "order.completed"
    ORDER_FAILED = "order.failed"
    ORDER_EXPIRED = "order.expired"
    DEPOSIT_DETECTED = "deposit.detected"
    WITHDRAWAL_BROADCAST = "withdrawal.broadcast"


class WebhookDelivery(SQLModel, table=True):
    """Record of webhook delivery attempts.

    Tracks each attempt to deliver a webhook event to merchant.
    Used for debugging and retry logic.

    The callback_url is stored in the order's chain_metadata,
    not in a separate WebhookConfig table.

    Attributes:
        id: Auto-increment primary key
        order_id: Related order ID
        event_type: Type of event
        event_id: Unique event identifier
        url: Target callback URL
        payload: JSON payload sent
        response_status: HTTP response status code
        response_body: Response body (truncated)
        attempts: Number of delivery attempts
        success: Whether delivery succeeded
    """

    __tablename__ = "webhook_deliveries"

    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orders.id", index=True)
    event_type: str = Field(max_length=64, index=True)
    event_id: str = Field(max_length=64, unique=True, index=True)
    url: str = Field(max_length=512)
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    response_status: int | None = Field(default=None)
    response_body: str | None = Field(default=None, max_length=2000)
    attempts: int = Field(default=0)
    success: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    last_attempt_at: datetime | None = Field(default=None)
