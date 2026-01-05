"""AKX Crypto Payment Gateway - Payment Channels API.

Provides REST API endpoints for payment channel management.
Business logic is delegated to ChannelService.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.db.engine import get_db
from src.models.user import User
from src.services.channel_service import ChannelService
from src.utils.pagination import PaginationParams

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
    label: str | None = None
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


# ============ Dependency ============


def get_channel_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChannelService:
    """Create ChannelService instance."""
    return ChannelService(db)


# ============ API Endpoints ============


@router.get("", response_model=PaginatedChannelsResponse)
async def list_channels(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChannelService, Depends(get_channel_service)],
    token_id: int | None = None,
    chain_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedChannelsResponse:
    """List payment channels with optional filters."""
    params = PaginationParams(page=page, page_size=page_size)
    result = await service.list_channels(
        user=user,
        params=params,
        token_id=token_id,
        chain_id=chain_id,
        status_filter=status_filter,
    )
    return PaginatedChannelsResponse(
        items=[PaymentChannelResponse(**item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post("", response_model=BatchCreateResponse)
async def create_channels(
    request: CreateChannelRequest,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> BatchCreateResponse:
    """Create payment channels for multiple wallets.

    This allows batch creation of channels with the same limits.
    """
    try:
        channels, token, chain = await service.create_channels(
            user=user,
            wallet_ids=request.wallet_ids,
            token_id=request.token_id,
            chain_id=request.chain_id,
            min_amount=request.min_amount,
            max_amount=request.max_amount,
            daily_limit=request.daily_limit,
            balance_limit=request.balance_limit,
            priority=request.priority,
            label=request.label,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    return BatchCreateResponse(
        created=len(channels),
        channels=[
            PaymentChannelResponse(
                id=c.id,  # type: ignore
                user_id=c.user_id,
                wallet_id=c.wallet_id,
                token_id=c.token_id,
                chain_id=c.chain_id,
                status=c.status.value,
                min_amount=str(c.min_amount),
                max_amount=str(c.max_amount),
                daily_limit=str(c.daily_limit),
                balance_limit=str(c.balance_limit),
                daily_used=str(c.daily_used),
                priority=c.priority,
                label=c.label,
                created_at=c.created_at.isoformat() if c.created_at else "",
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
                token_symbol=token.symbol,
                chain_name=chain.name,
                merchant_name=user.email,
            )
            for c in channels
        ],
    )


@router.get("/{channel_id}", response_model=PaymentChannelResponse)
async def get_channel(
    channel_id: int,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> PaymentChannelResponse:
    """Get a specific payment channel."""
    result = await service.get_channel(channel_id, user)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return PaymentChannelResponse(**result)


@router.patch("/{channel_id}", response_model=PaymentChannelResponse)
async def update_channel(
    channel_id: int,
    request: UpdateChannelRequest,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> PaymentChannelResponse:
    """Update a payment channel."""
    try:
        result = await service.update_channel(
            channel_id=channel_id,
            user=user,
            status=request.status,
            min_amount=request.min_amount,
            max_amount=request.max_amount,
            daily_limit=request.daily_limit,
            balance_limit=request.balance_limit,
            priority=request.priority,
            label=request.label,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return PaymentChannelResponse(**result)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChannelService, Depends(get_channel_service)],
) -> None:
    """Delete a payment channel."""
    deleted = await service.delete_channel(channel_id, user)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")


@router.get("/available/find", response_model=list[AvailableChannelResponse])
async def find_available_channels(
    token_id: int,
    chain_id: int,
    amount: str,
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ChannelService, Depends(get_channel_service)],
    limit: int = Query(5, ge=1, le=20),
) -> list[AvailableChannelResponse]:
    """Find available payment channels for a given amount.

    This endpoint is used by the payment API to find suitable addresses.
    It returns channels that can accept the specified amount, sorted by priority.
    """
    results = await service.find_available_channels(
        user=user,
        token_id=token_id,
        chain_id=chain_id,
        amount=amount,
        limit=limit,
    )
    return [AvailableChannelResponse(**item) for item in results]
