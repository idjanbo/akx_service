"""AKX Crypto Payment Gateway - Admin API endpoints.

Super Admin only endpoints for system management.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from src.api.auth import get_current_user
from src.chains import get_chain
from src.core.security import encrypt_private_key
from src.db import get_db
from src.models.order import Order, OrderStatus, OrderType
from src.models.user import User, UserRole
from src.models.wallet import Chain, Wallet, WalletType
from src.schemas.admin import (
    ChainStatsResponse,
    CreateSystemWalletRequest,
    DashboardStatsResponse,
    ImportWalletRequest,
    SystemWalletResponse,
    UpdateUserRequest,
    UserListResponse,
    UserResponse,
)

router = APIRouter()


# ============ Dependency for Admin Access ============


async def get_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Require SUPER_ADMIN role."""
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required",
        )
    return user


# ============ User Management ============


@router.get("/users", response_model=UserListResponse)
async def list_users(
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: UserRole | None = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserListResponse:
    """List all users with filters."""
    query = select(User)

    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    users = result.scalars().all()

    return UserListResponse(
        items=[
            UserResponse(
                id=u.id,  # type: ignore
                clerk_id=u.clerk_id,
                email=u.email,
                role=u.role,
                is_active=u.is_active,
                has_totp=bool(u.google_secret),
                created_at=u.created_at,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Get user details."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(
        id=user.id,  # type: ignore
        clerk_id=user.clerk_id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        has_totp=bool(user.google_secret),
        created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Update user role or status."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent self-demotion
    if user.id == admin.id and request.role and request.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote yourself",
        )

    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active

    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,  # type: ignore
        clerk_id=user.clerk_id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        has_totp=bool(user.google_secret),
        created_at=user.created_at,
    )


# ============ System Wallet Management ============


@router.get("/wallets/system", response_model=list[SystemWalletResponse])
async def list_system_wallets(
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    chain: Chain | None = None,
    wallet_type: WalletType | None = None,
) -> list[SystemWalletResponse]:
    """List system wallets (gas and cold)."""
    query = select(Wallet).where(
        Wallet.user_id == None,  # noqa: E711
        Wallet.wallet_type.in_([WalletType.GAS, WalletType.COLD]),
    )

    if chain:
        query = query.where(Wallet.chain == chain)
    if wallet_type:
        query = query.where(Wallet.wallet_type == wallet_type)

    result = await db.execute(query)
    wallets = result.scalars().all()

    return [SystemWalletResponse.model_validate(w) for w in wallets]


@router.post(
    "/wallets/system",
    response_model=SystemWalletResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_system_wallet(
    request: CreateSystemWalletRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SystemWalletResponse:
    """Create a new system wallet (generates new keypair)."""
    if request.wallet_type not in [WalletType.GAS, WalletType.COLD]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System wallets must be GAS or COLD type",
        )

    # Generate wallet
    chain_impl = get_chain(request.chain)
    wallet_info = chain_impl.generate_wallet()

    # Encrypt private key
    encrypted_key = encrypt_private_key(wallet_info.private_key)

    # Create wallet record
    wallet = Wallet(
        user_id=None,  # System wallet
        chain=request.chain,
        address=wallet_info.address,
        encrypted_private_key=encrypted_key,
        wallet_type=request.wallet_type,
        label=request.label or f"{request.chain.value.upper()} {request.wallet_type.value}",
        is_active=True,
    )

    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)

    return SystemWalletResponse.model_validate(wallet)


@router.post(
    "/wallets/import",
    response_model=SystemWalletResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_wallet(
    request: ImportWalletRequest,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SystemWalletResponse:
    """Import existing wallet with private key."""
    # Validate address
    chain_impl = get_chain(request.chain)
    if not chain_impl.validate_address(request.address):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {request.chain.value} address",
        )

    # Check if address already exists
    existing = await db.execute(
        select(Wallet).where(Wallet.address == request.address)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wallet already exists",
        )

    # Encrypt private key
    encrypted_key = encrypt_private_key(request.private_key)

    # Create wallet
    wallet = Wallet(
        user_id=None,  # System wallet
        chain=request.chain,
        address=request.address,
        encrypted_private_key=encrypted_key,
        wallet_type=request.wallet_type,
        label=request.label,
        is_active=True,
    )

    db.add(wallet)
    await db.commit()
    await db.refresh(wallet)

    return SystemWalletResponse.model_validate(wallet)


# ============ Dashboard & Statistics ============


@router.get("/dashboard", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardStatsResponse:
    """Get dashboard statistics."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    # Total users
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    # Active merchants
    active_merchants_result = await db.execute(
        select(func.count(User.id)).where(
            User.role == UserRole.MERCHANT,
            User.is_active == True,  # noqa: E712
        )
    )
    active_merchants = active_merchants_result.scalar() or 0

    # Deposits 24h
    deposits_24h_result = await db.execute(
        select(func.sum(Order.amount)).where(
            Order.order_type == OrderType.DEPOSIT,
            Order.status == OrderStatus.SUCCESS,
            Order.created_at >= yesterday,
        )
    )
    total_deposits_24h = deposits_24h_result.scalar() or Decimal("0")

    # Withdrawals 24h
    withdrawals_24h_result = await db.execute(
        select(func.sum(Order.amount)).where(
            Order.order_type == OrderType.WITHDRAWAL,
            Order.status == OrderStatus.SUCCESS,
            Order.created_at >= yesterday,
        )
    )
    total_withdrawals_24h = withdrawals_24h_result.scalar() or Decimal("0")

    # Pending orders
    pending_result = await db.execute(
        select(func.count(Order.id)).where(
            Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMING, OrderStatus.PROCESSING])
        )
    )
    pending_orders = pending_result.scalar() or 0

    # Success rate 7d
    total_7d_result = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= week_ago)
    )
    total_7d = total_7d_result.scalar() or 1

    success_7d_result = await db.execute(
        select(func.count(Order.id)).where(
            Order.status == OrderStatus.SUCCESS,
            Order.created_at >= week_ago,
        )
    )
    success_7d = success_7d_result.scalar() or 0

    success_rate = Decimal(success_7d) / Decimal(total_7d) * 100 if total_7d > 0 else Decimal("0")

    return DashboardStatsResponse(
        total_users=total_users,
        active_merchants=active_merchants,
        total_deposits_24h=total_deposits_24h,
        total_withdrawals_24h=total_withdrawals_24h,
        pending_orders=pending_orders,
        success_rate_7d=round(success_rate, 2),
    )


@router.get("/stats/chains", response_model=list[ChainStatsResponse])
async def get_chain_stats(
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ChainStatsResponse]:
    """Get per-chain statistics."""
    stats = []

    for chain in Chain:
        # Count deposit wallets
        wallet_count_result = await db.execute(
            select(func.count(Wallet.id)).where(
                Wallet.chain == chain,
                Wallet.wallet_type == WalletType.DEPOSIT,
            )
        )
        deposit_wallet_count = wallet_count_result.scalar() or 0

        # Total deposit volume
        deposit_volume_result = await db.execute(
            select(func.sum(Order.amount)).where(
                Order.chain == chain.value,
                Order.order_type == OrderType.DEPOSIT,
                Order.status == OrderStatus.SUCCESS,
            )
        )
        deposit_volume = deposit_volume_result.scalar() or Decimal("0")

        # Total withdrawal volume
        withdrawal_volume_result = await db.execute(
            select(func.sum(Order.amount)).where(
                Order.chain == chain.value,
                Order.order_type == OrderType.WITHDRAWAL,
                Order.status == OrderStatus.SUCCESS,
            )
        )
        withdrawal_volume = withdrawal_volume_result.scalar() or Decimal("0")

        # Get cold wallet balance
        cold_balance = Decimal("0")
        gas_balance = Decimal("0")

        try:
            chain_impl = get_chain(chain)

            # Cold wallet
            cold_result = await db.execute(
                select(Wallet).where(
                    Wallet.chain == chain,
                    Wallet.wallet_type == WalletType.COLD,
                    Wallet.user_id == None,  # noqa: E711
                )
            )
            cold_wallet = cold_result.scalar_one_or_none()
            if cold_wallet:
                balance = await chain_impl.get_balance(cold_wallet.address)
                cold_balance = balance.usdt_balance

            # Gas wallet
            gas_result = await db.execute(
                select(Wallet).where(
                    Wallet.chain == chain,
                    Wallet.wallet_type == WalletType.GAS,
                    Wallet.user_id == None,  # noqa: E711
                )
            )
            gas_wallet = gas_result.scalar_one_or_none()
            if gas_wallet:
                balance = await chain_impl.get_balance(gas_wallet.address)
                gas_balance = balance.native_balance

        except NotImplementedError:
            pass  # Chain not implemented yet

        stats.append(
            ChainStatsResponse(
                chain=chain,
                total_deposit_wallets=deposit_wallet_count,
                total_deposit_volume=deposit_volume,
                total_withdrawal_volume=withdrawal_volume,
                cold_wallet_balance=cold_balance,
                gas_wallet_balance=gas_balance,
            )
        )

    return stats
