"""Payment Channel Service - Business logic for payment channel operations."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chain import Chain
from src.models.payment_channel import ChannelStatus, PaymentChannel
from src.models.token import Token
from src.models.user import User, UserRole
from src.models.wallet import Wallet
from src.utils.pagination import PaginatedResult, PaginationParams, paginate_query


class ChannelService:
    """Service for payment channel business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ Channel CRUD Operations ============

    async def list_channels(
        self,
        user: User,
        params: PaginationParams,
        token_id: int | None = None,
        chain_id: int | None = None,
        status_filter: str | None = None,
    ) -> PaginatedResult[dict[str, Any]]:
        """List payment channels with filters.

        Args:
            user: Current user
            params: Pagination parameters
            token_id: Filter by token
            chain_id: Filter by chain
            status_filter: Filter by status

        Returns:
            Paginated channel list
        """
        query = select(PaymentChannel)

        # Role-based filtering
        if user.role == UserRole.MERCHANT:
            query = query.where(PaymentChannel.user_id == user.id)

        # Apply filters
        if token_id:
            query = query.where(PaymentChannel.token_id == token_id)
        if chain_id:
            query = query.where(PaymentChannel.chain_id == chain_id)
        if status_filter:
            try:
                status_enum = ChannelStatus(status_filter)
                query = query.where(PaymentChannel.status == status_enum)
            except ValueError:
                pass

        query = query.order_by(PaymentChannel.priority, PaymentChannel.created_at.desc())

        # Paginate
        channels, total = await paginate_query(self.db, query, params)

        # Get related data
        related_data = await self._get_related_data(channels)

        items = [self._channel_to_dict(c, related_data) for c in channels]

        return PaginatedResult(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_channel(self, channel_id: int, user: User) -> dict[str, Any] | None:
        """Get a single channel by ID.

        Args:
            channel_id: Channel ID
            user: Current user

        Returns:
            Channel dict or None
        """
        channel = await self.db.get(PaymentChannel, channel_id)
        if not channel:
            return None

        if user.role == UserRole.MERCHANT and channel.user_id != user.id:
            return None

        # Get related data
        wallet = await self.db.get(Wallet, channel.wallet_id)
        token = await self.db.get(Token, channel.token_id)
        chain = await self.db.get(Chain, channel.chain_id)
        owner = await self.db.get(User, channel.user_id)

        return self._channel_to_dict(
            channel,
            {
                "wallets": {channel.wallet_id: wallet} if wallet else {},
                "tokens": {channel.token_id: token} if token else {},
                "chains": {channel.chain_id: chain} if chain else {},
                "users": {channel.user_id: owner} if owner else {},
            },
        )

    async def create_channels(
        self,
        user: User,
        wallet_ids: list[int],
        token_id: int,
        chain_id: int,
        min_amount: str = "0",
        max_amount: str = "999999999",
        daily_limit: str = "999999999",
        balance_limit: str = "999999999",
        priority: int = 100,
        label: str | None = None,
    ) -> tuple[list[PaymentChannel], Token, Chain]:
        """Create payment channels for multiple wallets.

        Args:
            user: Current user
            wallet_ids: List of wallet IDs
            token_id: Token ID
            chain_id: Chain ID
            min_amount: Minimum payment amount
            max_amount: Maximum payment amount
            daily_limit: Daily transaction limit
            balance_limit: Balance limit threshold
            priority: Channel priority
            label: Optional label

        Returns:
            Tuple of (created channels, token, chain)

        Raises:
            ValueError: If validation fails
        """
        # Verify token
        token = await self.db.get(Token, token_id)
        if not token:
            raise ValueError(f"Token with id {token_id} not found")

        # Verify chain
        chain = await self.db.get(Chain, chain_id)
        if not chain:
            raise ValueError(f"Chain with id {chain_id} not found")

        # Verify wallets
        wallets_query = select(Wallet).where(Wallet.id.in_(wallet_ids))
        if user.role == UserRole.MERCHANT:
            wallets_query = wallets_query.where(Wallet.user_id == user.id)

        wallets_result = await self.db.execute(wallets_query)
        wallets = {w.id: w for w in wallets_result.scalars()}

        if len(wallets) != len(wallet_ids):
            raise ValueError("Some wallets not found or not accessible")

        # Check for existing channels
        existing_query = select(PaymentChannel).where(
            PaymentChannel.wallet_id.in_(wallet_ids),
            PaymentChannel.token_id == token_id,
            PaymentChannel.chain_id == chain_id,
        )
        existing_result = await self.db.execute(existing_query)
        existing_wallet_ids = {c.wallet_id for c in existing_result.scalars()}

        # Create channels
        created_channels: list[PaymentChannel] = []
        for wallet_id in wallet_ids:
            if wallet_id in existing_wallet_ids:
                continue

            wallet = wallets[wallet_id]
            channel = PaymentChannel(
                user_id=wallet.user_id or user.id,
                wallet_id=wallet_id,
                token_id=token_id,
                chain_id=chain_id,
                min_amount=Decimal(min_amount),
                max_amount=Decimal(max_amount),
                daily_limit=Decimal(daily_limit),
                balance_limit=Decimal(balance_limit),
                priority=priority,
                label=label,
            )
            self.db.add(channel)
            created_channels.append(channel)

        await self.db.commit()
        for c in created_channels:
            await self.db.refresh(c)

        return created_channels, token, chain

    async def update_channel(
        self,
        channel_id: int,
        user: User,
        status: str | None = None,
        min_amount: str | None = None,
        max_amount: str | None = None,
        daily_limit: str | None = None,
        balance_limit: str | None = None,
        priority: int | None = None,
        label: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a payment channel.

        Args:
            channel_id: Channel ID
            user: Current user
            status: New status
            min_amount: New min amount
            max_amount: New max amount
            daily_limit: New daily limit
            balance_limit: New balance limit
            priority: New priority
            label: New label

        Returns:
            Updated channel dict or None

        Raises:
            ValueError: If validation fails
        """
        channel = await self.db.get(PaymentChannel, channel_id)
        if not channel:
            return None

        if user.role == UserRole.MERCHANT and channel.user_id != user.id:
            return None

        # Update fields
        if status is not None:
            try:
                channel.status = ChannelStatus(status)
            except ValueError:
                raise ValueError(f"Invalid status: {status}")

        if min_amount is not None:
            channel.min_amount = Decimal(min_amount)
        if max_amount is not None:
            channel.max_amount = Decimal(max_amount)
        if daily_limit is not None:
            channel.daily_limit = Decimal(daily_limit)
        if balance_limit is not None:
            channel.balance_limit = Decimal(balance_limit)
        if priority is not None:
            channel.priority = priority
        if label is not None:
            channel.label = label

        channel.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(channel)

        return await self.get_channel(channel_id, user)

    async def delete_channel(self, channel_id: int, user: User) -> bool:
        """Delete a payment channel.

        Args:
            channel_id: Channel ID
            user: Current user

        Returns:
            True if deleted, False otherwise
        """
        channel = await self.db.get(PaymentChannel, channel_id)
        if not channel:
            return False

        if user.role == UserRole.MERCHANT and channel.user_id != user.id:
            return False

        await self.db.delete(channel)
        await self.db.commit()
        return True

    # ============ Available Channels (Payment API) ============

    async def find_available_channels(
        self,
        user: User,
        token_id: int,
        chain_id: int,
        amount: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find available channels for a payment amount.

        Args:
            user: Current user
            token_id: Token ID
            chain_id: Chain ID
            amount: Payment amount
            limit: Maximum channels to return

        Returns:
            List of available channels with addresses
        """
        payment_amount = Decimal(amount)

        query = select(PaymentChannel).where(
            PaymentChannel.token_id == token_id,
            PaymentChannel.chain_id == chain_id,
            PaymentChannel.status == ChannelStatus.ACTIVE,
            PaymentChannel.min_amount <= payment_amount,
            PaymentChannel.max_amount >= payment_amount,
        )

        if user.role == UserRole.MERCHANT:
            query = query.where(PaymentChannel.user_id == user.id)

        query = query.order_by(PaymentChannel.priority, PaymentChannel.daily_used)

        result = await self.db.execute(query)
        channels = list(result.scalars().all())

        # Filter by daily limit
        available: list[tuple[PaymentChannel, Decimal]] = []
        for channel in channels:
            channel.reset_daily_if_needed()
            remaining = channel.daily_limit - channel.daily_used
            if remaining >= payment_amount:
                available.append((channel, remaining))
                if len(available) >= limit:
                    break

        await self.db.commit()

        if not available:
            return []

        # Get related data
        wallet_ids = [c.wallet_id for c, _ in available]
        wallets_result = await self.db.execute(select(Wallet).where(Wallet.id.in_(wallet_ids)))
        wallets_map = {w.id: w for w in wallets_result.scalars()}

        token = await self.db.get(Token, token_id)
        chain = await self.db.get(Chain, chain_id)

        return [
            {
                "channel_id": channel.id,
                "wallet_address": wallets_map[channel.wallet_id].address,
                "chain_name": chain.name if chain else "",
                "token_symbol": token.symbol if token else "",
                "available_amount": str(remaining),
            }
            for channel, remaining in available
        ]

    # ============ Helper Methods ============

    async def _get_related_data(self, channels: list[PaymentChannel]) -> dict[str, dict[int, Any]]:
        """Get all related data for channels."""
        wallet_ids = [c.wallet_id for c in channels]
        token_ids = list(set(c.token_id for c in channels))
        chain_ids = list(set(c.chain_id for c in channels))
        user_ids = list(set(c.user_id for c in channels))

        result: dict[str, dict[int, Any]] = {
            "wallets": {},
            "tokens": {},
            "chains": {},
            "users": {},
        }

        if wallet_ids:
            wallets_result = await self.db.execute(select(Wallet).where(Wallet.id.in_(wallet_ids)))
            result["wallets"] = {w.id: w for w in wallets_result.scalars()}

        if token_ids:
            tokens_result = await self.db.execute(select(Token).where(Token.id.in_(token_ids)))
            result["tokens"] = {t.id: t for t in tokens_result.scalars()}

        if chain_ids:
            chains_result = await self.db.execute(select(Chain).where(Chain.id.in_(chain_ids)))
            result["chains"] = {c.id: c for c in chains_result.scalars()}

        if user_ids:
            users_result = await self.db.execute(select(User).where(User.id.in_(user_ids)))
            result["users"] = {u.id: u for u in users_result.scalars()}

        return result

    def _channel_to_dict(
        self,
        channel: PaymentChannel,
        related_data: dict[str, dict[int, Any]],
    ) -> dict[str, Any]:
        """Convert channel to response dict."""
        wallet = related_data["wallets"].get(channel.wallet_id)
        token = related_data["tokens"].get(channel.token_id)
        chain = related_data["chains"].get(channel.chain_id)
        owner = related_data["users"].get(channel.user_id)

        return {
            "id": channel.id,
            "user_id": channel.user_id,
            "wallet_id": channel.wallet_id,
            "token_id": channel.token_id,
            "chain_id": channel.chain_id,
            "status": channel.status.value,
            "min_amount": str(channel.min_amount),
            "max_amount": str(channel.max_amount),
            "daily_limit": str(channel.daily_limit),
            "balance_limit": str(channel.balance_limit),
            "daily_used": str(channel.daily_used),
            "priority": channel.priority,
            "label": channel.label,
            "created_at": channel.created_at.isoformat() if channel.created_at else "",
            "updated_at": channel.updated_at.isoformat() if channel.updated_at else "",
            "wallet_address": wallet.address if wallet else None,
            "token_symbol": token.symbol if token else None,
            "chain_name": chain.name if chain else None,
            "merchant_name": owner.email if owner else None,
        }
