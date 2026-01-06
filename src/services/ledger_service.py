"""Ledger Service - Business logic for balance ledger records."""

from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

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
            }
            items.append(item)

        return items, total

    async def manual_balance_adjust(
        self,
        operator: User,
        user_id: int,
        amount: Decimal,
        remark: str,
    ) -> BalanceLedger:
        """Manually adjust user balance (admin only).

        Args:
            operator: Admin user performing the operation
            user_id: Target user ID
            amount: Amount to add (positive) or deduct (negative)
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
        pre_balance = target_user.balance
        post_balance = pre_balance + amount

        if amount < 0 and post_balance < -target_user.credit_limit:
            raise ValueError(
                f"Insufficient balance. Current: {pre_balance}, "
                f"Credit limit: {target_user.credit_limit}"
            )

        # Update user balance
        target_user.balance = post_balance
        self.db.add(target_user)

        # Determine change type
        change_type = (
            BalanceChangeType.MANUAL_RECHARGE if amount > 0 else BalanceChangeType.MANUAL_DEDUCT
        )

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
