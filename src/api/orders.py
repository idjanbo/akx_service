"""Order management API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, TOTPUser, totp_required
from src.db.engine import get_db
from src.models.order import CallbackStatus, OrderStatus, OrderType
from src.schemas.order import (
    ForceCompleteRequest,
    OrderActionResponse,
    OrderListResponse,
    OrderQueryParams,
    OrderResponse,
)
from src.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


def get_order_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrderService:
    """Create OrderService instance."""
    return OrderService(db)


# ============ Deposit Orders ============


@router.get("/deposits", response_model=OrderListResponse)
async def list_deposit_orders(
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    order_no: str | None = Query(default=None, description="Order number (partial match)"),
    out_trade_no: str | None = Query(default=None, description="External trade number"),
    merchant_id: int | None = Query(default=None, description="Merchant ID"),
    token: str | None = Query(default=None, description="Token code"),
    chain: str | None = Query(default=None, description="Chain code"),
    status: OrderStatus | None = Query(default=None, description="Order status"),
    callback_status: CallbackStatus | None = Query(default=None, description="Callback status"),
    tx_hash: str | None = Query(default=None, description="Transaction hash"),
) -> OrderListResponse:
    """List deposit orders with pagination and filters."""
    params = OrderQueryParams(
        order_no=order_no,
        out_trade_no=out_trade_no,
        merchant_id=merchant_id,
        token=token,
        chain=chain,
        status=status,
        callback_status=callback_status,
        tx_hash=tx_hash,
    )

    items, total = await service.get_orders(
        user=user,
        order_type=OrderType.DEPOSIT,
        params=params,
        page=page,
        page_size=page_size,
    )

    return OrderListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ============ Withdraw Orders ============


@router.get("/withdrawals", response_model=OrderListResponse)
async def list_withdrawal_orders(
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    order_no: str | None = Query(default=None, description="Order number (partial match)"),
    out_trade_no: str | None = Query(default=None, description="External trade number"),
    merchant_id: int | None = Query(default=None, description="Merchant ID"),
    token: str | None = Query(default=None, description="Token code"),
    chain: str | None = Query(default=None, description="Chain code"),
    status: OrderStatus | None = Query(default=None, description="Order status"),
    callback_status: CallbackStatus | None = Query(default=None, description="Callback status"),
    tx_hash: str | None = Query(default=None, description="Transaction hash"),
) -> OrderListResponse:
    """List withdrawal orders with pagination and filters."""
    params = OrderQueryParams(
        order_no=order_no,
        out_trade_no=out_trade_no,
        merchant_id=merchant_id,
        token=token,
        chain=chain,
        status=status,
        callback_status=callback_status,
        tx_hash=tx_hash,
    )

    items, total = await service.get_orders(
        user=user,
        order_type=OrderType.WITHDRAW,
        params=params,
        page=page,
        page_size=page_size,
    )

    return OrderListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ============ Order Details ============


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    """Get order details by ID."""
    order = await service.get_order(user, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return OrderResponse(**order)


@router.get("/no/{order_no}", response_model=OrderResponse)
async def get_order_by_no(
    order_no: str,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderResponse:
    """Get order details by order number."""
    order = await service.get_order_by_no(user, order_no)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return OrderResponse(**order)


# ============ Order Actions ============


@router.post("/{order_id}/retry-callback", response_model=OrderActionResponse)
async def retry_callback(
    order_id: int,
    user: CurrentUser,
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderActionResponse:
    """Retry sending callback for an order.

    Only admin and support users can perform this action.
    """
    try:
        result = await service.retry_callback(user, order_id)
        return OrderActionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{order_id}/force-complete", response_model=OrderActionResponse)
@totp_required
async def force_complete(
    order_id: int,
    data: ForceCompleteRequest,
    user: TOTPUser,  # 依赖注入：确保用户已绑定 TOTP
    service: Annotated[OrderService, Depends(get_order_service)],
) -> OrderActionResponse:
    """强制补单。

    敏感操作，需要：
    - 已绑定 TOTP
    - TOTP 验证码正确
    - 补单备注

    权限规则：
    - 超级管理员可补任意订单
    - 商户/客服只能补自己的订单
    """
    try:
        result = await service.force_complete(user, order_id, data)
        return OrderActionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
