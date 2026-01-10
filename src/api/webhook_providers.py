"""Webhook Providers API endpoints.

Manages third-party webhook service providers for receiving
blockchain transaction notifications.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_super_admin
from src.db.engine import get_db
from src.models import User, WebhookProviderType
from src.schemas.pagination import CustomPage
from src.schemas.webhook_provider import (
    PROVIDER_TYPE_INFO,
    ProviderTypeInfo,
    WebhookProviderCreate,
    WebhookProviderResponse,
    WebhookProviderUpdate,
)
from src.services.webhook_provider_service import WebhookProviderService

router = APIRouter(prefix="/webhook-providers", tags=["Webhook Providers"])


def get_webhook_provider_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookProviderService:
    """Create WebhookProviderService instance."""
    return WebhookProviderService(db)


@router.get("/types", response_model=list[ProviderTypeInfo])
async def list_provider_types(
    _: Annotated[User, Depends(get_current_user)],
) -> list[ProviderTypeInfo]:
    """List all supported webhook provider types.

    Returns information about each provider type including:
    - Name and description
    - Supported blockchains
    - Documentation URL
    """
    return list(PROVIDER_TYPE_INFO.values())


@router.get("", response_model=CustomPage[WebhookProviderResponse])
async def list_providers(
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)],
    provider_type: WebhookProviderType | None = Query(default=None, description="Filter by type"),
    is_enabled: bool | None = Query(default=None, description="Filter by enabled status"),
) -> CustomPage[WebhookProviderResponse]:
    """List webhook providers with pagination and filtering.

    Requires authentication. Super admin can see all providers.
    """
    return await service.list_providers(
        provider_type=provider_type,
        is_enabled=is_enabled,
    )


@router.get("/{provider_id}", response_model=WebhookProviderResponse)
async def get_provider(
    provider_id: int,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)],
) -> WebhookProviderResponse:
    """Get a webhook provider by ID.

    Requires authentication.
    """
    provider = await service.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Webhook provider not found")

    return provider


@router.post("", response_model=WebhookProviderResponse)
async def create_provider(
    data: WebhookProviderCreate,
    _: Annotated[User, Depends(require_super_admin)],
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)],
) -> WebhookProviderResponse:
    """Create a new webhook provider.

    Requires super admin role.

    **Security Note**: API keys and secrets are encrypted before storage.
    """
    return await service.create_provider(data)


@router.patch("/{provider_id}", response_model=WebhookProviderResponse)
async def update_provider(
    provider_id: int,
    data: WebhookProviderUpdate,
    _: Annotated[User, Depends(require_super_admin)],
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)],
) -> WebhookProviderResponse:
    """Update a webhook provider.

    Requires super admin role.

    **Security Note**: Only provided fields will be updated.
    Leave sensitive fields (api_key, api_secret, webhook_secret) as None to keep existing values.
    """
    provider = await service.update_provider(provider_id, data)
    if not provider:
        raise HTTPException(status_code=404, detail="Webhook provider not found")

    return provider


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: int,
    _: Annotated[User, Depends(require_super_admin)],
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)],
) -> dict[str, str]:
    """Delete a webhook provider.

    Requires super admin role.

    **Warning**: This will remove all associated chain configurations.
    """
    deleted = await service.delete_provider(provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook provider not found")

    return {"status": "deleted"}


@router.get("/chain/{chain_code}", response_model=list[WebhookProviderResponse])
async def get_providers_for_chain(
    chain_code: str,
    _: Annotated[User, Depends(get_current_user)],
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)],
) -> list[WebhookProviderResponse]:
    """Get all enabled webhook providers for a specific chain.

    Useful for checking which providers are monitoring a particular blockchain.
    """
    return await service.get_enabled_providers_for_chain(chain_code.upper())


@router.post("/{provider_id}/addresses")
async def update_monitored_addresses(
    provider_id: int,
    chain_id: int,
    wallet_addresses: list[str] | None = None,
    contract_addresses: list[str] | None = None,
    _: Annotated[User, Depends(require_super_admin)] = None,
    service: Annotated[WebhookProviderService, Depends(get_webhook_provider_service)] = None,
) -> dict[str, str]:
    """Update monitored addresses for a provider-chain combination.

    Requires super admin role.

    This is used to keep track of which addresses are registered with
    the webhook provider for monitoring.
    """
    updated = await service.update_monitored_addresses(
        provider_id=provider_id,
        chain_id=chain_id,
        wallet_addresses=wallet_addresses,
        contract_addresses=contract_addresses,
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Provider-chain combination not found",
        )

    return {"status": "updated"}
