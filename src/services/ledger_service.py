"""Ledger Service - Business logic for transaction records."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.ledger import (
    AddressTransaction,
    AddressTransactionType,
    BalanceChangeType,
    BalanceLedger,
    RechargeRecord,
    RechargeStatus,
    RechargeType,
)
from src.models.order import Order
from src.models.user import User, UserRole
from src.schemas.ledger import (
    AddressTransactionQueryParams,
    BalanceLedgerQueryParams,
    RechargeRecordQueryParams,
)


class LedgerService:
    """Service for ledger-related business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Address Transaction (地址历史记录)
    # =========================================================================

    async def create_address_transaction(
        self,
        user_id: int,
        wallet_id: int | None,
        order_id: int | None,
        tx_type: AddressTransactionType,
        token: str,
        chain: str,
        amount: Decimal,
        address: str,
        tx_hash: str | None = None,
    ) -> AddressTransaction:
        """Create an address transaction record."""
        record = AddressTransaction(
            user_id=user_id,
            wallet_id=wallet_id,
            order_id=order_id,
            tx_type=tx_type,
            token=token,
            chain=chain,
            amount=amount,
            address=address,
            tx_hash=tx_hash,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def list_address_transactions(
        self,
        user: User,
        params: AddressTransactionQueryParams,
    ) -> tuple[list[dict[str, Any]], int]:
        """List address transactions with pagination.

        Args:
            user: Current user (for access control)
            params: Query parameters

        Returns:
            Tuple of (records, total_count)
        """
        # Build query
        query = (
            select(AddressTransaction, Order.order_no, User.email.label("user_email"))
            .outerjoin(Order, AddressTransaction.order_id == Order.id)
            .outerjoin(User, AddressTransaction.user_id == User.id)
        )

        # Access control: non-admin can only see their own records
        if user.role != UserRole.SUPER_ADMIN:
            query = query.where(AddressTransaction.user_id == user.id)
        elif params.user_id:
            query = query.where(AddressTransaction.user_id == params.user_id)

        # Apply filters
        if params.wallet_id:
            query = query.where(AddressTransaction.wallet_id == params.wallet_id)
        if params.address:
            query = query.where(AddressTransaction.address == params.address)
        if params.tx_type:
            query = query.where(AddressTransaction.tx_type == params.tx_type)
        if params.token:
            query = query.where(AddressTransaction.token == params.token.upper())
        if params.chain:
            query = query.where(AddressTransaction.chain == params.chain.lower())
        if params.start_date:
            query = query.where(AddressTransaction.created_at >= params.start_date)
        if params.end_date:
            query = query.where(AddressTransaction.created_at <= params.end_date)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(AddressTransaction.created_at.desc())
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
                "wallet_id": record.wallet_id,
                "order_id": record.order_id,
                "tx_type": record.tx_type,
                "token": record.token,
                "chain": record.chain,
                "amount": record.amount,
                "address": record.address,
                "tx_hash": record.tx_hash,
                "created_at": record.created_at,
                "order_no": row[1],
                "user_email": row[2],
            }
            items.append(item)

        return items, total

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
            BalanceChangeType.MANUAL_ADD if amount > 0 else BalanceChangeType.MANUAL_DEDUCT
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

        # Create recharge record for tracking
        recharge_type = RechargeType.MANUAL if amount > 0 else RechargeType.DEDUCT
        recharge = RechargeRecord(
            user_id=user_id,
            ledger_id=ledger.id,
            recharge_type=recharge_type,
            status=RechargeStatus.SUCCESS,
            amount=amount,
            remark=remark,
            operator_id=operator.id,
            completed_at=datetime.now(datetime.UTC),
        )
        self.db.add(recharge)

        await self.db.commit()
        await self.db.refresh(ledger)

        return ledger

    # =========================================================================
    # Recharge Record (充值记录)
    # =========================================================================

    async def list_recharge_records(
        self,
        user: User,
        params: RechargeRecordQueryParams,
    ) -> tuple[list[dict[str, Any]], int]:
        """List recharge records with pagination.

        Args:
            user: Current user (for access control)
            params: Query parameters

        Returns:
            Tuple of (records, total_count)
        """
        # Build query - join with BalanceLedger to get post_balance
        query = (
            select(
                RechargeRecord,
                User.email.label("user_email"),
                BalanceLedger.post_balance.label("post_balance"),
            )
            .outerjoin(User, RechargeRecord.user_id == User.id)
            .outerjoin(BalanceLedger, RechargeRecord.ledger_id == BalanceLedger.id)
        )

        # Access control: non-admin can only see their own records
        if user.role != UserRole.SUPER_ADMIN:
            query = query.where(RechargeRecord.user_id == user.id)
        elif params.user_id:
            query = query.where(RechargeRecord.user_id == params.user_id)

        # Apply filters
        if params.recharge_type:
            query = query.where(RechargeRecord.recharge_type == params.recharge_type)
        if params.status:
            query = query.where(RechargeRecord.status == params.status)
        if params.start_date:
            query = query.where(RechargeRecord.created_at >= params.start_date)
        if params.end_date:
            query = query.where(RechargeRecord.created_at <= params.end_date)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(RechargeRecord.created_at.desc())
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
                "ledger_id": record.ledger_id,
                "recharge_type": record.recharge_type,
                "status": record.status,
                "amount": record.amount,
                "payment_method": record.payment_method,
                "remark": record.remark,
                "created_at": record.created_at,
                "completed_at": record.completed_at,
                "user_email": row[1],
                "post_balance": row[2],  # From joined BalanceLedger
            }
            items.append(item)

        return items, total

    async def create_online_recharge(
        self,
        user_id: int,
        amount: Decimal,
        payment_method: str,
    ) -> RechargeRecord:
        """Create an online recharge request (pending payment).

        Args:
            user_id: User ID
            amount: Recharge amount
            payment_method: Payment method

        Returns:
            Created recharge record
        """
        record = RechargeRecord(
            user_id=user_id,
            recharge_type=RechargeType.ONLINE,
            status=RechargeStatus.PENDING,
            amount=amount,
            payment_method=payment_method,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def complete_online_recharge(
        self,
        recharge_id: int,
        success: bool = True,
    ) -> RechargeRecord:
        """Complete an online recharge request.

        Args:
            recharge_id: Recharge record ID
            success: Whether payment was successful

        Returns:
            Updated recharge record

        Raises:
            ValueError: On invalid operation
        """
        record = await self.db.get(RechargeRecord, recharge_id)
        if not record:
            raise ValueError(f"Recharge record {recharge_id} not found")

        if record.status != RechargeStatus.PENDING:
            raise ValueError(f"Recharge record {recharge_id} is not pending")

        if success:
            # Get user
            user = await self.db.get(User, record.user_id)
            if not user:
                raise ValueError(f"User {record.user_id} not found")

            # Update user balance
            pre_balance = user.balance
            post_balance = pre_balance + record.amount
            user.balance = post_balance
            self.db.add(user)

            # Create ledger entry
            ledger = await self.create_balance_ledger(
                user_id=record.user_id,
                change_type=BalanceChangeType.RECHARGE,
                amount=record.amount,
                pre_balance=pre_balance,
                post_balance=post_balance,
                remark=f"Online recharge via {record.payment_method}",
            )

            record.ledger_id = ledger.id
            record.status = RechargeStatus.SUCCESS
        else:
            record.status = RechargeStatus.FAILED

        record.completed_at = datetime.now(datetime.UTC)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        return record
