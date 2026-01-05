"""Ledger API - Transaction record endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import CurrentUser, SuperAdmin
from src.db.engine import get_db
from src.models.ledger import (
    AddressTransactionType,
    BalanceChangeType,
    RechargeStatus,
    RechargeType,
)
from src.schemas.ledger import (
    AddressTransactionListResponse,
    AddressTransactionQueryParams,
    BalanceLedgerListResponse,
    BalanceLedgerQueryParams,
    BalanceLedgerResponse,
    ManualBalanceAdjustRequest,
    RechargeRecordListResponse,
    RechargeRecordQueryParams,
)
from src.services.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["Ledger"])


def get_ledger_service(db=Depends(get_db)) -> LedgerService:
    """Get ledger service instance."""
    return LedgerService(db)


# =============================================================================
# Address Transaction Endpoints (地址历史记录)
# =============================================================================


@router.get("/address-transactions", response_model=AddressTransactionListResponse)
async def list_address_transactions(
    user: CurrentUser,
    service: Annotated[LedgerService, Depends(get_ledger_service)],
    user_id: int | None = Query(None, description="Filter by user ID (admin only)"),
    wallet_id: int | None = Query(None, description="Filter by wallet ID"),
    address: str | None = Query(None, description="Filter by wallet address"),
    tx_type: AddressTransactionType | None = Query(None, description="Filter by transaction type"),
    token: str | None = Query(None, description="Filter by token code"),
    chain: str | None = Query(None, description="Filter by chain code"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
) -> AddressTransactionListResponse:
    """List address transaction records (地址历史记录).

    Non-admin users can only see their own records.
    """
    params = AddressTransactionQueryParams(
        user_id=user_id,
        wallet_id=wallet_id,
        address=address,
        tx_type=tx_type,
        token=token,
        chain=chain,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    items, total = await service.list_address_transactions(user, params)

    return AddressTransactionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# Balance Ledger Endpoints (积分明细)
# =============================================================================


@router.get("/balance-ledgers", response_model=BalanceLedgerListResponse)
async def list_balance_ledgers(
    user: CurrentUser,
    service: Annotated[LedgerService, Depends(get_ledger_service)],
    user_id: int | None = Query(None, description="Filter by user ID (admin only)"),
    change_type: BalanceChangeType | None = Query(None, description="Filter by change type"),
    order_id: int | None = Query(None, description="Filter by order ID"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
) -> BalanceLedgerListResponse:
    """List balance ledger entries (积分明细).

    Non-admin users can only see their own records.
    """
    params = BalanceLedgerQueryParams(
        user_id=user_id,
        change_type=change_type,
        order_id=order_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    items, total = await service.list_balance_ledgers(user, params)

    return BalanceLedgerListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/balance-adjust", response_model=BalanceLedgerResponse)
async def manual_balance_adjust(
    admin: SuperAdmin,
    data: ManualBalanceAdjustRequest,
    service: Annotated[LedgerService, Depends(get_ledger_service)],
) -> BalanceLedgerResponse:
    """Manually adjust user balance (admin only).

    Use positive amount to add, negative amount to deduct.
    """
    try:
        ledger = await service.manual_balance_adjust(
            operator=admin,
            user_id=data.user_id,
            amount=data.amount,
            remark=data.remark,
        )
        return BalanceLedgerResponse(
            id=ledger.id,
            user_id=ledger.user_id,
            order_id=ledger.order_id,
            change_type=ledger.change_type,
            amount=ledger.amount,
            pre_balance=ledger.pre_balance,
            post_balance=ledger.post_balance,
            frozen_amount=ledger.frozen_amount,
            pre_frozen=ledger.pre_frozen,
            post_frozen=ledger.post_frozen,
            remark=ledger.remark,
            operator_id=ledger.operator_id,
            created_at=ledger.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Recharge Record Endpoints (充值记录)
# =============================================================================


@router.get("/recharge-records", response_model=RechargeRecordListResponse)
async def list_recharge_records(
    user: CurrentUser,
    service: Annotated[LedgerService, Depends(get_ledger_service)],
    user_id: int | None = Query(None, description="Filter by user ID (admin only)"),
    recharge_type: RechargeType | None = Query(None, description="Filter by recharge type"),
    status: RechargeStatus | None = Query(None, description="Filter by status"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
) -> RechargeRecordListResponse:
    """List recharge records (充值记录).

    Non-admin users can only see their own records.
    """
    params = RechargeRecordQueryParams(
        user_id=user_id,
        recharge_type=recharge_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    items, total = await service.list_recharge_records(user, params)

    return RechargeRecordListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
