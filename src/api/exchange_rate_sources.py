"""AKX Crypto Payment Gateway - Exchange Rate Source API.

Super admin endpoints for managing exchange rate sources.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import SuperAdmin
from src.db import get_db
from src.models.exchange_rate import ExchangeRateSource
from src.services.exchange_rate_service import ExchangeRateService

router = APIRouter(prefix="/exchange-rate-sources", tags=["Exchange Rate Sources"])


# ==================== Schemas ====================


class ExchangeRateSourceCreate(BaseModel):
    """Create exchange rate source request."""

    base_currency: str = Field(..., max_length=20, description="加密货币: USDT, USDC")
    quote_currency: str = Field(..., max_length=20, description="法币: CNY, USD")
    source_name: str = Field(..., max_length=50, description="来源: okx_c2c, binance, manual")
    source_url: str | None = Field(None, max_length=500, description="API URL")
    response_path: str | None = Field(
        None, max_length=200, description="汇率字段路径: data.buy[0].price"
    )
    sync_interval: int = Field(60, ge=0, description="同步间隔(秒), 0=手动")
    current_rate: Decimal | None = Field(None, description="初始汇率(手动设置时)")


class ExchangeRateSourceUpdate(BaseModel):
    """Update exchange rate source request."""

    source_name: str | None = Field(None, max_length=50)
    source_url: str | None = Field(None, max_length=500)
    response_path: str | None = Field(None, max_length=200)
    sync_interval: int | None = Field(None, ge=0)
    current_rate: Decimal | None = None
    is_enabled: bool | None = None


class ExchangeRateSourceResponse(BaseModel):
    """Exchange rate source response."""

    id: int
    base_currency: str
    quote_currency: str
    source_name: str
    source_url: str | None
    response_path: str | None
    sync_interval: int
    current_rate: str | None
    last_synced_at: str | None
    is_enabled: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, source: ExchangeRateSource) -> "ExchangeRateSourceResponse":
        from src.utils.helpers import format_utc_datetime

        return cls(
            id=source.id,  # type: ignore
            base_currency=source.base_currency,
            quote_currency=source.quote_currency,
            source_name=source.source_name,
            source_url=source.source_url,
            response_path=source.response_path,
            sync_interval=source.sync_interval,
            current_rate=str(source.current_rate) if source.current_rate else None,
            last_synced_at=format_utc_datetime(source.last_synced_at),
            is_enabled=source.is_enabled,
            created_at=format_utc_datetime(source.created_at),  # type: ignore
            updated_at=format_utc_datetime(source.updated_at),  # type: ignore
        )


# ==================== Dependencies ====================


def get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ExchangeRateService:
    return ExchangeRateService(db)


# ==================== Endpoints ====================


@router.get("", response_model=list[ExchangeRateSourceResponse])
async def list_sources(
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> list[ExchangeRateSourceResponse]:
    """列出所有汇率来源配置。"""
    sources = await service.list_sources()
    return [ExchangeRateSourceResponse.from_model(s) for s in sources]


@router.get("/{source_id}", response_model=ExchangeRateSourceResponse)
async def get_source(
    source_id: int,
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> ExchangeRateSourceResponse:
    """获取汇率来源详情。"""
    source = await service.get_source_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="汇率来源不存在")
    return ExchangeRateSourceResponse.from_model(source)


@router.post("", response_model=ExchangeRateSourceResponse, status_code=201)
async def create_source(
    data: ExchangeRateSourceCreate,
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> ExchangeRateSourceResponse:
    """创建汇率来源。"""
    # Check if exists
    existing = await service.get_source(data.base_currency, data.quote_currency)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"汇率来源 {data.base_currency}/{data.quote_currency} 已存在",
        )

    source = await service.create_source(
        base_currency=data.base_currency,
        quote_currency=data.quote_currency,
        source_name=data.source_name,
        source_url=data.source_url,
        response_path=data.response_path,
        sync_interval=data.sync_interval,
        current_rate=data.current_rate,
    )
    return ExchangeRateSourceResponse.from_model(source)


@router.put("/{source_id}", response_model=ExchangeRateSourceResponse)
async def update_source(
    source_id: int,
    data: ExchangeRateSourceUpdate,
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> ExchangeRateSourceResponse:
    """更新汇率来源。"""
    source = await service.update_source(
        source_id,
        **data.model_dump(exclude_unset=True),
    )
    if not source:
        raise HTTPException(status_code=404, detail="汇率来源不存在")
    return ExchangeRateSourceResponse.from_model(source)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: int,
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> None:
    """删除汇率来源。"""
    deleted = await service.delete_source(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="汇率来源不存在")


@router.post("/{source_id}/sync", response_model=ExchangeRateSourceResponse)
async def sync_source(
    source_id: int,
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> ExchangeRateSourceResponse:
    """手动同步汇率来源。"""
    source = await service.sync_rate_from_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="汇率来源不存在或无法同步")
    return ExchangeRateSourceResponse.from_model(source)


@router.post("/sync-all", response_model=list[ExchangeRateSourceResponse])
async def sync_all_sources(
    user: SuperAdmin,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> list[ExchangeRateSourceResponse]:
    """同步所有启用的汇率来源（手动触发，忽略频率限制）。"""
    sources = await service.sync_all_rates(force=True)
    return [ExchangeRateSourceResponse.from_model(s) for s in sources]
