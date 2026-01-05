"""AKX Crypto Payment Gateway - Payment Channels API.

Provides CRUD operations for payment channel management.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.db.engine import get_db
from src.models.chain import Chain
from src.models.payment_channel import ChannelStatus, PaymentChannel
from src.models.token import Token
from src.models.user import User, UserRole
from src.models.wallet import Wallet

router = APIRouter(prefix="/payment-channels", tags=["Payment Channels"])


# ============ Request/Response Models ============


class PaymentChannelResponse(BaseModel):
    """Response model for payment channel."""

    id: int
    user_id: int
    wallet_id: int
    token_id: int
    chain_id: int
    status: str
    min_amount: str
    max_amount: str
    daily_limit: str
    balance_limit: str
    daily_used: str
    priority: int
    label: str | None
    created_at: str
    updated_at: str
    # Joined fields
    wallet_address: str | None = None
    token_symbol: str | None = None
    chain_name: str | None = None
    merchant_name: str | None = None


class PaginatedChannelsResponse(BaseModel):
    """Paginated response for payment channels."""

    items: list[PaymentChannelResponse]
    total: int
    page: int
    page_size: int


class CreateChannelRequest(BaseModel):
    """Request model for creating a payment channel."""

    wallet_ids: list[int] = PydanticField(
        ..., min_length=1, description="Wallet IDs to create channels for"
    )
    token_id: int = PydanticField(..., description="Token ID")
    chain_id: int = PydanticField(..., description="Chain ID")
    min_amount: str = PydanticField("0", description="Minimum payment amount")
    max_amount: str = PydanticField("999999999", description="Maximum payment amount")
    daily_limit: str = PydanticField("999999999", description="Daily transaction limit")
    balance_limit: str = PydanticField("999999999", description="Balance limit threshold")
    priority: int = PydanticField(
        100, ge=1, le=1000, description="Priority (1-1000, lower = higher priority)"
    )
    label: str | None = PydanticField(None, max_length=255, description="Optional label")


class UpdateChannelRequest(BaseModel):
    """Request model for updating a payment channel."""

    status: str | None = PydanticField(None, description="Channel status")
    min_amount: str | None = PydanticField(None, description="Minimum payment amount")
    max_amount: str | None = PydanticField(None, description="Maximum payment amount")
    daily_limit: str | None = PydanticField(None, description="Daily transaction limit")
    balance_limit: str | None = PydanticField(None, description="Balance limit threshold")
    priority: int | None = PydanticField(None, ge=1, le=1000, description="Priority")
    label: str | None = PydanticField(None, max_length=255, description="Optional label")


class BatchCreateResponse(BaseModel):
    """Response for batch channel creation."""

    created: int
    channels: list[PaymentChannelResponse]


class AvailableChannelResponse(BaseModel):
    """Response for available channel query (for payment API)."""

    channel_id: int
    wallet_address: str
    chain_name: str
    token_symbol: str
    available_amount: str  # How much more can be processed today


# ============ Helper Functions ============


def _channel_to_response(
    channel: PaymentChannel,
    wallet: Wallet | None = None,
    token: Token | None = None,
    chain: Chain | None = None,
    user: User | None = None,
) -> PaymentChannelResponse:
    """Convert PaymentChannel model to response."""
    return PaymentChannelResponse(
        id=channel.id,  # type: ignore
        user_id=channel.user_id,
        wallet_id=channel.wallet_id,
        token_id=channel.token_id,
        chain_id=channel.chain_id,
        status=channel.status.value,
        min_amount=str(channel.min_amount),
        max_amount=str(channel.max_amount),
        daily_limit=str(channel.daily_limit),
        balance_limit=str(channel.balance_limit),
        daily_used=str(channel.daily_used),
        priority=channel.priority,
        label=channel.label,
        created_at=channel.created_at.isoformat() if channel.created_at else "",
        updated_at=channel.updated_at.isoformat() if channel.updated_at else "",
        wallet_address=wallet.address if wallet else None,
        token_symbol=token.symbol if token else None,
        chain_name=chain.name if chain else None,
        merchant_name=user.email if user else None,
    )


# ============ API Endpoints ============


@router.get("", response_model=PaginatedChannelsResponse)
async def list_channels(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    token_id: int | None = None,
    chain_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedChannelsResponse:
    """List payment channels with optional filters."""
    # Build query
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

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    query = query.order_by(PaymentChannel.priority, PaymentChannel.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    channels = result.scalars().all()

    # Get related data
    wallet_ids = [c.wallet_id for c in channels]
    token_ids = list(set(c.token_id for c in channels))
    chain_ids = list(set(c.chain_id for c in channels))
    user_ids = list(set(c.user_id for c in channels))

    # Fetch wallets
    wallets_map: dict[int, Wallet] = {}
    if wallet_ids:
        wallets_result = await db.execute(select(Wallet).where(Wallet.id.in_(wallet_ids)))
        wallets_map = {w.id: w for w in wallets_result.scalars()}  # type: ignore

    # Fetch tokens
    tokens_map: dict[int, Token] = {}
    if token_ids:
        tokens_result = await db.execute(select(Token).where(Token.id.in_(token_ids)))
        tokens_map = {t.id: t for t in tokens_result.scalars()}  # type: ignore

    # Fetch chains
    chains_map: dict[int, Chain] = {}
    if chain_ids:
        chains_result = await db.execute(select(Chain).where(Chain.id.in_(chain_ids)))
        chains_map = {c.id: c for c in chains_result.scalars()}  # type: ignore

    # Fetch users
    users_map: dict[int, User] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users_map = {u.id: u for u in users_result.scalars()}  # type: ignore

    return PaginatedChannelsResponse(
        items=[
            _channel_to_response(
                c,
                wallets_map.get(c.wallet_id),
                tokens_map.get(c.token_id),
                chains_map.get(c.chain_id),
                users_map.get(c.user_id),
            )
            for c in channels
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=BatchCreateResponse)
async def create_channels(
    request: CreateChannelRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchCreateResponse:
    """Create payment channels for multiple wallets.

    This allows batch creation of channels with the same limits.
    """
    # Verify token exists
    token = await db.get(Token, request.token_id)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token with id {request.token_id} not found",
        )

    # Verify chain exists
    chain = await db.get(Chain, request.chain_id)
    if not chain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chain with id {request.chain_id} not found",
        )

    # Verify all wallets exist and belong to user (if merchant)
    wallets_query = select(Wallet).where(Wallet.id.in_(request.wallet_ids))
    if user.role == UserRole.MERCHANT:
        wallets_query = wallets_query.where(Wallet.user_id == user.id)

    wallets_result = await db.execute(wallets_query)
    wallets = {w.id: w for w in wallets_result.scalars()}  # type: ignore

    if len(wallets) != len(request.wallet_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some wallets not found or not accessible",
        )

    # Check for existing channels with same wallet
    existing_query = select(PaymentChannel).where(
        PaymentChannel.wallet_id.in_(request.wallet_ids),
        PaymentChannel.token_id == request.token_id,
        PaymentChannel.chain_id == request.chain_id,
    )
    existing_result = await db.execute(existing_query)
    existing_wallet_ids = {c.wallet_id for c in existing_result.scalars()}

    # Create channels
    created_channels: list[PaymentChannel] = []
    for wallet_id in request.wallet_ids:
        if wallet_id in existing_wallet_ids:
            continue  # Skip if channel already exists

        wallet = wallets[wallet_id]
        channel = PaymentChannel(
            user_id=wallet.user_id or user.id,  # type: ignore
            wallet_id=wallet_id,
            token_id=request.token_id,
            chain_id=request.chain_id,
            min_amount=Decimal(request.min_amount),
            max_amount=Decimal(request.max_amount),
            daily_limit=Decimal(request.daily_limit),
            balance_limit=Decimal(request.balance_limit),
            priority=request.priority,
            label=request.label,
        )
        db.add(channel)
        created_channels.append(channel)

    await db.commit()

    # Refresh to get IDs
    for c in created_channels:
        await db.refresh(c)

    return BatchCreateResponse(
        created=len(created_channels),
        channels=[
            _channel_to_response(c, wallets.get(c.wallet_id), token, chain, user)
            for c in created_channels
        ],
    )


@router.get("/{channel_id}", response_model=PaymentChannelResponse)
async def get_channel(
    channel_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentChannelResponse:
    """Get a specific payment channel."""
    channel = await db.get(PaymentChannel, channel_id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    # Check access
    if user.role == UserRole.MERCHANT and channel.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get related data
    wallet = await db.get(Wallet, channel.wallet_id)
    token = await db.get(Token, channel.token_id)
    chain = await db.get(Chain, channel.chain_id)
    owner = await db.get(User, channel.user_id)

    return _channel_to_response(channel, wallet, token, chain, owner)


@router.patch("/{channel_id}", response_model=PaymentChannelResponse)
async def update_channel(
    channel_id: int,
    request: UpdateChannelRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentChannelResponse:
    """Update a payment channel."""
    channel = await db.get(PaymentChannel, channel_id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    # Check access
    if user.role == UserRole.MERCHANT and channel.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Update fields
    if request.status is not None:
        try:
            channel.status = ChannelStatus(request.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {request.status}",
            )

    if request.min_amount is not None:
        channel.min_amount = Decimal(request.min_amount)
    if request.max_amount is not None:
        channel.max_amount = Decimal(request.max_amount)
    if request.daily_limit is not None:
        channel.daily_limit = Decimal(request.daily_limit)
    if request.balance_limit is not None:
        channel.balance_limit = Decimal(request.balance_limit)
    if request.priority is not None:
        channel.priority = request.priority
    if request.label is not None:
        channel.label = request.label

    channel.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(channel)

    # Get related data
    wallet = await db.get(Wallet, channel.wallet_id)
    token = await db.get(Token, channel.token_id)
    chain = await db.get(Chain, channel.chain_id)
    owner = await db.get(User, channel.user_id)

    return _channel_to_response(channel, wallet, token, chain, owner)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a payment channel."""
    channel = await db.get(PaymentChannel, channel_id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    # Check access
    if user.role == UserRole.MERCHANT and channel.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    await db.delete(channel)
    await db.commit()


@router.get("/available/find", response_model=list[AvailableChannelResponse])
async def find_available_channels(
    token_id: int,
    chain_id: int,
    amount: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(5, ge=1, le=20),
) -> list[AvailableChannelResponse]:
    """Find available payment channels for a given amount.

    This endpoint is used by the payment API to find suitable addresses.
    It returns channels that can accept the specified amount, sorted by priority.
    """
    payment_amount = Decimal(amount)

    # Query active channels matching criteria
    query = select(PaymentChannel).where(
        PaymentChannel.token_id == token_id,
        PaymentChannel.chain_id == chain_id,
        PaymentChannel.status == ChannelStatus.ACTIVE,
        PaymentChannel.min_amount <= payment_amount,
        PaymentChannel.max_amount >= payment_amount,
    )

    # Role-based filtering
    if user.role == UserRole.MERCHANT:
        query = query.where(PaymentChannel.user_id == user.id)

    query = query.order_by(PaymentChannel.priority, PaymentChannel.daily_used)

    result = await db.execute(query)
    channels = list(result.scalars().all())

    # Filter by daily limit and reset if needed
    available_channels: list[tuple[PaymentChannel, Decimal]] = []
    for channel in channels:
        channel.reset_daily_if_needed()

        remaining = channel.daily_limit - channel.daily_used
        if remaining >= payment_amount:
            available_channels.append((channel, remaining))
            if len(available_channels) >= limit:
                break

    # Commit any daily resets
    await db.commit()

    if not available_channels:
        return []

    # Get related data
    wallet_ids = [c.wallet_id for c, _ in available_channels]
    wallets_result = await db.execute(select(Wallet).where(Wallet.id.in_(wallet_ids)))
    wallets_map = {w.id: w for w in wallets_result.scalars()}  # type: ignore

    token = await db.get(Token, token_id)
    chain = await db.get(Chain, chain_id)

    return [
        AvailableChannelResponse(
            channel_id=channel.id,  # type: ignore
            wallet_address=wallets_map[channel.wallet_id].address,
            chain_name=chain.name if chain else "",
            token_symbol=token.symbol if token else "",
            available_amount=str(remaining),
        )
        for channel, remaining in available_channels
    ]
