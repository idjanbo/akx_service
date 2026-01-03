"""AKX Crypto Payment Gateway - Chain and Token schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================================
# Chain Schemas
# ============================================================================

class ChainBase(BaseModel):
    """Base chain attributes."""

    code: str = Field(..., description="Chain code (uppercase)", max_length=20)
    name: str = Field(..., description="Chain name", max_length=100)
    full_name: str = Field(..., description="Full official name", max_length=200)
    description: str | None = Field(
        None, description="Chain description", max_length=500
    )
    remark: str | None = Field(None, description="Internal remarks", max_length=500)
    is_enabled: bool = Field(True, description="Is chain active")
    sort_order: int = Field(0, description="Display order")
    rpc_url: str | None = Field(None, description="RPC endpoint", max_length=500)
    explorer_url: str | None = Field(
        None, description="Block explorer URL", max_length=500
    )
    native_token: str | None = Field(
        None, description="Native token symbol", max_length=20
    )
    confirmation_blocks: int = Field(1, description="Required confirmations")


class ChainCreate(ChainBase):
    """Schema for creating a new chain."""
    pass


class ChainUpdate(BaseModel):
    """Schema for updating a chain (all fields optional)."""

    name: str | None = Field(None, max_length=100)
    full_name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=500)
    remark: str | None = Field(None, max_length=500)
    is_enabled: bool | None = None
    sort_order: int | None = None
    rpc_url: str | None = Field(None, max_length=500)
    explorer_url: str | None = Field(None, max_length=500)
    native_token: str | None = Field(None, max_length=20)
    confirmation_blocks: int | None = None


class ChainResponse(ChainBase):
    """Schema for chain responses."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Token Schemas
# ============================================================================

class TokenBase(BaseModel):
    """Base token attributes."""

    code: str = Field(..., description="Token code (uppercase)", max_length=20)
    symbol: str = Field(..., description="Trading symbol", max_length=20)
    name: str = Field(..., description="Token name", max_length=100)
    full_name: str = Field(..., description="Full official name", max_length=200)
    description: str | None = Field(
        None, description="Token description", max_length=500
    )
    remark: str | None = Field(None, description="Internal remarks", max_length=500)
    is_enabled: bool = Field(True, description="Is token active")
    sort_order: int = Field(0, description="Display order")
    decimals: int = Field(6, description="Default decimal places")
    icon_url: str | None = Field(
        None, description="Token icon URL", max_length=500
    )
    is_stablecoin: bool = Field(False, description="Is stablecoin")


class TokenCreate(TokenBase):
    """Schema for creating a new token."""
    pass


class TokenUpdate(BaseModel):
    """Schema for updating a token (all fields optional)."""

    symbol: str | None = Field(None, max_length=20)
    name: str | None = Field(None, max_length=100)
    full_name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=500)
    remark: str | None = Field(None, max_length=500)
    is_enabled: bool | None = None
    sort_order: int | None = None
    decimals: int | None = None
    icon_url: str | None = Field(None, max_length=500)
    is_stablecoin: bool | None = None


class TokenResponse(TokenBase):
    """Schema for token responses."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# TokenChainSupport Schemas
# ============================================================================

class TokenChainSupportBase(BaseModel):
    """Base token-chain support attributes."""

    token_id: int = Field(..., description="Token ID")
    chain_id: int = Field(..., description="Chain ID")
    contract_address: str = Field(
        "", description="Contract address (empty for native)", max_length=200
    )
    decimals: int | None = Field(
        None, description="Override decimals for this chain"
    )
    is_enabled: bool = Field(True, description="Is this token-chain pair active")
    is_native: bool = Field(False, description="Is native token of the chain")
    min_deposit: str | None = Field(
        None, description="Minimum deposit amount", max_length=50
    )
    min_withdrawal: str | None = Field(
        None, description="Minimum withdrawal amount", max_length=50
    )
    withdrawal_fee: str | None = Field(
        None, description="Fixed withdrawal fee", max_length=50
    )


class TokenChainSupportCreate(TokenChainSupportBase):
    """Schema for creating token-chain support."""
    pass


class TokenChainSupportUpdate(BaseModel):
    """Schema for updating token-chain support (all fields optional)."""

    contract_address: str | None = Field(None, max_length=200)
    decimals: int | None = None
    is_enabled: bool | None = None
    is_native: bool | None = None
    min_deposit: str | None = Field(None, max_length=50)
    min_withdrawal: str | None = Field(None, max_length=50)
    withdrawal_fee: str | None = Field(None, max_length=50)


class TokenChainSupportResponse(TokenChainSupportBase):
    """Schema for token-chain support responses."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenChainSupportWithDetails(TokenChainSupportResponse):
    """Token-chain support with nested chain and token details."""

    token: TokenResponse
    chain: ChainResponse


# ============================================================================
# Combined Schemas for Frontend
# ============================================================================

class TokenWithChains(TokenResponse):
    """Token with list of supported chains."""

    supported_chains: list[dict] = Field(
        default_factory=list,
        description="List of chains supporting this token with configuration"
    )


class ChainWithTokens(ChainResponse):
    """Chain with list of supported tokens."""

    supported_tokens: list[dict] = Field(
        default_factory=list,
        description="List of tokens supported on this chain with configuration"
    )
