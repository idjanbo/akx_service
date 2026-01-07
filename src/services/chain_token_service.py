"""Chain and Token Service - Business logic for chain/token operations."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.chain import Chain
from src.models.token import Token, TokenChainSupport


class ChainTokenService:
    """Service for chain and token business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Chain Operations ============

    async def list_chains(self, is_enabled: bool | None = None) -> list[Chain]:
        """List all chains with optional filter.

        Args:
            is_enabled: Filter by enabled status

        Returns:
            List of chains
        """
        query = select(Chain).order_by(Chain.sort_order, Chain.id)

        if is_enabled is not None:
            query = query.where(Chain.is_enabled == is_enabled)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_chain(self, chain_id: int) -> Chain | None:
        """Get chain by ID."""
        return await self.db.get(Chain, chain_id)

    async def get_chain_with_tokens(self, chain_id: int) -> dict[str, Any] | None:
        """Get chain with supported tokens.

        Args:
            chain_id: Chain ID

        Returns:
            Chain dict with supported tokens or None
        """
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            return None

        query = (
            select(TokenChainSupport, Token)
            .join(Token)
            .where(TokenChainSupport.chain_id == chain_id)
            .where(TokenChainSupport.is_enabled)
            .order_by(Token.sort_order, Token.id)
        )
        result = await self.db.execute(query)
        supports = result.all()

        supported_tokens = [
            {
                "token_id": token.id,
                "token_code": token.code,
                "token_name": token.name,
                "contract_address": support.contract_address,
                "decimals": support.decimals or token.decimals,
                "is_native": support.is_native,
                "min_deposit": support.min_deposit,
                "min_withdrawal": support.min_withdrawal,
                "withdrawal_fee": support.withdrawal_fee,
            }
            for support, token in supports
        ]

        chain_dict = chain.model_dump()
        chain_dict["supported_tokens"] = supported_tokens
        return chain_dict

    async def create_chain(self, data: dict[str, Any]) -> Chain:
        """Create a new chain.

        Args:
            data: Chain data

        Returns:
            Created chain

        Raises:
            ValueError: If code already exists
        """
        existing = await self.db.execute(select(Chain).where(Chain.code == data.get("code")))
        if existing.scalars().first():
            raise ValueError("Chain code already exists")

        chain = Chain(**data)
        self.db.add(chain)
        await self.db.commit()
        await self.db.refresh(chain)
        return chain

    async def update_chain(self, chain_id: int, data: dict[str, Any]) -> Chain | None:
        """Update chain configuration.

        Args:
            chain_id: Chain ID
            data: Update data

        Returns:
            Updated chain or None
        """
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            return None

        for field, value in data.items():
            setattr(chain, field, value)

        chain.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(chain)
        return chain

    async def delete_chain(self, chain_id: int) -> bool:
        """Delete a chain.

        Args:
            chain_id: Chain ID

        Returns:
            True if deleted
        """
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            return False

        await self.db.delete(chain)
        await self.db.commit()
        return True

    # ============ Token Operations ============

    async def list_tokens(
        self,
        is_enabled: bool | None = None,
        is_stablecoin: bool | None = None,
    ) -> list[Token]:
        """List all tokens with optional filters.

        Args:
            is_enabled: Filter by enabled status
            is_stablecoin: Filter by stablecoin flag

        Returns:
            List of tokens
        """
        query = select(Token).order_by(Token.sort_order, Token.id)

        if is_enabled is not None:
            query = query.where(Token.is_enabled == is_enabled)
        if is_stablecoin is not None:
            query = query.where(Token.is_stablecoin == is_stablecoin)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_token(self, token_id: int) -> Token | None:
        """Get token by ID."""
        return await self.db.get(Token, token_id)

    async def get_token_with_chains(self, token_id: int) -> dict[str, Any] | None:
        """Get token with supported chains.

        Args:
            token_id: Token ID

        Returns:
            Token dict with supported chains or None
        """
        token = await self.db.get(Token, token_id)
        if not token:
            return None

        query = (
            select(TokenChainSupport, Chain)
            .join(Chain)
            .where(TokenChainSupport.token_id == token_id)
            .where(TokenChainSupport.is_enabled)
            .where(Chain.is_enabled)
            .order_by(Chain.sort_order, Chain.id)
        )
        result = await self.db.execute(query)
        supports = result.all()

        supported_chains = [
            {
                "chain_id": chain.id,
                "chain_code": chain.code,
                "chain_name": chain.name,
                "contract_address": support.contract_address,
                "decimals": support.decimals or token.decimals,
                "is_native": support.is_native,
                "min_deposit": support.min_deposit,
                "min_withdrawal": support.min_withdrawal,
                "withdrawal_fee": support.withdrawal_fee,
                "confirmation_blocks": chain.confirmation_blocks,
            }
            for support, chain in supports
        ]

        token_dict = token.model_dump()
        token_dict["supported_chains"] = supported_chains
        return token_dict

    async def create_token(self, data: dict[str, Any]) -> Token:
        """Create a new token.

        Args:
            data: Token data

        Returns:
            Created token

        Raises:
            ValueError: If code already exists
        """
        existing = await self.db.execute(select(Token).where(Token.code == data.get("code")))
        if existing.scalars().first():
            raise ValueError("Token code already exists")

        token = Token(**data)
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def update_token(self, token_id: int, data: dict[str, Any]) -> Token | None:
        """Update token configuration.

        Args:
            token_id: Token ID
            data: Update data

        Returns:
            Updated token or None
        """
        token = await self.db.get(Token, token_id)
        if not token:
            return None

        for field, value in data.items():
            setattr(token, field, value)

        token.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def delete_token(self, token_id: int) -> bool:
        """Delete a token.

        Args:
            token_id: Token ID

        Returns:
            True if deleted
        """
        token = await self.db.get(Token, token_id)
        if not token:
            return False

        await self.db.delete(token)
        await self.db.commit()
        return True

    # ============ Token Chain Support Operations ============

    async def list_token_chain_supports(
        self,
        token_id: int | None = None,
        chain_id: int | None = None,
        is_enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List token-chain supports with filters.

        Args:
            token_id: Filter by token
            chain_id: Filter by chain
            is_enabled: Filter by enabled status

        Returns:
            List of support configurations
        """
        query = select(TokenChainSupport, Token, Chain).join(Token).join(Chain)

        if token_id is not None:
            query = query.where(TokenChainSupport.token_id == token_id)
        if chain_id is not None:
            query = query.where(TokenChainSupport.chain_id == chain_id)
        if is_enabled is not None:
            query = query.where(TokenChainSupport.is_enabled == is_enabled)

        result = await self.db.execute(query)
        supports_data = result.all()

        return [
            {
                "id": support.id,
                "token_code": token.code,
                "chain_code": chain.code,
                "contract_address": support.contract_address,
                "decimals": support.decimals or token.decimals,
                "is_native": support.is_native,
                "is_enabled": support.is_enabled,
                "min_deposit": support.min_deposit,
                "min_withdrawal": support.min_withdrawal,
                "withdrawal_fee": support.withdrawal_fee,
                "created_at": support.created_at,
                "updated_at": support.updated_at,
            }
            for support, token, chain in supports_data
        ]

    async def create_token_chain_support(self, data: dict[str, Any]) -> TokenChainSupport:
        """Create token-chain support.

        Args:
            data: Support data with token_id and chain_id

        Returns:
            Created support

        Raises:
            ValueError: If token/chain not found or support exists
        """
        token = await self.db.get(Token, data.get("token_id"))
        if not token:
            raise ValueError("Token not found")

        chain = await self.db.get(Chain, data.get("chain_id"))
        if not chain:
            raise ValueError("Chain not found")

        existing = await self.db.execute(
            select(TokenChainSupport)
            .where(TokenChainSupport.token_id == data.get("token_id"))
            .where(TokenChainSupport.chain_id == data.get("chain_id"))
        )
        if existing.scalars().first():
            raise ValueError("Token-chain support already exists")

        support = TokenChainSupport(**data)
        self.db.add(support)
        await self.db.commit()
        await self.db.refresh(support)
        return support

    async def update_token_chain_support(
        self, support_id: int, data: dict[str, Any]
    ) -> TokenChainSupport | None:
        """Update token-chain support.

        Args:
            support_id: Support ID
            data: Update data

        Returns:
            Updated support or None
        """
        support = await self.db.get(TokenChainSupport, support_id)
        if not support:
            return None

        for field, value in data.items():
            setattr(support, field, value)

        support.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(support)
        return support

    async def delete_token_chain_support(self, support_id: int) -> bool:
        """Delete token-chain support.

        Args:
            support_id: Support ID

        Returns:
            True if deleted
        """
        support = await self.db.get(TokenChainSupport, support_id)
        if not support:
            return False

        await self.db.delete(support)
        await self.db.commit()
        return True
