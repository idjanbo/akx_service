"""Order service for business logic."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from src.models.order import CallbackStatus, Order, OrderStatus, OrderType
from src.models.user import User, UserRole
from src.schemas.order import (
    ForceCompleteRequest,
    OrderQueryParams,
)


class OrderService:
    """Service for order management operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_orders(
        self,
        user: User,
        order_type: OrderType,
        params: OrderQueryParams,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated orders with filters.

        Args:
            user: Current user
            order_type: deposit or withdraw
            params: Query parameters
            page: Page number
            page_size: Items per page

        Returns:
            Tuple of (orders list, total count)
        """
        # Base query
        query = select(Order).where(Order.order_type == order_type)

        # Role-based filter: merchants can only see their own orders
        if user.role == UserRole.MERCHANT:
            query = query.where(Order.merchant_id == user.id)
        elif params.merchant_id:
            query = query.where(Order.merchant_id == params.merchant_id)

        # Apply filters
        if params.order_no:
            query = query.where(Order.order_no.contains(params.order_no))
        if params.out_trade_no:
            query = query.where(Order.out_trade_no.contains(params.out_trade_no))
        if params.token:
            query = query.where(Order.token == params.token)
        if params.chain:
            query = query.where(Order.chain == params.chain)
        if params.status:
            query = query.where(Order.status == params.status)
        if params.callback_status:
            query = query.where(Order.callback_status == params.callback_status)
        if params.tx_hash:
            query = query.where(Order.tx_hash.contains(params.tx_hash))
        if params.start_date:
            query = query.where(Order.created_at >= params.start_date)
        if params.end_date:
            query = query.where(Order.created_at <= params.end_date)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Apply pagination and ordering
        query = query.order_by(col(Order.created_at).desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        # Execute query
        result = await self.db.execute(query)
        orders = result.scalars().all()

        # Convert to response format with merchant name
        order_list = []
        for order in orders:
            order_dict = self._order_to_dict(order)
            # Get merchant email (User model uses email, not username)
            if order.merchant:
                order_dict["merchant_name"] = order.merchant.email
            order_list.append(order_dict)

        return order_list, total

    async def get_order(self, user: User, order_id: int) -> dict[str, Any] | None:
        """Get single order by ID.

        Args:
            user: Current user
            order_id: Order ID

        Returns:
            Order dict or None
        """
        order = await self.db.get(Order, order_id)
        if not order:
            return None

        # Permission check: merchants can only see their own orders
        if user.role == UserRole.MERCHANT and order.merchant_id != user.id:
            return None

        order_dict = self._order_to_dict(order)
        if order.merchant:
            order_dict["merchant_name"] = order.merchant.email
        return order_dict

    async def get_order_by_no(self, user: User, order_no: str) -> dict[str, Any] | None:
        """Get single order by order number.

        Args:
            user: Current user
            order_no: Order number

        Returns:
            Order dict or None
        """
        query = select(Order).where(Order.order_no == order_no)
        result = await self.db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            return None

        # Permission check
        if user.role == UserRole.MERCHANT and order.merchant_id != user.id:
            return None

        order_dict = self._order_to_dict(order)
        if order.merchant:
            order_dict["merchant_name"] = order.merchant.email
        return order_dict

    async def retry_callback(self, user: User, order_id: int) -> dict[str, Any]:
        """Retry sending callback for an order.

        Args:
            user: Current user (must be admin)
            order_id: Order ID

        Returns:
            Result dict with success flag and message
        """
        # Only admin/support can retry callbacks
        if user.role == UserRole.MERCHANT:
            raise ValueError("Permission denied")

        order = await self.db.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")

        # Only completed orders can have callbacks retried
        if order.status not in [OrderStatus.SUCCESS, OrderStatus.FAILED]:
            raise ValueError("Order status does not support callback retry")

        # Reset callback status
        order.callback_status = CallbackStatus.PENDING
        order.callback_retry_count = 0
        order.updated_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(order)

        # Trigger callback task (TODO: integrate with Celery)
        # from src.tasks.orders import send_callback_task
        # send_callback_task.delay(order.id)

        return {
            "success": True,
            "message": "回调已重新加入发送队列",
            "order": self._order_to_dict(order),
        }

    async def force_complete(
        self,
        user: User,
        order_id: int,
        data: ForceCompleteRequest,
    ) -> dict[str, Any]:
        """Force complete an order (补单).

        This is a sensitive operation that:
        1. Marks the order as SUCCESS
        2. Adds a remark noting forced completion
        3. Triggers callback to merchant

        Args:
            user: Current user (TOTP already verified by API layer)
            order_id: Order ID
            data: Request data with remark

        Returns:
            Result dict with success flag and message
        """
        order = await self.db.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")

        # Permission check: super_admin can complete any order,
        # merchant/support can only complete their own orders
        if user.role != UserRole.SUPER_ADMIN:
            if order.merchant_id != user.id:
                raise ValueError("Permission denied: can only force complete own orders")

        # Update order
        old_status = order.status
        order.status = OrderStatus.SUCCESS
        order.completed_at = datetime.now(UTC)
        order.updated_at = datetime.now(UTC)

        # Add remark
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        force_remark = (
            f"[强制补单] {timestamp} 由 {user.email} 操作。"
            f"原状态: {old_status.value}。备注: {data.remark}"
        )
        if order.remark:
            order.remark = f"{order.remark}\n{force_remark}"
        else:
            order.remark = force_remark

        # Reset callback to trigger re-send
        order.callback_status = CallbackStatus.PENDING
        order.callback_retry_count = 0

        await self.db.commit()
        await self.db.refresh(order)

        # Trigger callback task (TODO: integrate with Celery)
        # from src.tasks.orders import send_callback_task
        # send_callback_task.delay(order.id)

        return {
            "success": True,
            "message": "订单已强制补单成功，回调已加入发送队列",
            "order": self._order_to_dict(order),
        }

    def _order_to_dict(self, order: Order) -> dict[str, Any]:
        """Convert Order model to dict."""
        return {
            "id": order.id,
            "order_no": order.order_no,
            "out_trade_no": order.out_trade_no,
            "order_type": order.order_type.value,
            "merchant_id": order.merchant_id,
            "merchant_name": None,
            "token": order.token,
            "chain": order.chain,
            "amount": str(order.amount),
            "fee": str(order.fee),
            "net_amount": str(order.net_amount),
            "wallet_address": order.wallet_address,
            "to_address": order.to_address,
            "tx_hash": order.tx_hash,
            "confirmations": order.confirmations,
            "status": order.status.value,
            "callback_status": order.callback_status.value,
            "callback_retry_count": order.callback_retry_count,
            "last_callback_at": (
                order.last_callback_at.isoformat() if order.last_callback_at else None
            ),
            "extra_data": order.extra_data,
            "remark": order.remark,
            "expire_time": order.expire_time.isoformat() if order.expire_time else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }
