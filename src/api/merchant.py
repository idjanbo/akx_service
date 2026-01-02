"""AKX Crypto Payment Gateway - Merchant API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.chains import get_chain
from src.db import get_db
from src.models.order import OrderStatus, OrderType
from src.models.user import User
from src.models.wallet import Chain
from src.schemas.merchant import (
    BalanceResponse,
    ChainBalanceResponse,
    CreateWalletRequest,
    CreateWithdrawalRequest,
    DepositAddressRequest,
    DepositAddressResponse,
    OrderListResponse,
    OrderResponse,
    WalletResponse,
)
from src.services.order_service import OrderService
from src.services.wallet_service import WalletService

router = APIRouter()


# ============ Wallet Endpoints ============


@router.post("/wallets", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def create_wallet(
    request: CreateWalletRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WalletResponse:
    """Create a new wallet for the authenticated merchant."""
    service = WalletService(db)
    wallet = await service.create_wallet(
        user_id=user.id,  # type: ignore
        chain=request.chain,
        label=request.label,
    )
    return WalletResponse.model_validate(wallet)


@router.get("/wallets", response_model=list[WalletResponse])
async def list_wallets(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    chain: Chain | None = None,
) -> list[WalletResponse]:
    """List all wallets for the authenticated merchant."""
    service = WalletService(db)
    wallets = await service.get_user_wallets(
        user_id=user.id,  # type: ignore
        chain=chain,
    )
    return [WalletResponse.model_validate(w) for w in wallets]


@router.post("/deposit-address", response_model=DepositAddressResponse)
async def get_deposit_address(
    request: DepositAddressRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepositAddressResponse:
    """Get or create a deposit address for the specified chain.

    If the merchant already has an active deposit wallet for the chain,
    returns that address. Otherwise creates a new one.
    """
    service = WalletService(db)
    wallet = await service.get_deposit_address(
        user_id=user.id,  # type: ignore
        chain=request.chain,
    )
    return DepositAddressResponse(
        chain=wallet.chain,
        address=wallet.address,
        label=wallet.label,
    )


@router.get("/wallets/{address}/balance", response_model=ChainBalanceResponse)
async def get_wallet_balance(
    address: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChainBalanceResponse:
    """Get on-chain balance for a wallet address.

    Queries the blockchain directly for current balance.
    """
    service = WalletService(db)
    wallet = await service.get_wallet_by_address(address)

    if not wallet or wallet.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    # Query blockchain
    chain_impl = get_chain(wallet.chain)
    balance = await chain_impl.get_balance(wallet.address)

    return ChainBalanceResponse(
        chain=wallet.chain,
        address=wallet.address,
        native_balance=balance.native_balance,
        usdt_balance=balance.usdt_balance,
    )


# ============ Order Endpoints ============


@router.post("/withdrawals", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_withdrawal(
    request: CreateWithdrawalRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrderResponse:
    """Create a withdrawal order.

    Requires sufficient balance. Fee will be deducted from the amount.
    """
    service = OrderService(db)

    try:
        order = await service.create_withdrawal(
            user_id=user.id,  # type: ignore
            chain=request.chain,
            to_address=request.to_address,
            amount=request.amount,
            merchant_ref=request.merchant_ref,
        )
        return OrderResponse.model_validate(order)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    order_type: OrderType | None = None,
    status: OrderStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> OrderListResponse:
    """List orders with pagination and filters."""
    service = OrderService(db)
    orders, total = await service.list_orders(
        user_id=user.id,  # type: ignore
        order_type=order_type,
        status=status,
        page=page,
        page_size=page_size,
    )

    return OrderListResponse(
        items=[OrderResponse.model_validate(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/orders/{order_no}", response_model=OrderResponse)
async def get_order(
    order_no: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrderResponse:
    """Get order details by order number."""
    service = OrderService(db)
    order = await service.get_order_by_no(
        order_no=order_no,
        user_id=user.id,  # type: ignore
    )

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return OrderResponse.model_validate(order)


# ============ Balance Endpoints ============


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BalanceResponse:
    """Get merchant's USDT balance.

    Balance is calculated from the transaction ledger.
    """
    service = OrderService(db)
    total = await service.get_user_balance(user.id)  # type: ignore
    frozen = await service.get_frozen_balance(user.id)  # type: ignore
    available = total - frozen

    return BalanceResponse(
        user_id=user.id,  # type: ignore
        available_balance=available,
        frozen_balance=frozen,
        total_balance=total,
    )
