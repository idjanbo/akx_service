"""AKX - Unified orders API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, or_, select

from src.api.auth import get_current_user
from src.db import get_db
from src.models.order import Order, OrderStatus, OrderType
from src.models.user import User, UserRole

router = APIRouter()


class OrderResponse(BaseModel):
    """Order response model."""

    id: int
    order_no: str
    merchant_id: int | None
    merchant_name: str | None
    merchant_ref: str | None
    type: str
    amount: str
    chain: str
    token: str
    status: str
    tx_hash: str | None
    wallet_address: str | None
    callback_url: str | None
    callback_status: str | None
    fee: str | None
    net_amount: str | None
    to_address: str | None
    confirmations: int | None
    created_at: str
    updated_at: str
    completed_at: str | None

    class Config:
        from_attributes = True


class PaginatedOrdersResponse(BaseModel):
    """Paginated orders response."""

    items: list[OrderResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=PaginatedOrdersResponse)
async def list_orders(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    type: OrderType | None = None,
    status: OrderStatus | None = None,
    chain: str | None = None,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedOrdersResponse:
    """List orders with filters.

    Merchants can only see their own orders.
    Admins can see all orders.
    """
    query = select(Order)

    # Filter by user role
    if user.role == UserRole.MERCHANT:
        query = query.where(Order.user_id == user.id)

    # Apply filters
    if type:
        query = query.where(Order.order_type == type)
    if status:
        query = query.where(Order.status == status)
    if chain:
        query = query.where(Order.chain == chain)
    if search:
        query = query.where(
            or_(
                Order.order_no.contains(search),  # type: ignore
                Order.merchant_ref.contains(search),  # type: ignore
                Order.tx_hash.contains(search),  # type: ignore
            )
        )

    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    orders = result.scalars().all()

    # Get user names (merchants)
    user_ids = list({o.user_id for o in orders if o.user_id})
    user_names = {}
    if user_ids:
        from src.models.user import User as UserModel

        users_result = await db.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
        for u in users_result.scalars():
            user_names[u.id] = u.email  # type: ignore

    return PaginatedOrdersResponse(
        items=[
            OrderResponse(
                id=o.id,  # type: ignore
                order_no=o.order_no,
                merchant_id=o.user_id,
                merchant_name=user_names.get(o.user_id) if o.user_id else None,
                merchant_ref=o.merchant_ref,
                type=o.order_type.value,
                amount=str(o.amount),
                chain=o.chain,
                token=o.token,
                status=o.status.value,
                tx_hash=o.tx_hash,
                wallet_address=o.wallet_address,
                callback_url=o.callback_url,
                callback_status=o.callback_status.value if o.callback_status else None,
                fee=str(o.fee) if o.fee else None,
                net_amount=str(o.net_amount) if o.net_amount else None,
                to_address=o.to_address,
                confirmations=o.confirmations,
                created_at=o.created_at.isoformat() if o.created_at else "",
                updated_at=o.updated_at.isoformat() if o.updated_at else "",
                completed_at=o.completed_at.isoformat() if o.completed_at else None,
            )
            for o in orders
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrderResponse:
    """Get order details."""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Check permissions
    if user.role == UserRole.MERCHANT and order.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # Get merchant name
    merchant_name = None
    if order.user_id:
        user_result = await db.execute(select(User).where(User.id == order.user_id))
        merchant = user_result.scalar_one_or_none()
        merchant_name = merchant.email if merchant else None

    return OrderResponse(
        id=order.id,  # type: ignore
        order_no=order.order_no,
        merchant_id=order.user_id,
        merchant_name=merchant_name,
        merchant_ref=order.merchant_ref,
        type=order.order_type.value,
        amount=str(order.amount),
        chain=order.chain,
        token=order.token,
        status=order.status.value,
        tx_hash=order.tx_hash,
        wallet_address=order.wallet_address,
        callback_url=order.callback_url,
        callback_status=order.callback_status.value if order.callback_status else None,
        fee=str(order.fee) if order.fee else None,
        net_amount=str(order.net_amount) if order.net_amount else None,
        to_address=order.to_address,
        confirmations=order.confirmations,
        created_at=order.created_at.isoformat() if order.created_at else "",
        updated_at=order.updated_at.isoformat() if order.updated_at else "",
        completed_at=order.completed_at.isoformat() if order.completed_at else None,
    )
