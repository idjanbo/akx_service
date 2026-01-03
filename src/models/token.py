"""AKX Crypto Payment Gateway - Token model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from src.models.chain import Chain
    from src.models.token import TokenChainSupport


class Token(SQLModel, table=True):
    """Cryptocurrency token configuration.

    Manages supported tokens/currencies independently from chains.
    Each token can be supported on multiple chains.

    Attributes:
        id: Auto-increment primary key
        code: Unique token identifier code (e.g., 'USDT', 'BTC', 'ETH')
        symbol: Trading symbol (usually same as code)
        name: Display name (e.g., 'Tether USD')
        full_name: Complete official name (e.g., 'Tether USD Stablecoin')
        description: Token description and notes
        remark: Internal remarks/memo
        is_enabled: Whether this token is currently active
        sort_order: Display order (lower numbers appear first)
        decimals: Default decimal places (can be overridden per chain)
        icon_url: Token icon/logo URL
        is_stablecoin: Whether this is a stablecoin
        created_at: Record creation timestamp
        updated_at: Last modification timestamp
    """

    __tablename__ = "tokens"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(
        max_length=20, unique=True, index=True, description="Token code (uppercase)"
    )
    symbol: str = Field(max_length=20, description="Trading symbol")
    name: str = Field(max_length=100, description="Token name")
    full_name: str = Field(max_length=200, description="Full official name")
    description: str | None = Field(
        default=None, max_length=500, description="Token description"
    )
    remark: str | None = Field(
        default=None, max_length=500, description="Internal remarks"
    )

    is_enabled: bool = Field(default=True, description="Is token active")
    sort_order: int = Field(default=0, description="Display order")

    # Token-specific configuration
    decimals: int = Field(default=6, description="Default decimal places")
    icon_url: str | None = Field(
        default=None, max_length=500, description="Token icon URL"
    )
    is_stablecoin: bool = Field(default=False, description="Is stablecoin")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    chain_supports: list["TokenChainSupport"] = Relationship(back_populates="token")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "code": "USDT",
                "symbol": "USDT",
                "name": "Tether USD",
                "full_name": "Tether USD Stablecoin",
                "description": "Leading stablecoin pegged to USD",
                "is_enabled": True,
                "sort_order": 1,
                "decimals": 6,
                "is_stablecoin": True
            }
        }


class TokenChainSupport(SQLModel, table=True):
    """Token support on specific chains.

    Many-to-many relationship between tokens and chains.
    Stores chain-specific configuration for each token.

    Attributes:
        id: Auto-increment primary key
        token_id: Reference to Token
        chain_id: Reference to Chain
        contract_address: Token contract address on this chain (empty for native tokens)
        decimals: Token decimals on this chain (overrides token.decimals if set)
        is_enabled: Whether this token-chain pair is active
        is_native: Whether this is the native token of the chain
        min_deposit: Minimum deposit amount
        min_withdrawal: Minimum withdrawal amount
        withdrawal_fee: Fixed withdrawal fee for this token-chain pair
        created_at: Record creation timestamp
        updated_at: Last modification timestamp
    """

    __tablename__ = "token_chain_supports"

    id: int | None = Field(default=None, primary_key=True)
    token_id: int = Field(foreign_key="tokens.id", index=True)
    chain_id: int = Field(foreign_key="chains.id", index=True)

    contract_address: str = Field(
        default="",
        max_length=200,
        description="Contract address (empty for native)",
    )
    decimals: int | None = Field(
        default=None, description="Override decimals for this chain"
    )
    is_enabled: bool = Field(
        default=True, description="Is this token-chain pair active"
    )
    is_native: bool = Field(default=False, description="Is native token of the chain")

    # Limits and fees (stored as string to preserve precision)
    min_deposit: str | None = Field(
        default=None, max_length=50, description="Minimum deposit amount"
    )
    min_withdrawal: str | None = Field(
        default=None, max_length=50, description="Minimum withdrawal amount"
    )
    withdrawal_fee: str | None = Field(
        default=None, max_length=50, description="Fixed withdrawal fee"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    token: "Token" = Relationship(back_populates="chain_supports")
    chain: "Chain" = Relationship(back_populates="token_supports")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "token_id": 1,
                "chain_id": 1,
                "contract_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
                "decimals": 6,
                "is_enabled": True,
                "is_native": False,
                "min_deposit": "1.0",
                "min_withdrawal": "10.0",
                "withdrawal_fee": "1.0"
            }
        }
