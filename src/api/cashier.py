"""Cashier page routes - Server-side rendered payment pages.

This module provides public-facing payment pages that merchants can embed
or redirect their customers to for completing cryptocurrency payments.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select

from src.core.templates import templates
from src.db import get_session
from src.models.order import Order, OrderStatus, OrderType
from src.utils.helpers import format_utc_datetime

router = APIRouter(prefix="/pay", tags=["Cashier"])


class OrderStatusResponse(BaseModel):
    """Public order status response for polling."""

    order_no: str
    status: str
    confirmations: int
    tx_hash: str | None = None
    completed_at: str | None = None


@router.get("/{order_no}", response_class=HTMLResponse)
async def cashier_page(request: Request, order_no: str) -> HTMLResponse:
    """Render the payment cashier page.

    This is a public page where customers can view payment details and
    make cryptocurrency payments to the displayed wallet address.

    Args:
        request: FastAPI request object
        order_no: Unique order number (DEP prefix for deposits)

    Returns:
        HTML response with the payment page
    """
    async with get_session() as db:
        # Only allow deposit orders
        result = await db.execute(
            select(Order).where(
                Order.order_no == order_no,
                Order.order_type == OrderType.DEPOSIT,
            )
        )
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        # Check if order is expired
        now = datetime.now(UTC)
        expire_time = order.expire_time
        if expire_time and expire_time.tzinfo is None:
            expire_time = expire_time.replace(tzinfo=UTC)

        is_expired = order.status == OrderStatus.EXPIRED or (expire_time and now > expire_time)

        # Determine which template to render
        if order.status == OrderStatus.SUCCESS:
            template_name = "cashier/success.html"
        elif is_expired:
            template_name = "cashier/expired.html"
        else:
            template_name = "cashier/pay.html"

        # Calculate remaining time in seconds
        remaining_seconds = 0
        if expire_time and not is_expired:
            remaining_seconds = max(0, int((expire_time - now).total_seconds()))

        # Format amounts for display
        def format_crypto_amount(amount: str) -> str:
            """Remove trailing zeros from crypto amount."""
            return amount.rstrip("0").rstrip(".") if "." in amount else amount

        def format_fiat_amount(amount: str) -> str:
            """Format fiat amount with 2 decimal places."""
            try:
                return f"{float(amount):.2f}"
            except (ValueError, TypeError):
                return amount

        # Prepare template context
        context = {
            "request": request,
            "order": {
                "order_no": order.order_no,
                "amount": format_crypto_amount(str(order.amount)),
                "requested_amount": format_fiat_amount(str(order.requested_amount))
                if order.requested_amount
                else None,
                "requested_currency": order.requested_currency,
                "exchange_rate": str(order.exchange_rate) if order.exchange_rate else None,
                "token": order.token,
                "chain": order.chain.upper(),
                "wallet_address": order.wallet_address,
                "status": order.status.value,
                "confirmations": order.confirmations,
                "tx_hash": order.tx_hash,
                "expire_time": format_utc_datetime(expire_time),
                "remaining_seconds": remaining_seconds,
                "created_at": format_utc_datetime(order.created_at),
                "completed_at": format_utc_datetime(order.completed_at),
            },
        }

        return templates.TemplateResponse(template_name, context)


@router.get("/api/status/{order_no}")
async def get_order_status(order_no: str) -> OrderStatusResponse:
    """Get order status for polling.

    This is a public API endpoint for the cashier page to poll
    order status updates without authentication.

    Args:
        order_no: Unique order number

    Returns:
        Current order status information
    """
    async with get_session() as db:
        result = await db.execute(
            select(Order).where(
                Order.order_no == order_no,
                Order.order_type == OrderType.DEPOSIT,
            )
        )
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")

        return OrderStatusResponse(
            order_no=order.order_no,
            status=order.status.value,
            confirmations=order.confirmations,
            tx_hash=order.tx_hash,
            completed_at=format_utc_datetime(order.completed_at),
        )
