"""AKX Crypto Payment Gateway - Exchange Rate Service.

This module provides:
- Exchange rate source management (super admin)
- Merchant exchange rate configuration
- Rate calculation with merchant adjustments
- External rate sync (OKX C2C, etc.)
"""

import logging
import re
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.exchange_rate import ExchangeRate, ExchangeRateMode, ExchangeRateSource

logger = logging.getLogger(__name__)


class ExchangeRateService:
    """Service for exchange rate operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Rate Source (Super Admin) ====================

    async def list_sources(self) -> list[ExchangeRateSource]:
        """List all exchange rate sources."""
        result = await self.db.execute(
            select(ExchangeRateSource).order_by(ExchangeRateSource.base_currency)
        )
        return list(result.scalars().all())

    async def get_source(
        self, base_currency: str, quote_currency: str
    ) -> ExchangeRateSource | None:
        """Get exchange rate source by currency pair."""
        result = await self.db.execute(
            select(ExchangeRateSource).where(
                ExchangeRateSource.base_currency == base_currency.upper(),
                ExchangeRateSource.quote_currency == quote_currency.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def get_source_by_id(self, source_id: int) -> ExchangeRateSource | None:
        """Get exchange rate source by ID."""
        return await self.db.get(ExchangeRateSource, source_id)

    async def create_source(
        self,
        base_currency: str,
        quote_currency: str,
        source_name: str,
        source_url: str | None = None,
        response_path: str | None = None,
        sync_interval: int = 60,
        current_rate: Decimal | None = None,
    ) -> ExchangeRateSource:
        """Create a new exchange rate source."""
        source = ExchangeRateSource(
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
            source_name=source_name,
            source_url=source_url,
            response_path=response_path,
            sync_interval=sync_interval,
            current_rate=current_rate,
            is_enabled=True,
        )
        self.db.add(source)
        await self.db.commit()
        await self.db.refresh(source)
        return source

    async def update_source(
        self,
        source_id: int,
        **kwargs: Any,
    ) -> ExchangeRateSource | None:
        """Update an exchange rate source."""
        source = await self.get_source_by_id(source_id)
        if not source:
            return None

        for key, value in kwargs.items():
            if hasattr(source, key) and value is not None:
                setattr(source, key, value)

        await self.db.commit()
        await self.db.refresh(source)
        return source

    async def delete_source(self, source_id: int) -> bool:
        """Delete an exchange rate source."""
        source = await self.get_source_by_id(source_id)
        if not source:
            return False

        await self.db.delete(source)
        await self.db.commit()
        return True

    # ==================== Merchant Config ====================

    async def list_merchant_configs(self, user_id: int) -> list[ExchangeRate]:
        """List merchant's exchange rate configurations."""
        result = await self.db.execute(select(ExchangeRate).where(ExchangeRate.user_id == user_id))
        return list(result.scalars().all())

    async def get_merchant_config(
        self, user_id: int, base_currency: str, quote_currency: str
    ) -> ExchangeRate | None:
        """Get merchant's config for a currency pair."""
        result = await self.db.execute(
            select(ExchangeRate).where(
                ExchangeRate.user_id == user_id,
                ExchangeRate.base_currency == base_currency.upper(),
                ExchangeRate.quote_currency == quote_currency.upper(),
            )
        )
        return result.scalar_one_or_none()

    async def get_merchant_config_by_id(self, config_id: int) -> ExchangeRate | None:
        """Get merchant config by ID."""
        return await self.db.get(ExchangeRate, config_id)

    async def create_or_update_merchant_config(
        self,
        user_id: int,
        base_currency: str,
        quote_currency: str,
        mode: ExchangeRateMode,
        rate: Decimal | None = None,
        adjustment: Decimal = Decimal("0"),
    ) -> ExchangeRate:
        """Create or update merchant exchange rate config."""
        config = await self.get_merchant_config(user_id, base_currency, quote_currency)

        if config:
            config.mode = mode
            config.rate = rate
            config.adjustment = adjustment
            config.is_enabled = True
        else:
            config = ExchangeRate(
                user_id=user_id,
                base_currency=base_currency.upper(),
                quote_currency=quote_currency.upper(),
                mode=mode,
                rate=rate,
                adjustment=adjustment,
                is_enabled=True,
            )
            self.db.add(config)

        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def delete_merchant_config(self, config_id: int, user_id: int) -> bool:
        """Delete merchant config (only own config)."""
        config = await self.get_merchant_config_by_id(config_id)
        if not config or config.user_id != user_id:
            return False

        await self.db.delete(config)
        await self.db.commit()
        return True

    # ==================== Rate Calculation ====================

    async def get_system_rate(self, base_currency: str, quote_currency: str) -> Decimal | None:
        """Get current system rate for a currency pair."""
        source = await self.get_source(base_currency, quote_currency)
        if source and source.is_enabled and source.current_rate:
            return source.current_rate
        return None

    async def get_merchant_rate(
        self, merchant_id: int, base_currency: str, quote_currency: str
    ) -> Decimal | None:
        """Get effective rate for a merchant.

        Priority:
        1. Merchant custom rate (mode=custom)
        2. Merchant adjustment on system rate (mode=adjustment)
        3. System rate (mode=system or no config)

        Returns:
            Calculated rate or None if no rate available
        """
        # Get system rate first
        system_rate = await self.get_system_rate(base_currency, quote_currency)

        # Get merchant config
        config = await self.get_merchant_config(merchant_id, base_currency, quote_currency)

        if config and config.is_enabled:
            if config.mode == ExchangeRateMode.CUSTOM and config.rate:
                return config.rate
            elif config.mode == ExchangeRateMode.ADJUSTMENT and system_rate:
                # Apply adjustment: rate * (1 + adjustment)
                # adjustment = +0.03 means 3% markup
                return system_rate * (1 + config.adjustment)

        return system_rate

    async def calculate_payment_amount(
        self,
        user_id: int,
        requested_amount: Decimal,
        requested_currency: str,
        payment_currency: str,
    ) -> dict[str, Decimal] | None:
        """Calculate actual payment amount in target token.

        Args:
            user_id: Merchant ID
            requested_amount: Amount in requested currency
            requested_currency: Currency of the request (CNY, USD, USDT, etc.)
            payment_currency: Target crypto token (USDT, USDC, etc.)

        Returns:
            Dict with payment_amount and exchange_rate, or None if conversion fails
        """
        requested_currency = requested_currency.upper()
        payment_currency = payment_currency.upper()

        # Same currency - no conversion needed
        if requested_currency == payment_currency:
            return {
                "payment_amount": requested_amount,
                "exchange_rate": Decimal("1"),
            }

        # Need conversion - get merchant rate
        rate = await self.get_merchant_rate(user_id, payment_currency, requested_currency)

        if not rate or rate <= 0:
            return None

        # Convert: fiat_amount / rate = crypto_amount
        # Example: 700 CNY / 7.0 = 100 USDT
        payment_amount = requested_amount / rate

        return {
            "payment_amount": payment_amount,
            "exchange_rate": rate,
        }

    # ==================== External Sync ====================

    async def sync_rate_from_source(self, source_id: int) -> ExchangeRateSource | None:
        """Sync exchange rate from external source.

        Fetches rate from source_url and extracts value using response_path.
        """
        source = await self.get_source_by_id(source_id)
        if not source or not source.source_url:
            return None

        pair = f"{source.base_currency}/{source.quote_currency}"

        # 模拟真实浏览器请求，避免被风控
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                response = await client.get(source.source_url)
                response.raise_for_status()
                data = response.json()

            # Extract rate using response_path
            rate = self._extract_value(data, source.response_path)
            if rate is not None:
                old_rate = source.current_rate
                source.current_rate = Decimal(str(rate))
                from datetime import datetime

                source.last_synced_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(source)
                # 只在汇率变化时记录
                if old_rate != source.current_rate:
                    logger.info("%s: %s -> %s", pair, old_rate, source.current_rate)
            else:
                logger.warning("%s: 无法提取汇率 (path: %s)", pair, source.response_path)

        except Exception as e:
            logger.error("同步 %s 失败: %s", pair, e)

        return source

    async def sync_all_rates(self, *, force: bool = False) -> list[ExchangeRateSource]:
        """Sync all enabled rate sources.

        Args:
            force: 强制同步所有源，忽略 sync_interval 限制（手动触发时使用）
        """
        from datetime import datetime

        result = await self.db.execute(
            select(ExchangeRateSource).where(
                ExchangeRateSource.is_enabled.is_(True),
                ExchangeRateSource.source_url.isnot(None),
                ExchangeRateSource.sync_interval > 0,
            )
        )
        sources = list(result.scalars().all())

        # 手动触发时忽略频率限制，自动任务时检查 sync_interval
        if not force:
            now = datetime.utcnow()
            # 过滤出需要同步的源（首次同步 或 距离上次超过 sync_interval）
            due_sources = []
            for source in sources:
                if source.last_synced_at is None:
                    due_sources.append(source)
                elif (now - source.last_synced_at).total_seconds() >= source.sync_interval:
                    due_sources.append(source)
        else:
            due_sources = sources

        if not due_sources:
            return []

        synced = []
        for source in due_sources:
            updated = await self.sync_rate_from_source(source.id)  # type: ignore
            if updated:
                synced.append(updated)

        if synced:
            logger.info("汇率同步完成: %d 个源", len(synced))
        return synced

    def _extract_value(self, data: Any, path: str | None) -> Any:
        """Extract value from nested dict/list using dot notation path.

        Supports:
        - data.field
        - data.array[0]
        - data.array[0].field

        Example: 'data.buy[0].price'
        """
        if not path:
            return data

        current = data
        # Split by dots but handle array indices
        parts = re.split(r"\.(?![^\[]*\])", path)

        for part in parts:
            if current is None:
                return None

            # Check for array index: field[0]
            match = re.match(r"(\w+)\[(\d+)\]", part)
            if match:
                field, index = match.groups()
                if isinstance(current, dict) and field in current:
                    current = current[field]
                    if isinstance(current, list) and int(index) < len(current):
                        current = current[int(index)]
                    else:
                        return None
                else:
                    return None
            else:
                # Simple field access
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None

        return current
