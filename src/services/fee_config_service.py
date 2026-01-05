"""Fee Configuration Service - Business logic for fee management."""

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.fee_config import FeeConfig
from src.models.user import User


class FeeConfigService:
    """Service for fee configuration business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_fee_configs(self) -> list[FeeConfig]:
        """List all fee configurations.

        Returns:
            List of fee configs ordered by ID
        """
        result = await self.db.execute(select(FeeConfig).order_by(FeeConfig.id))
        return list(result.scalars().all())

    async def get_fee_config(self, fee_config_id: int) -> FeeConfig | None:
        """Get fee configuration by ID.

        Args:
            fee_config_id: Fee config ID

        Returns:
            Fee config or None
        """
        return await self.db.get(FeeConfig, fee_config_id)

    async def get_default_fee_config(self) -> FeeConfig | None:
        """Get the default fee configuration.

        Returns:
            Default fee config or None
        """
        result = await self.db.execute(
            select(FeeConfig).where(FeeConfig.is_default == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def create_fee_config(self, data: dict[str, Any]) -> FeeConfig:
        """Create new fee configuration.

        Args:
            data: Fee config data

        Returns:
            Created fee config

        Raises:
            ValueError: If name already exists
        """
        # Check name uniqueness
        result = await self.db.execute(select(FeeConfig).where(FeeConfig.name == data.get("name")))
        if result.scalar_one_or_none():
            raise ValueError(f"Fee configuration with name '{data.get('name')}' already exists")

        # If setting as default, unset all others
        if data.get("is_default"):
            await self._clear_default()

        fee_config = FeeConfig(**data)
        self.db.add(fee_config)
        await self.db.commit()
        await self.db.refresh(fee_config)
        return fee_config

    async def update_fee_config(self, fee_config_id: int, data: dict[str, Any]) -> FeeConfig | None:
        """Update fee configuration.

        Args:
            fee_config_id: Fee config ID
            data: Update data

        Returns:
            Updated fee config or None

        Raises:
            ValueError: If name already exists
        """
        fee_config = await self.db.get(FeeConfig, fee_config_id)
        if not fee_config:
            return None

        # Check name uniqueness if changed
        if data.get("name") and data.get("name") != fee_config.name:
            result = await self.db.execute(
                select(FeeConfig).where(FeeConfig.name == data.get("name"))
            )
            if result.scalar_one_or_none():
                raise ValueError(f"Fee configuration with name '{data.get('name')}' already exists")

        # If setting as default, unset all others
        if data.get("is_default"):
            await self._clear_default(exclude_id=fee_config_id)

        for field, value in data.items():
            setattr(fee_config, field, value)

        self.db.add(fee_config)
        await self.db.commit()
        await self.db.refresh(fee_config)
        return fee_config

    async def delete_fee_config(self, fee_config_id: int) -> bool:
        """Delete fee configuration.

        Args:
            fee_config_id: Fee config ID

        Returns:
            True if deleted

        Raises:
            ValueError: If config is in use by merchants
        """
        fee_config = await self.db.get(FeeConfig, fee_config_id)
        if not fee_config:
            return False

        # Check if in use
        result = await self.db.execute(select(User).where(User.fee_config_id == fee_config_id))
        if result.first():
            raise ValueError("Cannot delete fee configuration that is in use by merchants")

        await self.db.delete(fee_config)
        await self.db.commit()
        return True

    async def calculate_fee(
        self, user: User, amount: Decimal, transaction_type: str
    ) -> dict[str, Any]:
        """Calculate fee for a transaction.

        Args:
            user: User making the transaction
            amount: Transaction amount
            transaction_type: 'deposit' or 'withdraw'

        Returns:
            Fee calculation result

        Raises:
            ValueError: If no fee config found
        """
        # Get user's fee config
        if user.fee_config_id:
            fee_config = await self.db.get(FeeConfig, user.fee_config_id)
        else:
            fee_config = await self.get_default_fee_config()

        if not fee_config:
            raise ValueError("No fee configuration found")

        # Calculate fee
        if transaction_type == "deposit":
            fee = fee_config.calculate_deposit_fee(amount)
            total = amount - fee  # User receives amount minus fee
        else:  # withdraw
            fee = fee_config.calculate_withdraw_fee(amount)
            total = amount + fee  # User pays amount plus fee

        return {
            "amount": amount,
            "fee": fee,
            "total": total,
            "fee_config_name": fee_config.name,
        }

    async def _clear_default(self, exclude_id: int | None = None) -> None:
        """Clear default flag from all fee configs.

        Args:
            exclude_id: Optional ID to exclude from clearing
        """
        query = select(FeeConfig).where(FeeConfig.is_default == True)  # noqa: E712
        if exclude_id:
            query = query.where(FeeConfig.id != exclude_id)

        result = await self.db.execute(query)
        for config in result.scalars().all():
            config.is_default = False
            self.db.add(config)
