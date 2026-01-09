"""AKX Crypto Payment Gateway - Exchange Rate API.

Merchant endpoints for managing their own exchange rate configurations.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import NonGuestUser
from src.db import get_db
from src.models.exchange_rate import ExchangeRate, ExchangeRateMode
from src.services.exchange_rate_service import ExchangeRateService

router = APIRouter(prefix="/exchange-rates", tags=["Exchange Rates"])


# ==================== Schemas ====================


class ExchangeRateConfigCreate(BaseModel):
    """Create/update merchant exchange rate config."""

    base_currency: str = Field(..., max_length=20, description="加密货币: USDT, USDC")
    quote_currency: str = Field(..., max_length=20, description="法币: CNY, USD")
    mode: ExchangeRateMode = Field(default=ExchangeRateMode.SYSTEM, description="汇率模式")
    rate: Decimal | None = Field(None, gt=0, description="自定义汇率 (mode=custom时必填)")
    adjustment: Decimal | None = Field(
        None,
        ge=Decimal("-0.5"),
        le=Decimal("0.5"),
        description="调整比例 (mode=adjustment时必填), +0.03=加3%",
    )

    @field_validator("rate", "adjustment", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: str | None) -> Decimal | None:
        """将空字符串转换为 None。"""
        if v == "" or v is None:
            return None
        return v


class ExchangeRateConfigResponse(BaseModel):
    """Merchant exchange rate config response."""

    id: int
    base_currency: str
    quote_currency: str
    mode: str
    rate: str | None
    adjustment: str | None
    is_enabled: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, config: ExchangeRate) -> "ExchangeRateConfigResponse":
        from src.utils.helpers import format_utc_datetime

        return cls(
            id=config.id,  # type: ignore
            base_currency=config.base_currency,
            quote_currency=config.quote_currency,
            mode=config.mode.value,
            rate=str(config.rate) if config.rate else None,
            adjustment=str(config.adjustment) if config.adjustment else None,
            is_enabled=config.is_enabled,
            created_at=format_utc_datetime(config.created_at),  # type: ignore
            updated_at=format_utc_datetime(config.updated_at),  # type: ignore
        )


class CurrentRateResponse(BaseModel):
    """当前汇率计算结果。"""

    base_currency: str
    quote_currency: str
    rate: str
    mode: str
    source: str  # "system" | "custom" | "adjustment"


class PaymentCalculateRequest(BaseModel):
    """计算支付金额请求。"""

    base_currency: str = Field(default="USDT", description="加密货币")
    quote_currency: str = Field(..., description="法币: CNY, USD")
    amount: Decimal = Field(..., gt=0, description="法币金额")


class PaymentCalculateResponse(BaseModel):
    """计算支付金额响应。"""

    requested_amount: str
    requested_currency: str
    payment_amount: str
    payment_currency: str
    exchange_rate: str


# ==================== Dependencies ====================


def get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ExchangeRateService:
    return ExchangeRateService(db)


# ==================== Endpoints ====================


@router.get("", response_model=list[ExchangeRateConfigResponse])
async def list_my_configs(
    user: NonGuestUser,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> list[ExchangeRateConfigResponse]:
    """列出我的汇率配置。"""
    configs = await service.list_merchant_configs(user.id)  # type: ignore
    return [ExchangeRateConfigResponse.from_model(c) for c in configs]


@router.get("/{base}/{quote}", response_model=ExchangeRateConfigResponse | None)
async def get_my_config(
    base: str,
    quote: str,
    user: NonGuestUser,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> ExchangeRateConfigResponse | None:
    """获取指定币种对的汇率配置。"""
    config = await service.get_merchant_config(user.id, base, quote)  # type: ignore
    if not config:
        return None
    return ExchangeRateConfigResponse.from_model(config)


@router.put("", response_model=ExchangeRateConfigResponse)
async def upsert_config(
    data: ExchangeRateConfigCreate,
    user: NonGuestUser,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> ExchangeRateConfigResponse:
    """创建或更新汇率配置。"""
    # Validate based on mode
    if data.mode == ExchangeRateMode.CUSTOM and not data.rate:
        raise HTTPException(status_code=400, detail="自定义模式需要设置 rate")
    if data.mode == ExchangeRateMode.ADJUSTMENT and data.adjustment is None:
        raise HTTPException(status_code=400, detail="调整模式需要设置 adjustment")

    config = await service.create_or_update_merchant_config(
        user_id=user.id,  # type: ignore
        base_currency=data.base_currency,
        quote_currency=data.quote_currency,
        mode=data.mode,
        rate=data.rate,
        adjustment=data.adjustment or Decimal("0"),
    )
    return ExchangeRateConfigResponse.from_model(config)


@router.delete("/{base}/{quote}", status_code=204)
async def delete_config(
    base: str,
    quote: str,
    user: NonGuestUser,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> None:
    """删除汇率配置（恢复使用系统默认）。"""
    config = await service.get_merchant_config(user.id, base, quote)  # type: ignore
    if config:
        await service.db.delete(config)
        await service.db.commit()


@router.get("/{base}/{quote}/current", response_model=CurrentRateResponse)
async def get_current_rate(
    base: str,
    quote: str,
    user: NonGuestUser,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> CurrentRateResponse:
    """获取当前生效的汇率。

    根据商户配置计算实际汇率：
    - system: 使用系统汇率
    - custom: 使用自定义汇率
    - adjustment: 系统汇率 * (1 + 调整百分比/100)
    """
    rate = await service.get_merchant_rate(user.id, base, quote)  # type: ignore
    if not rate:
        raise HTTPException(status_code=404, detail=f"汇率 {base}/{quote} 不可用，请联系管理员配置")

    # Determine source
    config = await service.get_merchant_config(user.id, base, quote)  # type: ignore
    if config:
        source = config.mode.value
    else:
        source = "system"

    return CurrentRateResponse(
        base_currency=base,
        quote_currency=quote,
        rate=str(rate),
        mode=source,
        source=source,
    )


@router.post("/calculate", response_model=PaymentCalculateResponse)
async def calculate_payment(
    data: PaymentCalculateRequest,
    user: NonGuestUser,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> PaymentCalculateResponse:
    """计算支付金额。

    输入法币金额，输出需要支付的加密货币金额。
    """
    result = await service.calculate_payment_amount(
        user_id=user.id,  # type: ignore
        requested_amount=data.amount,
        requested_currency=data.quote_currency,
        payment_currency=data.base_currency,
    )
    if not result:
        raise HTTPException(
            status_code=400,
            detail=f"无法计算汇率 {data.base_currency}/{data.quote_currency}",
        )

    return PaymentCalculateResponse(
        requested_amount=str(data.amount),
        requested_currency=data.quote_currency,
        payment_amount=str(result["payment_amount"]),
        payment_currency=data.base_currency,
        exchange_rate=str(result["exchange_rate"]),
    )


# ==================== Public Endpoints (for payment API) ====================


@router.get("/public/{merchant_id}/{base}/{quote}", response_model=CurrentRateResponse)
async def get_merchant_public_rate(
    merchant_id: int,
    base: str,
    quote: str,
    service: Annotated[ExchangeRateService, Depends(get_service)],
) -> CurrentRateResponse:
    """获取商户的公开汇率（供支付页面使用）。"""
    rate = await service.get_merchant_rate(merchant_id, base, quote)
    if not rate:
        raise HTTPException(status_code=404, detail=f"汇率 {base}/{quote} 不可用")

    config = await service.get_merchant_config(merchant_id, base, quote)
    source = config.mode.value if config else "system"

    return CurrentRateResponse(
        base_currency=base,
        quote_currency=quote,
        rate=str(rate),
        mode=source,
        source=source,
    )
