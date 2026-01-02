"""AKX - Wallets API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from src.api.auth import get_current_user
from src.db import get_db
from src.models.user import User, UserRole
from src.models.wallet import Chain, Wallet, WalletType

router = APIRouter()


class WalletResponse(BaseModel):
    """Wallet response model."""

    id: int
    chain: str
    address: str
    source: str  # SYSTEM_GENERATED or MANUAL_IMPORT
    balance: str | None
    merchant_id: int | None
    merchant_name: str | None
    remark: str | None
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


@router.get("", response_model=PaginatedWalletsResponse)
async def list_wallets(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    chain: Chain | None = None,
    source: str | None = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedWalletsResponse:
    """List wallets with filters.

    Merchants can only see their own wallets.
    Admins can see all wallets.
    """
    query = select(Wallet)

    # Filter by user role
    if user.role == UserRole.MERCHANT:
        query = query.where(Wallet.user_id == user.id)

    # Apply filters
    if chain:
        query = query.where(Wallet.chain == chain)
    if source:
        if source == "SYSTEM_GENERATED":
            query = query.where(Wallet.wallet_type == WalletType.DEPOSIT)
        elif source == "MANUAL_IMPORT":
            query = query.where(Wallet.wallet_type == WalletType.MERCHANT)
    if is_active is not None:
        query = query.where(Wallet.is_active == is_active)

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(Wallet.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    wallets = result.scalars().all()

    # Get user names (merchants)
    user_ids = list({w.user_id for w in wallets if w.user_id})
    user_names = {}
    if user_ids:
        from src.models.user import User as UserModel

        users_result = await db.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
        for u in users_result.scalars():
            user_names[u.id] = u.email  # type: ignore

    return PaginatedWalletsResponse(
        items=[
            WalletResponse(
                id=w.id,  # type: ignore
                chain=w.chain.value,
                address=w.address,
                source=(
                    "SYSTEM_GENERATED"
                    if w.wallet_type == WalletType.DEPOSIT
                    else "MANUAL_IMPORT"
                ),
                balance=None,  # TODO: Fetch from chain
                merchant_id=w.user_id,
                merchant_name=user_names.get(w.user_id) if w.user_id else None,
                remark=w.label,
                is_active=w.is_active,
                created_at=w.created_at.isoformat() if w.created_at else "",
            )
            for w in wallets
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
