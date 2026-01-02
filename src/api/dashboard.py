"""AKX - Unified dashboard API endpoints."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from src.api.auth import get_current_user
from src.db import get_db
from src.models.order import Order, OrderStatus, OrderType
from src.models.user import User, UserRole
from src.models.wallet import Chain, Wallet, WalletType

router = APIRouter()


class ChainDistribution(BaseModel):
    """Chain distribution data."""

    chain: str
    amount: str
    percentage: float


class SuccessRateTrend(BaseModel):
    """Success rate trend data point."""

    timestamp: str
    deposit_rate: float
    withdraw_rate: float


class DashboardStats(BaseModel):
    """Dashboard statistics response."""

    today_deposit_total: str
    today_withdraw_total: str
    total_fee_income: str
    active_merchants_count: int
    pending_withdrawals_count: int
    success_rate_trend: list[SuccessRateTrend]
    chain_distribution: list[ChainDistribution]


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardStats:
    """Get dashboard statistics for authenticated user."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's deposits
    deposits_result = await db.execute(
        select(func.sum(Order.amount)).where(
            Order.order_type == OrderType.DEPOSIT,
            Order.status == OrderStatus.SUCCESS,
            Order.created_at >= today_start,
        )
    )
    today_deposits = deposits_result.scalar() or Decimal("0")

    # Today's withdrawals
    withdrawals_result = await db.execute(
        select(func.sum(Order.amount)).where(
            Order.order_type == OrderType.WITHDRAWAL,
            Order.status == OrderStatus.SUCCESS,
            Order.created_at >= today_start,
        )
    )
    today_withdrawals = withdrawals_result.scalar() or Decimal("0")

    # Total fee income
    fees_result = await db.execute(select(func.sum(Order.fee)).where(Order.fee != None))
    total_fees = fees_result.scalar() or Decimal("0")

    # Active merchants count
    merchants_result = await db.execute(
        select(func.count(User.id)).where(
            User.role == UserRole.MERCHANT,
            User.is_active == True,  # noqa: E712
        )
    )
    active_merchants = merchants_result.scalar() or 0

    # Pending withdrawals
    pending_result = await db.execute(
        select(func.count(Order.id)).where(
            Order.order_type == OrderType.WITHDRAWAL,
            Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING]),
        )
    )
    pending_withdrawals = pending_result.scalar() or 0

    # Chain distribution
    chain_dist = []
    total_amount = Decimal("0")

    for chain in Chain:
        chain_total_result = await db.execute(
            select(func.sum(Order.amount)).where(
                Order.chain == chain.value,
                Order.status == OrderStatus.SUCCESS,
            )
        )
        chain_amount = chain_total_result.scalar() or Decimal("0")
        total_amount += chain_amount

    for chain in Chain:
        chain_total_result = await db.execute(
            select(func.sum(Order.amount)).where(
                Order.chain == chain.value,
                Order.status == OrderStatus.SUCCESS,
            )
        )
        chain_amount = chain_total_result.scalar() or Decimal("0")
        percentage = float((chain_amount / total_amount * 100)) if total_amount > 0 else 0.0

        chain_dist.append(
            ChainDistribution(
                chain=chain.value,
                amount=str(chain_amount),
                percentage=round(percentage, 2),
            )
        )

    # Success rate trend (mock data for now)
    success_rate_trend = []
    for i in range(7):
        trend_date = now - timedelta(days=6 - i)
        success_rate_trend.append(
            SuccessRateTrend(
                timestamp=trend_date.isoformat(),
                deposit_rate=95.5,  # TODO: Calculate from real data
                withdraw_rate=92.3,  # TODO: Calculate from real data
            )
        )

    return DashboardStats(
        today_deposit_total=str(today_deposits),
        today_withdraw_total=str(today_withdrawals),
        total_fee_income=str(total_fees),
        active_merchants_count=active_merchants,
        pending_withdrawals_count=pending_withdrawals,
        success_rate_trend=success_rate_trend,
        chain_distribution=chain_dist,
    )
