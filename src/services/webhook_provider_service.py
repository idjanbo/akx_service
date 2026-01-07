"""Webhook Provider service - Business logic layer."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.security import decrypt_sensitive_data, encrypt_sensitive_data
from src.models import Chain, WebhookProvider, WebhookProviderChain, WebhookProviderType
from src.schemas.webhook_provider import (
    PROVIDER_TYPE_INFO,
    ProviderTypeInfo,
    WebhookProviderChainResponse,
    WebhookProviderCreate,
    WebhookProviderResponse,
    WebhookProviderUpdate,
)

logger = logging.getLogger(__name__)


class WebhookProviderService:
    """Service for managing webhook providers."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_providers(
        self,
        page: int = 1,
        page_size: int = 20,
        provider_type: WebhookProviderType | None = None,
        is_enabled: bool | None = None,
    ) -> tuple[list[WebhookProviderResponse], int]:
        """List webhook providers with pagination and filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            provider_type: Filter by provider type
            is_enabled: Filter by enabled status

        Returns:
            Tuple of (providers list, total count)
        """
        # Build query
        stmt = select(WebhookProvider)

        if provider_type:
            stmt = stmt.where(WebhookProvider.provider_type == provider_type)
        if is_enabled is not None:
            stmt = stmt.where(WebhookProvider.is_enabled == is_enabled)

        # Count total
        count_stmt = select(WebhookProvider)
        if provider_type:
            count_stmt = count_stmt.where(WebhookProvider.provider_type == provider_type)
        if is_enabled is not None:
            count_stmt = count_stmt.where(WebhookProvider.is_enabled == is_enabled)
        count_result = await self.db.execute(count_stmt)
        total = len(count_result.scalars().all())

        # Paginate
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(stmt)
        providers = result.scalars().all()

        return [self._to_response(p) for p in providers], total

    async def get_provider(self, provider_id: int) -> WebhookProviderResponse | None:
        """Get a webhook provider by ID.

        Args:
            provider_id: Provider ID

        Returns:
            Provider response or None if not found
        """
        stmt = select(WebhookProvider).where(WebhookProvider.id == provider_id)
        result = await self.db.execute(stmt)
        provider = result.scalars().first()

        if not provider:
            return None

        return self._to_response(provider)

    async def create_provider(self, data: WebhookProviderCreate) -> WebhookProviderResponse:
        """Create a new webhook provider.

        Args:
            data: Provider creation data

        Returns:
            Created provider response
        """
        # Encrypt sensitive fields
        encrypted_api_key = encrypt_sensitive_data(data.api_key) if data.api_key else None
        encrypted_api_secret = encrypt_sensitive_data(data.api_secret) if data.api_secret else None
        encrypted_webhook_secret = (
            encrypt_sensitive_data(data.webhook_secret) if data.webhook_secret else None
        )

        # Create provider
        provider = WebhookProvider(
            name=data.name,
            provider_type=data.provider_type,
            api_key=encrypted_api_key,
            api_secret=encrypted_api_secret,
            webhook_secret=encrypted_webhook_secret,
            webhook_url=data.webhook_url,
            webhook_id=data.webhook_id,
            is_enabled=data.is_enabled,
            remark=data.remark,
        )
        self.db.add(provider)
        await self.db.flush()

        # Add chain supports
        if data.chain_ids:
            for chain_id in data.chain_ids:
                chain_support = WebhookProviderChain(
                    provider_id=provider.id,
                    chain_id=chain_id,
                    is_enabled=True,
                )
                self.db.add(chain_support)

        await self.db.commit()
        await self.db.refresh(provider)

        # Reload with relationships
        return await self.get_provider(provider.id)  # type: ignore

    async def update_provider(
        self, provider_id: int, data: WebhookProviderUpdate
    ) -> WebhookProviderResponse | None:
        """Update a webhook provider.

        Args:
            provider_id: Provider ID
            data: Update data

        Returns:
            Updated provider response or None if not found
        """
        stmt = select(WebhookProvider).where(WebhookProvider.id == provider_id)
        result = await self.db.execute(stmt)
        provider = result.scalars().first()

        if not provider:
            return None

        # Update basic fields
        if data.name is not None:
            provider.name = data.name
        if data.webhook_url is not None:
            provider.webhook_url = data.webhook_url
        if data.webhook_id is not None:
            provider.webhook_id = data.webhook_id
        if data.is_enabled is not None:
            provider.is_enabled = data.is_enabled
        if data.remark is not None:
            provider.remark = data.remark

        # Update encrypted fields (only if provided)
        if data.api_key is not None:
            provider.api_key = encrypt_sensitive_data(data.api_key) if data.api_key else None
        if data.api_secret is not None:
            provider.api_secret = (
                encrypt_sensitive_data(data.api_secret) if data.api_secret else None
            )
        if data.webhook_secret is not None:
            provider.webhook_secret = (
                encrypt_sensitive_data(data.webhook_secret) if data.webhook_secret else None
            )

        provider.updated_at = datetime.now(timezone.utc)

        # Update chain supports if provided
        if data.chain_ids is not None:
            # Remove existing chain supports
            stmt = select(WebhookProviderChain).where(
                WebhookProviderChain.provider_id == provider_id
            )
            result = await self.db.execute(stmt)
            existing = result.scalars().all()
            for support in existing:
                await self.db.delete(support)

            # Add new chain supports
            for chain_id in data.chain_ids:
                chain_support = WebhookProviderChain(
                    provider_id=provider_id,
                    chain_id=chain_id,
                    is_enabled=True,
                )
                self.db.add(chain_support)

        await self.db.commit()

        return await self.get_provider(provider_id)

    async def delete_provider(self, provider_id: int) -> bool:
        """Delete a webhook provider.

        Args:
            provider_id: Provider ID

        Returns:
            True if deleted, False if not found
        """
        stmt = select(WebhookProvider).where(WebhookProvider.id == provider_id)
        result = await self.db.execute(stmt)
        provider = result.scalars().first()

        if not provider:
            return False

        await self.db.delete(provider)
        await self.db.commit()
        return True

    async def get_provider_by_type_and_chain(
        self, provider_type: WebhookProviderType, chain_code: str
    ) -> WebhookProvider | None:
        """Get an enabled provider by type and chain.

        Used by webhook handlers to find the provider configuration.

        Args:
            provider_type: Provider type
            chain_code: Chain code

        Returns:
            Provider or None if not found
        """
        stmt = (
            select(WebhookProvider)
            .join(WebhookProviderChain)
            .join(Chain)
            .where(
                WebhookProvider.provider_type == provider_type,
                WebhookProvider.is_enabled == True,  # noqa: E712
                WebhookProviderChain.is_enabled == True,  # noqa: E712
                Chain.code == chain_code,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_decrypted_secrets(self, provider_id: int) -> dict[str, str | None] | None:
        """Get decrypted secrets for a provider.

        SECURITY: Only call this when needed for webhook verification.

        Args:
            provider_id: Provider ID

        Returns:
            Dict with decrypted secrets or None if not found
        """
        stmt = select(WebhookProvider).where(WebhookProvider.id == provider_id)
        result = await self.db.execute(stmt)
        provider = result.scalars().first()

        if not provider:
            return None

        return {
            "api_key": decrypt_sensitive_data(provider.api_key) if provider.api_key else None,
            "api_secret": decrypt_sensitive_data(provider.api_secret)
            if provider.api_secret
            else None,
            "webhook_secret": (
                decrypt_sensitive_data(provider.webhook_secret) if provider.webhook_secret else None
            ),
        }

    def get_provider_types(self) -> list[ProviderTypeInfo]:
        """Get all supported provider types with their info.

        Returns:
            List of provider type information
        """
        return list(PROVIDER_TYPE_INFO.values())

    async def get_enabled_providers_for_chain(
        self, chain_code: str
    ) -> list[WebhookProviderResponse]:
        """Get all enabled providers for a specific chain.

        Args:
            chain_code: Chain code

        Returns:
            List of enabled providers
        """
        stmt = (
            select(WebhookProvider)
            .join(WebhookProviderChain)
            .join(Chain)
            .where(
                WebhookProvider.is_enabled == True,  # noqa: E712
                WebhookProviderChain.is_enabled == True,  # noqa: E712
                Chain.code == chain_code,
            )
        )
        result = await self.db.execute(stmt)
        providers = result.scalars().all()

        return [self._to_response(p) for p in providers]

    async def update_monitored_addresses(
        self,
        provider_id: int,
        chain_id: int,
        wallet_addresses: list[str] | None = None,
        contract_addresses: list[str] | None = None,
    ) -> bool:
        """Update monitored addresses for a provider-chain combination.

        Args:
            provider_id: Provider ID
            chain_id: Chain ID
            wallet_addresses: List of wallet addresses to monitor
            contract_addresses: List of contract addresses to monitor

        Returns:
            True if updated, False if not found
        """
        stmt = select(WebhookProviderChain).where(
            WebhookProviderChain.provider_id == provider_id,
            WebhookProviderChain.chain_id == chain_id,
        )
        result = await self.db.execute(stmt)
        chain_support = result.scalars().first()

        if not chain_support:
            return False

        if wallet_addresses is not None:
            chain_support.wallet_addresses = json.dumps(wallet_addresses)
        if contract_addresses is not None:
            chain_support.contract_addresses = json.dumps(contract_addresses)

        chain_support.updated_at = datetime.now(timezone.utc)
        await self.db.commit()

        return True

    def _to_response(self, provider: WebhookProvider) -> WebhookProviderResponse:
        """Convert provider model to response schema.

        Args:
            provider: Provider model

        Returns:
            Provider response schema
        """
        chain_supports = []
        for support in provider.chain_supports:
            chain_supports.append(
                WebhookProviderChainResponse(
                    id=support.id,
                    chain_id=support.chain_id,
                    chain_code=support.chain.code if support.chain else None,
                    chain_name=support.chain.name if support.chain else None,
                    is_enabled=support.is_enabled,
                    created_at=support.created_at,
                )
            )

        return WebhookProviderResponse(
            id=provider.id,  # type: ignore
            name=provider.name,
            provider_type=provider.provider_type,
            webhook_url=provider.webhook_url,
            webhook_id=provider.webhook_id,
            is_enabled=provider.is_enabled,
            remark=provider.remark,
            has_api_key=bool(provider.api_key),
            has_api_secret=bool(provider.api_secret),
            has_webhook_secret=bool(provider.webhook_secret),
            chain_supports=chain_supports,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )
