"""AKX Crypto Payment Gateway - Merchant model.

Stores merchant API keys for order creation and query.
"""

import secrets
from datetime import datetime

from sqlmodel import Field, SQLModel


class Merchant(SQLModel, table=True):
    """Merchant model - stores API keys for payment integration.

    Each merchant has two key pairs:
    - deposit_key: For creating and querying deposit orders
    - withdraw_key: For creating and querying withdrawal orders

    Attributes:
        id: Auto-increment primary key
        user_id: Associated user ID
        merchant_no: Unique merchant number (e.g., M1234567890)
        name: Merchant display name
        deposit_key: Secret key for deposit API (32 bytes hex)
        withdraw_key: Secret key for withdrawal API (32 bytes hex)
        callback_ip_whitelist: Comma-separated IPs allowed for callbacks
        is_active: Whether merchant is active
    """

    __tablename__ = "merchants"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", unique=True, index=True)
    merchant_no: str = Field(max_length=32, unique=True, index=True)
    name: str = Field(max_length=255)

    # API Keys (32 bytes hex = 64 characters)
    deposit_key: str = Field(max_length=64)
    withdraw_key: str = Field(max_length=64)

    # Security settings
    callback_ip_whitelist: str | None = Field(default=None, max_length=1024)
    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @staticmethod
    def generate_merchant_no() -> str:
        """Generate a unique merchant number."""
        import time

        timestamp = int(time.time() * 1000) % 10000000000
        random_suffix = secrets.randbelow(1000)
        return f"M{timestamp:010d}{random_suffix:03d}"

    @staticmethod
    def generate_api_key() -> str:
        """Generate a secure API key (32 bytes hex)."""
        return secrets.token_hex(32)
