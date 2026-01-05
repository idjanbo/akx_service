"""AKX Crypto Payment Gateway - Chain model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.token import TokenChainSupport
    from src.models.webhook_provider import WebhookProviderChain


class Chain(SQLModel, table=True):
    """Blockchain network configuration.

    Manages supported blockchain networks independently from tokens.
    Each chain has its own characteristics and configuration.

    Attributes:
        id: Auto-increment primary key
        code: Unique chain identifier code (e.g., 'TRON', 'ETH', 'BSC')
        name: Chain name (e.g., 'TRON')
        description: Chain description and notes
        remark: Internal remarks/memo
        is_enabled: Whether this chain is currently active
        sort_order: Display order (lower numbers appear first)
        explorer_url: Block explorer base URL (e.g., https://tronscan.org)
        native_token: Native token symbol (e.g., 'TRX' for TRON, 'ETH' for Ethereum)
        confirmation_blocks: Required confirmations for finality
        created_at: Record creation timestamp
        updated_at: Last modification timestamp
    """

    __tablename__ = "chains"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=20, unique=True, index=True, description="Chain code (uppercase)")
    name: str = Field(max_length=100, description="Chain name")
    description: str | None = Field(default=None, max_length=500, description="Chain description")
    remark: str | None = Field(default=None, max_length=500, description="Internal remarks")

    is_enabled: bool = Field(default=True, description="Is chain active")
    sort_order: int = Field(default=0, description="Display order")

    # Chain-specific configuration
    explorer_url: str | None = Field(default=None, max_length=500, description="Block explorer URL")
    native_token: str | None = Field(default=None, max_length=20, description="Native token symbol")
    confirmation_blocks: int = Field(default=1, description="Required confirmations")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    token_supports: list["TokenChainSupport"] = Relationship(back_populates="chain")
    webhook_providers: list["WebhookProviderChain"] = Relationship(back_populates="chain")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "code": "TRON",
                "name": "TRON",
                "description": "High-throughput blockchain supporting TRC-20 tokens",
                "is_enabled": True,
                "sort_order": 1,
                "explorer_url": "https://tronscan.org",
                "native_token": "TRX",
                "confirmation_blocks": 19,
            }
        }
