"""Recharge API - Merchant online recharge (商户在线充值) endpoints.

Endpoints for:
- Creating recharge orders (获取充值地址)
- Querying recharge orders (查询充值订单)
- Admin: Managing address pool
- Admin: Managing collection tasks

Note: This is different from Orders deposit which handles merchant's customer deposits.
- Recharge: Merchant tops up their platform balance (商户向平台充值)
- Deposit Order: Merchant's customer pays merchant (商户客户向商户充值)
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, SuperAdmin
from src.db.engine import get_db
from src.models.recharge import RechargeOrderStatus
from src.services.collect_service import CollectService
from src.services.recharge_service import RechargeService

router = APIRouter(prefix="/recharges", tags=["Recharges"])


# ============ Request/Response Models ============


class RechargeOrderDetailResponse(BaseModel):
    """Recharge order detail response."""

    id: int
    order_no: str
    user_id: int
    recharge_address: str
    chain: str
    chain_name: str
    token: str
    token_name: str
    expected_amount: str
    actual_amount: str | None
    status: str
    tx_hash: str | None
    confirmations: int
    required_confirmations: int
    expires_at: str | None
    detected_at: str | None
    confirmed_at: str | None
    credited_at: str | None
    created_at: str | None


class PoolStatsResponse(BaseModel):
    """Address pool statistics response."""

    chain: str
    token: str
    total: int
    available: int
    assigned: int
    locked: int
    disabled: int


class GeneratePoolRequest(BaseModel):
    """Generate address pool request."""

    count: int = Field(default=10, ge=1, le=100, description="Number of addresses to generate")
    chain_code: str = Field(default="tron", description="Blockchain network")
    token_code: str = Field(default="USDT", description="Token code")


class CollectTaskResponse(BaseModel):
    """Collection task response."""

    id: int
    from_address: str
    to_address: str
    amount: str
    chain: str
    status: str


class ExecuteCollectRequest(BaseModel):
    """Execute collection request."""

    chain_code: str = Field(default="tron", description="Blockchain network")
    max_tasks: int = Field(default=10, ge=1, le=50, description="Max tasks to execute")
    dry_run: bool = Field(default=False, description="Dry run mode")


# ============ Dependency Injection ============


def get_recharge_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RechargeService:
    """Get recharge service instance."""
    return RechargeService(db)


def get_collect_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CollectService:
    """Get collect service instance."""
    return CollectService(db)


# ============ User Endpoints ============


@router.get("/orders", response_model=list[RechargeOrderDetailResponse])
async def list_recharge_orders(
    user: CurrentUser,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[RechargeOrderDetailResponse]:
    """List merchant's recharge orders (balance top-up history)."""
    status_enum = None
    if status:
        try:
            status_enum = RechargeOrderStatus(status)
        except ValueError:
            pass

    orders = await service.list_recharge_orders(
        user=user,
        status=status_enum,
        limit=limit,
        offset=offset,
    )
    return [RechargeOrderDetailResponse(**o) for o in orders]


@router.get("/orders/{order_no}", response_model=RechargeOrderDetailResponse)
async def get_recharge_order(
    order_no: str,
    user: CurrentUser,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
) -> RechargeOrderDetailResponse:
    """Get recharge order details."""
    result = await service.get_recharge_order(order_no=order_no, user=user)
    if not result:
        raise HTTPException(status_code=404, detail="Order not found")
    return RechargeOrderDetailResponse(**result)


@router.get("/address")
async def get_recharge_address(
    user: CurrentUser,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
    chain_code: str = Query(default="tron", description="Blockchain network"),
    token_code: str = Query(default="USDT", description="Token code"),
) -> dict[str, Any]:
    """Get or allocate a recharge address for the merchant.

    If the merchant already has a recharge address for this chain+token,
    returns the existing address. Otherwise, allocates a new one from the pool.
    """
    recharge_address = await service.get_or_assign_address(
        user=user,
        chain_code=chain_code,
        token_code=token_code,
    )

    if not recharge_address:
        raise HTTPException(
            status_code=503,
            detail="No recharge addresses available. Please contact support.",
        )

    return {
        "address": recharge_address.wallet.address if recharge_address.wallet else "",
        "chain": chain_code,
        "token": token_code,
        "assigned_at": recharge_address.assigned_at.isoformat()
        if recharge_address.assigned_at
        else None,
    }


# ============ Admin Endpoints ============


