"""AKX Crypto Payment Gateway - Payment Channel model.

Payment channels are used to manage wallet addresses for payment processing.
When an API request comes in, the system finds matching channels based on
amount limits and returns available addresses.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.chain import Chain
    from src.models.token import Token
    from src.models.user import User
    from src.models.wallet import Wallet


class ChannelStatus(str, Enum):
    """Payment channel status."""

    ACTIVE = "active"  # Channel is active and accepting payments
    PAUSED = "paused"  # Temporarily paused
    DISABLED = "disabled"  # Permanently disabled


class PaymentChannel(SQLModel, table=True):
    """Payment Channel model - manages wallet addresses for payment processing.

    A payment channel links a wallet address to specific payment limits and
    is used to route incoming payment requests to appropriate addresses.

    Attributes:
        id: Auto-increment primary key
        user_id: Owner merchant
        wallet_id: Associated wallet address
        token_id: Token type (e.g., USDT)
        chain_id: Blockchain network
        status: Channel status (active, paused, disabled)
        min_amount: Minimum payment amount
        max_amount: Maximum payment amount
        daily_limit: Maximum daily transaction amount
        balance_limit: Maximum balance threshold
        daily_used: Amount used today (reset daily)
        priority: Priority for channel selection (lower = higher priority)
        label: Optional description
    """

    __tablename__ = "payment_channels"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    wallet_id: int = Field(foreign_key="wallets.id", index=True)
    token_id: int = Field(foreign_key="tokens.id", index=True)
    chain_id: int = Field(foreign_key="chains.id", index=True)

    status: ChannelStatus = Field(default=ChannelStatus.ACTIVE)

    # Amount limits (stored as DECIMAL for precision)
    min_amount: Decimal = Field(default=Decimal("0"), max_digits=32, decimal_places=8)
    max_amount: Decimal = Field(default=Decimal("999999999"), max_digits=32, decimal_places=8)
    daily_limit: Decimal = Field(default=Decimal("999999999"), max_digits=32, decimal_places=8)
    balance_limit: Decimal = Field(default=Decimal("999999999"), max_digits=32, decimal_places=8)

    # Daily tracking
    daily_used: Decimal = Field(default=Decimal("0"), max_digits=32, decimal_places=8)
    last_reset_date: datetime | None = Field(default=None)

    # Channel priority (lower = higher priority)
    priority: int = Field(default=100)

    # Optional label
    label: str | None = Field(default=None, max_length=255)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: Optional["User"] = Relationship()
    wallet: Optional["Wallet"] = Relationship()
    token: Optional["Token"] = Relationship()
    chain: Optional["Chain"] = Relationship()

    def is_available_for_amount(self, amount: Decimal) -> bool:
        """Check if this channel can accept a payment of the given amount.

        Args:
            amount: The payment amount to check

        Returns:
            True if the channel can accept the payment
        """
        if self.status != ChannelStatus.ACTIVE:
            return False

        if amount < self.min_amount or amount > self.max_amount:
            return False

        # Check daily limit
        if self.daily_used + amount > self.daily_limit:
            return False

        return True

    def reset_daily_if_needed(self) -> bool:
        """Reset daily_used if it's a new day.

        Returns:
            True if reset was performed
        """
        today = datetime.utcnow().date()
        if self.last_reset_date is None or self.last_reset_date.date() < today:
            self.daily_used = Decimal("0")
            self.last_reset_date = datetime.utcnow()
            return True
        return False
