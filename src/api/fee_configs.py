"""AKX Crypto Payment Gateway - Fee configuration API endpoints.

Provides REST API endpoints for fee configuration management.
Business logic is delegated to FeeConfigService.
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, SuperAdmin
from src.db.engine import get_db
from src.models.fee_config import FeeConfig
from src.schemas.fee_config import (
    FeeCalculationRequest,
    FeeCalculationResponse,
    FeeConfigCreate,
    FeeConfigResponse,
    FeeConfigUpdate,
)
from src.services.fee_config_service import FeeConfigService

router = APIRouter(prefix="/fee-configs", tags=["Fee Configurations"])


# ============ Dependency ============


def get_fee_config_service(db: Annotated[AsyncSession, Depends(get_db)]) -> FeeConfigService:
    """Create FeeConfigService instance."""
    return FeeConfigService(db)


# ============ API Endpoints ============


@router.get("", response_model=list[FeeConfigResponse])
async def list_fee_configs(
    service: Annotated[FeeConfigService, Depends(get_fee_config_service)],
    current_user: SuperAdmin,
) -> list[FeeConfig]:
    """List all fee configurations.

    Only accessible by super_admin users.
    """
    return await service.list_fee_configs()


@router.get("/{fee_config_id}", response_model=FeeConfigResponse)
async def get_fee_config(
    fee_config_id: int,
    service: Annotated[FeeConfigService, Depends(get_fee_config_service)],
    current_user: SuperAdmin,
) -> FeeConfig:
    """Get fee configuration by ID.

    Only accessible by super_admin users.
    """
    fee_config = await service.get_fee_config(fee_config_id)
    if not fee_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fee configuration {fee_config_id} not found",
        )
    return fee_config


@router.post("", response_model=FeeConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_fee_config(
    fee_config_data: FeeConfigCreate,
    service: Annotated[FeeConfigService, Depends(get_fee_config_service)],
    current_user: SuperAdmin,
) -> FeeConfig:
    """Create new fee configuration.

    Only accessible by super_admin users.
    If is_default is True, all other configs will be set to False.
    """
    try:
        return await service.create_fee_config(fee_config_data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{fee_config_id}", response_model=FeeConfigResponse)
async def update_fee_config(
    fee_config_id: int,
    fee_config_data: FeeConfigUpdate,
    service: Annotated[FeeConfigService, Depends(get_fee_config_service)],
    current_user: SuperAdmin,
) -> FeeConfig:
    """Update fee configuration.

    Only accessible by super_admin users.
    If is_default is set to True, all other configs will be set to False.
    """
    try:
        result = await service.update_fee_config(
            fee_config_id, fee_config_data.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fee configuration {fee_config_id} not found",
        )
    return result


@router.delete("/{fee_config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fee_config(
    fee_config_id: int,
    service: Annotated[FeeConfigService, Depends(get_fee_config_service)],
    current_user: SuperAdmin,
) -> None:
    """Delete fee configuration.

    Only accessible by super_admin users.
    Cannot delete if any users are using this configuration.
    """
    try:
        deleted = await service.delete_fee_config(fee_config_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fee configuration {fee_config_id} not found",
        )


@router.post("/calculate", response_model=FeeCalculationResponse)
async def calculate_fee(
    request: FeeCalculationRequest,
    service: Annotated[FeeConfigService, Depends(get_fee_config_service)],
    current_user: CurrentUser,
) -> FeeCalculationResponse:
    """Calculate fee for a transaction amount.

    Uses the current user's fee configuration.
    """
    try:
        result = await service.calculate_fee(
            user=current_user,
            amount=Decimal(str(request.amount)),
            transaction_type=request.transaction_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    return FeeCalculationResponse(
        amount=result["amount"],
        fee=result["fee"],
        total=result["total"],
        fee_config_name=result["fee_config_name"],
    )