@router.get("/admin/pool/stats", response_model=PoolStatsResponse)
async def get_pool_stats(
    _user: SuperAdmin,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
    chain_code: str = Query(default="tron"),
    token_code: str = Query(default="USDT"),
) -> PoolStatsResponse:
    """Get address pool statistics (admin only)."""
    stats = await service.get_pool_stats(chain_code=chain_code, token_code=token_code)
    return PoolStatsResponse(**stats)


@router.post("/admin/pool/generate")
async def generate_address_pool(
    data: GeneratePoolRequest,
    _user: SuperAdmin,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
) -> dict[str, Any]:
    """Generate addresses for the recharge pool (admin only)."""
    try:
        addresses = await service.generate_address_pool(
            count=data.count,
            chain_code=data.chain_code,
            token_code=data.token_code,
        )
        return {
            "message": f"Generated {len(addresses)} addresses",
            "count": len(addresses),
            "chain": data.chain_code,
            "token": data.token_code,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/admin/orders", response_model=list[RechargeOrderDetailResponse])
async def admin_list_all_orders(
    _user: SuperAdmin,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[RechargeOrderDetailResponse]:
    """List all recharge orders (admin only)."""
    status_enum = None
    if status:
        try:
            status_enum = RechargeOrderStatus(status)
        except ValueError:
            pass

    orders = await service.list_recharge_orders(
        user=None,  # Admin sees all
        status=status_enum,
        limit=limit,
        offset=offset,
    )
    return [RechargeOrderDetailResponse(**o) for o in orders]


@router.post("/admin/expire-orders")
async def expire_pending_orders(
    _user: SuperAdmin,
    service: Annotated[RechargeService, Depends(get_recharge_service)],
) -> dict[str, Any]:
    """Expire pending orders that have passed their expiry time (admin only)."""
    count = await service.expire_pending_orders()
    return {"message": f"Expired {count} orders", "count": count}


# ============ Collection Endpoints (Admin) ============


@router.get("/admin/collect/tasks", response_model=list[CollectTaskResponse])
async def list_collect_tasks(
    _user: SuperAdmin,
    service: Annotated[CollectService, Depends(get_collect_service)],
    chain_code: str = Query(default="tron"),
    limit: int = Query(50, ge=1, le=200),
) -> list[CollectTaskResponse]:
    """List pending collection tasks (admin only)."""
    # Use recharge service for this query
    db = service.db
    recharge_svc = RechargeService(db)
    tasks = await recharge_svc.get_pending_collect_tasks(chain_code=chain_code, limit=limit)
    return [CollectTaskResponse(**t) for t in tasks]


@router.post("/admin/collect/scan")
async def scan_for_collection(
    _user: SuperAdmin,
    service: Annotated[CollectService, Depends(get_collect_service)],
    hot_wallet_id: int = Query(description="Hot wallet ID to collect to"),
    chain_code: str = Query(default="tron"),
    token_code: str = Query(default="USDT"),
) -> dict[str, Any]:
    """Scan recharge addresses and create collection tasks (admin only)."""
    tasks = await service.scan_and_create_tasks(
        hot_wallet_id=hot_wallet_id,
        chain_code=chain_code,
        token_code=token_code,
    )
    return {
        "message": f"Created {len(tasks)} collection tasks",
        "count": len(tasks),
    }


@router.post("/admin/collect/execute")
async def execute_collection(
    data: ExecuteCollectRequest,
    _user: SuperAdmin,
    service: Annotated[CollectService, Depends(get_collect_service)],
) -> dict[str, Any]:
    """Execute pending collection tasks (admin only).

    WARNING: This will transfer funds from recharge addresses to hot wallet.
    Use dry_run=true to preview without executing.
    """
    result = await service.execute_pending_tasks(
        chain_code=data.chain_code,
        max_tasks=data.max_tasks,
        dry_run=data.dry_run,
    )
    return result


@router.get("/admin/collect/stats")
async def get_collection_stats(
    _user: SuperAdmin,
    service: Annotated[CollectService, Depends(get_collect_service)],
    chain_code: str = Query(default="tron"),
) -> dict[str, Any]:
    """Get collection statistics (admin only)."""
    return await service.get_collection_stats(chain_code=chain_code)


@router.post("/admin/collect/retry-failed")
async def retry_failed_tasks(
    _user: SuperAdmin,
    service: Annotated[CollectService, Depends(get_collect_service)],
    chain_code: str = Query(default="tron"),
    max_retries: int = Query(default=3, ge=1, le=10),
) -> dict[str, Any]:
    """Retry failed collection tasks (admin only)."""
    return await service.retry_failed_tasks(
        chain_code=chain_code,
        max_retries=max_retries,
    )
