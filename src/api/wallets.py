"""AKX - Wallets API endpoints.

This module provides REST API endpoints for wallet management.
Business logic is delegated to WalletService.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser
from src.db import get_db
from src.services.wallet_service import WalletService
from src.utils.pagination import PaginationParams

router = APIRouter()


# ============ Response Models ============


class WalletResponse(BaseModel):
    """Wallet response model."""

    id: int
    chain_id: int
    chain_name: str
    token_id: int | None = None
    token_symbol: str | None = None
    address: str
    source: str  # SYSTEM_GENERATED or MANUAL_IMPORT
    balance: str | None = None
    merchant_id: int | None = None
    merchant_name: str | None = None
    remark: str | None = None
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class PaginatedWalletsResponse(BaseModel):
    """Paginated wallets response."""

    items: list[WalletResponse]
    total: int
    page: int
    page_size: int


class GenerateWalletsRequest(BaseModel):
    """Request model for generating wallets."""

    chain_id: int = PydanticField(..., description="Chain ID to generate wallets for")
    token_id: int | None = PydanticField(
        None, description="Token ID (optional, defaults to primary stablecoin)"
    )
    count: int = PydanticField(1, ge=1, le=100, description="Number of addresses to generate")


class GenerateWalletsResponse(BaseModel):
    """Response model for generated wallets."""

    wallets: list[WalletResponse]
    count: int


class ImportWalletRequest(BaseModel):
    """Request model for importing a wallet."""

    chain_id: int = PydanticField(..., description="Chain ID")
    token_id: int | None = PydanticField(
        None, description="Token ID (optional, defaults to primary stablecoin)"
    )
    address: str = PydanticField(..., min_length=10, max_length=255, description="Wallet address")
    private_key: str = PydanticField(..., min_length=10, description="Private key")
    label: str | None = PydanticField(None, max_length=255, description="Optional label")


class UpdateWalletRequest(BaseModel):
    """Request model for updating a wallet."""

    label: str | None = PydanticField(None, max_length=255, description="Optional label")
    is_active: bool | None = PydanticField(None, description="Whether wallet is active")


# ============ Asset Summary Models ============


class AssetBalanceResponse(BaseModel):
    """Total asset balance overview."""

    amount: str
    base_asset: str
    fiat_symbol: str
    fiat_currency: str
    fiat_value: str
    today_change: str
    today_change_percent: str


class AssetResponse(BaseModel):
    """Single asset info."""

    symbol: str
    name: str
    amount: str
    fiat_symbol: str
    fiat_value: str


class AddressBalanceResponse(BaseModel):
    """Address balance info."""

    id: int
    address: str
    balance: str
    is_default: bool
    label: str | None = None


class ChainAddressGroupResponse(BaseModel):
    """Chain address group."""

    chain: str
    chain_id: int
    addresses: list[AddressBalanceResponse]


class AssetSummaryResponse(BaseModel):
    """Asset summary response."""

    balance: AssetBalanceResponse
    trend_data: list[float]
    assets: list[AssetResponse]
    asset_chains: dict[str, list[ChainAddressGroupResponse]]


# ============ Dependency ============


def get_wallet_service(db: Annotated[AsyncSession, Depends(get_db)]) -> WalletService:
    """Create WalletService instance."""
    return WalletService(db)


# ============ API Endpoints ============


@router.get("/assets/summary", response_model=AssetSummaryResponse)
async def get_asset_summary(
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> AssetSummaryResponse:
    """Get asset summary for the current user.

    Returns total balance, trend data, asset list, and addresses grouped by chain.
    """
    result = await service.get_asset_summary(user)
    return AssetSummaryResponse(**result)


@router.get("", response_model=PaginatedWalletsResponse)
async def list_wallets(
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
    chain_id: int | None = None,
    token_id: int | None = None,
    source: str | None = None,
    is_active: bool | None = None,
    search: str | None = Query(None, description="Search by address or remark"),
    user_id: int | None = Query(None, description="Filter by user ID (admin only)"),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedWalletsResponse:
    """List wallets with filters.

    Merchants can only see their own wallets.
    Admins can see all wallets and filter by user_id.
    """
    params = PaginationParams(page=page, page_size=page_size)
    result = await service.list_wallets(
        user=user,
        params=params,
        chain_id=chain_id,
        token_id=token_id,
        source=source,
        is_active=is_active,
        search=search,
        user_id=user_id,
    )
    return PaginatedWalletsResponse(
        items=[WalletResponse(**item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.post("/generate", response_model=GenerateWalletsResponse)
async def generate_wallets(
    request: GenerateWalletsRequest,
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> GenerateWalletsResponse:
    """Generate new wallet addresses for a chain.

    This creates system-generated deposit wallets.
    """
    try:
        wallets, chain = await service.generate_wallets(
            user=user,
            chain_id=request.chain_id,
            count=request.count,
            token_id=request.token_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    # Convert Wallet objects to response dicts
    wallet_responses = []
    for w in wallets:
        wallet_responses.append(
            WalletResponse(
                id=w.id,
                chain_id=w.chain_id,
                chain_name=chain.name,
                token_id=w.token_id,
                token_symbol=None,  # TODO: get from token
                address=w.address,
                source="SYSTEM_GENERATED",
                balance=w.balance,
                merchant_id=w.user_id,
                merchant_name=None,  # TODO: get from user
                remark=w.label,
                is_active=w.is_active,
                created_at=w.created_at.isoformat(),
            )
        )

    return GenerateWalletsResponse(
        wallets=wallet_responses,
        count=len(wallets),
    )


@router.post("/import", response_model=WalletResponse)
async def import_wallet(
    request: ImportWalletRequest,
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> WalletResponse:
    """Import an existing wallet with private key.

    Security Note: Private key is encrypted before storage.
    """
    try:
        result = await service.import_wallet(
            user=user,
            chain_id=request.chain_id,
            address=request.address,
            private_key=request.private_key,
            token_id=request.token_id,
            label=request.label,
        )
    except ValueError as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg)
        elif "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    return WalletResponse(**result)


@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: int,
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> WalletResponse:
    """Get a single wallet by ID."""
    result = await service.get_wallet(wallet_id, user)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return WalletResponse(**result)


@router.patch("/{wallet_id}", response_model=WalletResponse)
async def update_wallet(
    wallet_id: int,
    request: UpdateWalletRequest,
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> WalletResponse:
    """Update a wallet's label or status."""
    result = await service.update_wallet(
        wallet_id=wallet_id,
        user=user,
        label=request.label,
        is_active=request.is_active,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return WalletResponse(**result)


@router.delete("/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet(
    wallet_id: int,
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
) -> None:
    """Delete a wallet.

    Note: Only wallets with zero balance can be deleted for safety.
    """
    try:
        deleted = await service.delete_wallet(wallet_id, user)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============ Deposit Address Endpoints ============


class DepositAddressResponse(BaseModel):
    """Deposit address response for online recharge."""

    address: str
    chain_code: str
    chain_name: str
    token_code: str
    token_symbol: str
    qr_content: str  # Content for QR code (usually just the address)
    min_deposit: str | None = None
    confirmations: int


@router.get("/deposit-address", response_model=DepositAddressResponse)
async def get_deposit_address(
    user: CurrentUser,
    service: Annotated[WalletService, Depends(get_wallet_service)],
    chain_code: str = Query(..., description="Chain code (e.g., TRON, ETH)"),
    token_code: str = Query(default="usdt", description="Token code (e.g., usdt, usdc)"),
) -> DepositAddressResponse:
    """Get or create a deposit address for online recharge.

    Returns an existing active deposit address or creates a new one.
    """
    try:
        result = await service.get_or_create_deposit_address(
            user=user,
            chain_code=chain_code.upper(),
            token_code=token_code.lower(),
        )
        return DepositAddressResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
