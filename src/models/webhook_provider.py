"""AKX Crypto Payment Gateway - WebhookProvider model."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, Text
from sqlmodel import Field, Relationship, SQLModel


class WebhookProviderType(str, Enum):
    """Webhook provider types."""

    tatum = "tatum"  # Multi-chain including TRON
    alchemy = "alchemy"  # Ethereum, Polygon, Arbitrum, etc.
    helius = "helius"  # Solana
    quicknode = "quicknode"  # Multi-chain
    moralis = "moralis"  # Multi-chain
    getblock = "getblock"  # Multi-chain including TRON
    custom = "custom"  # Custom webhook


class WebhookProvider(SQLModel, table=True):
    """Webhook service provider configuration.

    Manages third-party webhook service providers for receiving
    blockchain transaction notifications.

    Attributes:
        id: Auto-increment primary key
        name: Provider display name (e.g., 'TronGrid Production')
        provider_type: Type of provider (trongrid, alchemy, helius, etc.)
        api_key: API key for the provider
        api_secret: API secret (encrypted)
        webhook_secret: Webhook signature verification secret (encrypted)
        webhook_url: Our callback URL registered with provider
        is_enabled: Whether this provider is currently active
        remark: Internal notes
        created_at: Record creation timestamp
        updated_at: Last modification timestamp
    """

    __tablename__ = "webhook_providers"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, description="Provider display name")
    provider_type: WebhookProviderType = Field(
        description="Provider type (trongrid, alchemy, helius, etc.)"
    )

    # Credentials (encrypted in database)
    api_key: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="API key (encrypted)",
    )
    api_secret: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="API secret (encrypted)",
    )
    webhook_secret: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Webhook signature secret (encrypted)",
    )

    # Webhook configuration
    webhook_url: str | None = Field(
        default=None,
        max_length=500,
        description="Callback URL registered with provider",
    )
    webhook_id: str | None = Field(
        default=None,
        max_length=100,
        description="Webhook ID from provider",
    )

    # RPC configuration
    rpc_url: str | None = Field(
        default=None,
        max_length=500,
        description="RPC endpoint URL for blockchain queries",
    )

    is_enabled: bool = Field(default=True, description="Is provider active")
    remark: str | None = Field(default=None, max_length=500, description="Internal notes")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships - use selectin to avoid async lazy-load issues
    chain_supports: list["WebhookProviderChain"] = Relationship(
        back_populates="provider",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "name": "TronGrid Production",
                "provider_type": "trongrid",
                "api_key": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "webhook_secret": "your_webhook_secret",
                "webhook_url": "https://api.example.com/webhooks/tron",
                "is_enabled": True,
            }
        }


class WebhookProviderChain(SQLModel, table=True):
    """Association table between WebhookProvider and Chain.

    Tracks which chains each webhook provider supports and is configured for.

    Attributes:
        id: Auto-increment primary key
        provider_id: Foreign key to webhook_providers
        chain_id: Foreign key to chains
        is_enabled: Whether monitoring is enabled for this chain
        contract_addresses: List of token contract addresses to monitor (JSON)
        wallet_addresses: List of wallet addresses being monitored (JSON)
    """

    __tablename__ = "webhook_provider_chains"

    id: int | None = Field(default=None, primary_key=True)
    provider_id: int = Field(foreign_key="webhook_providers.id", index=True)
    chain_id: int = Field(foreign_key="chains.id", index=True)

    is_enabled: bool = Field(default=True, description="Is monitoring enabled")

    # Monitored addresses (JSON arrays)
    contract_addresses: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Token contracts to monitor (JSON array)",
    )
    wallet_addresses: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Wallet addresses being monitored (JSON array)",
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships - use selectin to avoid async lazy-load issues
    provider: WebhookProvider = Relationship(
        back_populates="chain_supports",
        sa_relationship_kwargs={"lazy": "selectin"},
    )
    chain: "Chain" = Relationship(
        back_populates="webhook_providers",
        sa_relationship_kwargs={"lazy": "selectin"},
    )


# Import Chain for type hints
from src.models.chain import Chain  # noqa: E402
