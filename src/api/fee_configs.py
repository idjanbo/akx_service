"""AKX Crypto Payment Gateway - Fee configuration API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.api.auth import get_current_user
from src.db.engine import get_db
from src.models.fee_config import FeeConfig
from src.models.user import User
from src.schemas.fee_config import (
    FeeCalculationRequest,
    FeeCalculationResponse,
    FeeConfigCreate,
    FeeConfigResponse,
    FeeConfigUpdate,
)

router = APIRouter(prefix="/fee-configs", tags=["Fee Configurations"])


@router.get("", response_model=list[FeeConfigResponse])
async def list_fee_configs(
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FeeConfig]:
    """List all fee configurations.

    Only accessible by super_admin users.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can access fee configurations",
        )

    result = await session.execute(select(FeeConfig).order_by(FeeConfig.id))
    return list(result.scalars().all())


@router.get("/{fee_config_id}", response_model=FeeConfigResponse)
async def get_fee_config(
    fee_config_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeeConfig:
    """Get fee configuration by ID.

    Only accessible by super_admin users.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can access fee configurations",
        )

    fee_config = await session.get(FeeConfig, fee_config_id)
    if not fee_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fee configuration {fee_config_id} not found",
        )
    return fee_config


@router.post("", response_model=FeeConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_fee_config(
    fee_config_data: FeeConfigCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeeConfig:
    """Create new fee configuration.

    Only accessible by super_admin users.
    If is_default is True, all other configs will be set to False.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create fee configurations",
        )

    # Check if name already exists
    result = await session.execute(select(FeeConfig).where(FeeConfig.name == fee_config_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fee configuration with name '{fee_config_data.name}' already exists",
        )

    # If setting as default, unset all other defaults
    if fee_config_data.is_default:
        result = await session.execute(select(FeeConfig).where(FeeConfig.is_default == True))
        for existing_config in result.scalars().all():
            existing_config.is_default = False
            session.add(existing_config)

    # Create new config
    fee_config = FeeConfig.model_validate(fee_config_data)
    session.add(fee_config)
    await session.commit()
    await session.refresh(fee_config)
    return fee_config


@router.patch("/{fee_config_id}", response_model=FeeConfigResponse)
async def update_fee_config(
    fee_config_id: int,
    fee_config_data: FeeConfigUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeeConfig:
    """Update fee configuration.

    Only accessible by super_admin users.
    If is_default is set to True, all other configs will be set to False.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can update fee configurations",
        )

    fee_config = await session.get(FeeConfig, fee_config_id)
    if not fee_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fee configuration {fee_config_id} not found",
        )

    # Check name uniqueness if being changed
    if fee_config_data.name and fee_config_data.name != fee_config.name:
        result = await session.execute(
            select(FeeConfig).where(FeeConfig.name == fee_config_data.name)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fee configuration with name '{fee_config_data.name}' already exists",
            )

    # If setting as default, unset all other defaults
    if fee_config_data.is_default:
        result = await session.execute(
            select(FeeConfig).where(FeeConfig.is_default == True, FeeConfig.id != fee_config_id)
        )
        for existing_config in result.scalars().all():
            existing_config.is_default = False
            session.add(existing_config)

    # Update fields
    update_data = fee_config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fee_config, field, value)

    session.add(fee_config)
    await session.commit()
    await session.refresh(fee_config)
    return fee_config


@router.delete("/{fee_config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fee_config(
    fee_config_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete fee configuration.

    Only accessible by super_admin users.
    Cannot delete if any users are using this configuration.
    """
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can delete fee configurations",
        )

    fee_config = await session.get(FeeConfig, fee_config_id)
    if not fee_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fee configuration {fee_config_id} not found",
        )

    # Check if any users are using this config
    result = await session.execute(select(User).where(User.fee_config_id == fee_config_id))
    if result.first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete fee configuration that is in use by merchants",
        )

    await session.delete(fee_config)
    await session.commit()


@router.post("/calculate", response_model=FeeCalculationResponse)
async def calculate_fee(
    request: FeeCalculationRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeeCalculationResponse:
    """Calculate fee for a transaction amount.

    Uses the current user's fee configuration.
    """
    # Get user's fee config
    if not current_user.fee_config_id:
        # Use default fee config
        result = await session.execute(select(FeeConfig).where(FeeConfig.is_default == True))
        fee_config = result.scalar_one_or_none()
        if not fee_config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No default fee configuration found",
            )
    else:
        fee_config = await session.get(FeeConfig, current_user.fee_config_id)
        if not fee_config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User's fee configuration not found",
            )

    # Calculate fee
    if request.transaction_type == "deposit":
        fee = fee_config.calculate_deposit_fee(request.amount)
        total = request.amount - fee  # Deposit: user receives amount minus fee
    else:  # withdraw
        fee = fee_config.calculate_withdraw_fee(request.amount)
        total = request.amount + fee  # Withdrawal: user pays amount plus fee

    return FeeCalculationResponse(
        amount=request.amount,
        fee=fee,
        total=total,
        fee_config_name=fee_config.name,
    )
