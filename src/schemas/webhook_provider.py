"""Webhook Provider schemas for API request/response."""

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.webhook_provider import WebhookProviderType

# ============ Chain Support Schemas ============


class WebhookProviderChainBase(BaseModel):
    """Base schema for webhook provider chain support."""

    chain_id: int = Field(description="Chain ID")
    is_enabled: bool = Field(default=True, description="Is monitoring enabled")


class WebhookProviderChainCreate(WebhookProviderChainBase):
    """Schema for creating webhook provider chain support."""

    pass


class WebhookProviderChainResponse(WebhookProviderChainBase):
    """Schema for webhook provider chain support response."""

    id: int
    chain_code: str | None = None
    chain_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Provider Schemas ============


class WebhookProviderBase(BaseModel):
    """Base schema for webhook provider."""

    name: str = Field(max_length=100, description="Provider display name")
    provider_type: WebhookProviderType = Field(description="Provider type")
    webhook_url: str | None = Field(default=None, max_length=500, description="Callback URL")
    webhook_id: str | None = Field(
        default=None, max_length=100, description="Webhook ID from provider"
    )
    rpc_url: str | None = Field(default=None, max_length=500, description="RPC endpoint URL")
    is_enabled: bool = Field(default=True, description="Is provider active")
    remark: str | None = Field(default=None, max_length=500, description="Internal notes")


class WebhookProviderCreate(WebhookProviderBase):
    """Schema for creating a webhook provider."""

    api_key: str | None = Field(default=None, description="API key")
    api_secret: str | None = Field(default=None, description="API secret")
    webhook_secret: str | None = Field(default=None, description="Webhook signature secret")
    chain_ids: list[int] = Field(default_factory=list, description="Supported chain IDs")


class WebhookProviderUpdate(BaseModel):
    """Schema for updating a webhook provider."""

    name: str | None = Field(default=None, max_length=100)
    api_key: str | None = None
    api_secret: str | None = None
    webhook_secret: str | None = None
    webhook_url: str | None = None
    webhook_id: str | None = None
    rpc_url: str | None = None
    is_enabled: bool | None = None
    remark: str | None = None
    chain_ids: list[int] | None = None


class WebhookProviderResponse(WebhookProviderBase):
    """Schema for webhook provider response."""

    id: int
    has_api_key: bool = Field(description="Whether API key is set")
    has_api_secret: bool = Field(description="Whether API secret is set")
    has_webhook_secret: bool = Field(description="Whether webhook secret is set")
    chain_supports: list[WebhookProviderChainResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookProviderListResponse(BaseModel):
    """Schema for paginated webhook provider list."""

    items: list[WebhookProviderResponse]
    total: int
    page: int
    page_size: int


# ============ Provider Type Info ============


class ProviderTypeInfo(BaseModel):
    """Information about a webhook provider type."""

    type: WebhookProviderType
    name: str
    description: str
    supported_chains: list[str]
    docs_url: str | None = None


# Provider type metadata
# NOTE: supported_chains must match chain.code in database (e.g., ETH, not ETHEREUM)
PROVIDER_TYPE_INFO: dict[WebhookProviderType, ProviderTypeInfo] = {
    WebhookProviderType.tatum: ProviderTypeInfo(
        type=WebhookProviderType.tatum,
        name="Tatum",
        description="Tatum Webhooks for multi-chain notifications including TRON",
        supported_chains=["TRON", "ETH", "BSC", "POLYGON", "SOL"],
        docs_url="https://docs.tatum.io/docs/notifications",
    ),
    WebhookProviderType.alchemy: ProviderTypeInfo(
        type=WebhookProviderType.alchemy,
        name="Alchemy",
        description="Alchemy Webhooks for Ethereum and EVM-compatible chains",
        supported_chains=["ETH", "POLYGON", "ARBITRUM", "OPTIMISM", "BASE"],
        docs_url="https://docs.alchemy.com/reference/notify-api-quickstart",
    ),
    WebhookProviderType.helius: ProviderTypeInfo(
        type=WebhookProviderType.helius,
        name="Helius",
        description="Helius Webhooks for Solana blockchain notifications",
        supported_chains=["SOL"],
        docs_url="https://docs.helius.dev/webhooks/webhooks-summary",
    ),
    WebhookProviderType.quicknode: ProviderTypeInfo(
        type=WebhookProviderType.quicknode,
        name="QuickNode",
        description="QuickNode Streams for multi-chain notifications",
        supported_chains=["ETH", "POLYGON", "BSC", "ARBITRUM", "SOL", "TRON"],
        docs_url="https://www.quicknode.com/docs/streams",
    ),
    WebhookProviderType.moralis: ProviderTypeInfo(
        type=WebhookProviderType.moralis,
        name="Moralis",
        description="Moralis Streams for multi-chain real-time data",
        supported_chains=["ETH", "POLYGON", "BSC", "ARBITRUM", "AVAX"],
        docs_url="https://docs.moralis.io/streams-api",
    ),
    WebhookProviderType.getblock: ProviderTypeInfo(
        type=WebhookProviderType.getblock,
        name="GetBlock",
        description="GetBlock Webhooks for multi-chain notifications",
        supported_chains=["TRON", "ETH", "BSC", "SOL"],
        docs_url="https://getblock.io/docs/",
    ),
    WebhookProviderType.custom: ProviderTypeInfo(
        type=WebhookProviderType.custom,
        name="Custom",
        description="Custom webhook endpoint for self-hosted solutions",
        supported_chains=[],
        docs_url=None,
    ),
}
