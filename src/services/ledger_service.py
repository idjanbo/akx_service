"""Ledger Service - Business logic for balance ledger records."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.core.exceptions import InsufficientBalanceError
from src.models.ledger import (
    BalanceChangeType,
    BalanceLedger,
)
from src.models.order import Order
from src.models.user import User, UserRole
from src.schemas.ledger import (
    BalanceLedgerQueryParams,
)


class LedgerService:
    """Service for ledger-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Fee Management (手续费管理) - 订单流程中使用
    # =========================================================================

    async def freeze_fee(
        self,
        user: User,
        amount: Decimal,
        order_id: int,
        remark: str | None = None,
    ) -> BalanceLedger:
        """冻结手续费 - 订单创建时调用。

        从可用余额中冻结指定金额作为手续费预扣。
        可用余额 = balance - frozen_balance + credit_limit

        Args:
            user: 用户对象 (需要已刷新)
            amount: 冻结金额 (正数)
            order_id: 关联订单 ID
            remark: 备注

        Returns:
            BalanceLedger: 账变记录

        Raises:
            InsufficientBalanceError: 余额不足（含赊账额度）
        """
        # 检查可用余额是否足够（含赊账额度）
        available = user.balance - user.frozen_balance + user.credit_limit
        if available < amount:
            raise InsufficientBalanceError(
                required=amount,
                available=available,
                message="积分余额不足，无法创建订单",
            )

        # 记录变更前状态
        pre_balance = user.balance
        pre_frozen = user.frozen_balance

        # 冻结：可用余额不变，冻结余额增加
        user.frozen_balance = user.frozen_balance + amount

        # 创建账变记录
        ledger = BalanceLedger(
            user_id=user.id,
            order_id=order_id,
            change_type=BalanceChangeType.FEE_FREEZE,
            amount=Decimal("0"),  # 总余额不变
            pre_balance=pre_balance,
            post_balance=user.balance,
            frozen_amount=amount,
            pre_frozen=pre_frozen,
            post_frozen=user.frozen_balance,
            remark=remark or f"订单手续费冻结 - 订单ID: {order_id}",
        )

        self.db.add(ledger)
        return ledger

    async def settle_fee(
        self,
        user: User,
        amount: Decimal,
        order_id: int,
        remark: str | None = None,
    ) -> BalanceLedger:
        """结算手续费 - 订单成功时调用。

        从冻结余额中扣除手续费。

        Args:
            user: 用户对象 (需要已刷新)
            amount: 结算金额 (正数)
            order_id: 关联订单 ID
            remark: 备注

        Returns:
            BalanceLedger: 账变记录
        """
        # 记录变更前状态
        pre_balance = user.balance
        pre_frozen = user.frozen_balance

        # 结算：总余额减少，冻结余额减少
        user.balance = user.balance - amount
        user.frozen_balance = user.frozen_balance - amount

        # 创建账变记录
        ledger = BalanceLedger(
            user_id=user.id,
            order_id=order_id,
            change_type=BalanceChangeType.FEE_SETTLE,
            amount=-amount,  # 总余额减少
            pre_balance=pre_balance,
            post_balance=user.balance,
            frozen_amount=-amount,  # 冻结余额减少
            pre_frozen=pre_frozen,
            post_frozen=user.frozen_balance,
            remark=remark or f"订单手续费结算 - 订单ID: {order_id}",
        )

        self.db.add(ledger)
        return ledger

    async def unfreeze_fee(
        self,
        user: User,
        amount: Decimal,
        order_id: int,
        remark: str | None = None,
    ) -> BalanceLedger:
        """解冻手续费 - 订单失败/取消时调用。

        退回冻结的手续费到可用余额。

        Args:
            user: 用户对象 (需要已刷新)
            amount: 解冻金额 (正数)
            order_id: 关联订单 ID
            remark: 备注

        Returns:
            BalanceLedger: 账变记录
        """
        # 记录变更前状态
        pre_balance = user.balance
        pre_frozen = user.frozen_balance

        # 解冻：总余额不变，冻结余额减少
        user.frozen_balance = user.frozen_balance - amount

        # 创建账变记录
        ledger = BalanceLedger(
            user_id=user.id,
            order_id=order_id,
            change_type=BalanceChangeType.FEE_UNFREEZE,
            amount=Decimal("0"),  # 总余额不变
            pre_balance=pre_balance,
            post_balance=user.balance,
            frozen_amount=-amount,  # 冻结余额减少
            pre_frozen=pre_frozen,
            post_frozen=user.frozen_balance,
            remark=remark or f"订单手续费解冻 - 订单ID: {order_id}",
        )

        self.db.add(ledger)
        return ledger

    # =========================================================================
    # Balance Ledger (积分明细)
    # =========================================================================

    async def create_balance_ledger(
        self,
        user_id: int,
        change_type: BalanceChangeType,
        amount: Decimal,
        pre_balance: Decimal,
        post_balance: Decimal,
        order_id: int | None = None,
        frozen_amount: Decimal = Decimal("0"),
        pre_frozen: Decimal = Decimal("0"),
        post_frozen: Decimal = Decimal("0"),
        remark: str | None = None,
        operator_id: int | None = None,
    ) -> BalanceLedger:
        """Create a balance ledger entry."""
        record = BalanceLedger(
            user_id=user_id,
            order_id=order_id,
            change_type=change_type,
            amount=amount,
            pre_balance=pre_balance,
            post_balance=post_balance,
            frozen_amount=frozen_amount,
            pre_frozen=pre_frozen,
            post_frozen=post_frozen,
            remark=remark,
            operator_id=operator_id,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def list_balance_ledgers(
        self,
        user: User,
        params: BalanceLedgerQueryParams,
    ) -> tuple[list[dict[str, Any]], int]:
        """List balance ledger entries with pagination.

        Args:
            user: Current user (for access control)
            params: Query parameters

        Returns:
            Tuple of (records, total_count)
        """
        # Build query
        query = (
            select(
                BalanceLedger,
                Order.order_no,
                User.email.label("user_email"),
                User.username.label("user_username"),
            )
            .outerjoin(Order, BalanceLedger.order_id == Order.id)
            .outerjoin(User, BalanceLedger.user_id == User.id)
        )

        # Access control: non-admin can only see their own records
        if user.role != UserRole.SUPER_ADMIN:
            query = query.where(BalanceLedger.user_id == user.id)
        elif params.user_id:
            query = query.where(BalanceLedger.user_id == params.user_id)

        # Apply filters
        if params.change_type:
            query = query.where(BalanceLedger.change_type == params.change_type)
        if params.order_id:
            query = query.where(BalanceLedger.order_id == params.order_id)
        if params.start_date:
            query = query.where(BalanceLedger.created_at >= params.start_date)
        if params.end_date:
            query = query.where(BalanceLedger.created_at <= params.end_date)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(BalanceLedger.created_at.desc())
        offset = (params.page - 1) * params.page_size
        query = query.offset(offset).limit(params.page_size)

        # Execute
        result = await self.db.execute(query)
        rows = result.all()

        # Build response
        items = []
        for row in rows:
            record = row[0]
            item = {
                "id": record.id,
                "user_id": record.user_id,
                "order_id": record.order_id,
                "change_type": record.change_type,
                "amount": record.amount,
                "pre_balance": record.pre_balance,
                "post_balance": record.post_balance,
                "frozen_amount": record.frozen_amount,
                "pre_frozen": record.pre_frozen,
                "post_frozen": record.post_frozen,
                "remark": record.remark,
                "created_at": record.created_at,
                "order_no": row[1],
                "user_email": row[2],
                "user_username": row[3],
            }
            items.append(item)

        return items, total

    async def manual_balance_adjust(
        self,
        operator: User,
        user_id: int,
        amount: Decimal,
        change_type: BalanceChangeType,
        remark: str,
    ) -> BalanceLedger:
        """Manually adjust user balance (admin only).

        Args:
            operator: Admin user performing the operation
            user_id: Target user ID
            amount: Amount to add (positive) or deduct (negative)
            change_type: Type of balance change (manual_recharge, manual_deduct, adjustment, refund)
            remark: Reason for adjustment

        Returns:
            Created ledger entry

        Raises:
            ValueError: On invalid operation
        """
        # Get target user
        target_user = await self.db.get(User, user_id)
        if not target_user:
            raise ValueError(f"User {user_id} not found")

        # Check if deduction is possible
        # 可用余额 = balance - frozen_balance + credit_limit
        pre_balance = target_user.balance
        post_balance = pre_balance + amount

        if amount < 0:
            # 扣款时检查：扣款后可用余额不能为负
            post_available = post_balance - target_user.frozen_balance + target_user.credit_limit
            if post_available < 0:
                current_available = (
                    pre_balance - target_user.frozen_balance + target_user.credit_limit
                )
                raise ValueError(
                    f"可用余额不足。当前可用: {current_available}, 需要扣除: {abs(amount)}"
                )

        # Update user balance
        target_user.balance = post_balance
        self.db.add(target_user)

        # Create ledger entry
        ledger = await self.create_balance_ledger(
            user_id=user_id,
            change_type=change_type,
            amount=amount,
            pre_balance=pre_balance,
            post_balance=post_balance,
            remark=remark,
            operator_id=operator.id,
        )

        await self.db.commit()
        await self.db.refresh(ledger)

        return ledger
