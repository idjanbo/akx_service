"""User management API routes.

Provides REST API endpoints for user management.
Business logic is delegated to UserService.
"""

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, SuperAdmin
from src.db import get_db
from src.models.user import User, UserRole
from src.schemas.user import (
    AddSupportUserRequest,
    PaginatedResponse,
    ResetGoogleSecretResponse,
    ResetKeyResponse,
    SearchUserResponse,
    SupportUserResponse,
    UpdateSupportPermissionsRequest,
    UpdateUserBalanceRequest,
    UpdateUserCreditLimitRequest,
    UpdateUserFeeConfigRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserResponse,
)
from src.services.user_service import UserService
from src.utils.pagination import PaginationParams

router = APIRouter(prefix="/users", tags=["Users"])


# ============ Dependency ============


def get_user_service(db: Annotated[AsyncSession, Depends(get_db)]) -> UserService:
    """Create UserService instance."""
    return UserService(db)


# ============ API Endpoints ============


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search by email"),
    role: UserRole | None = Query(default=None, description="Filter by role"),
    is_active: bool | None = Query(default=None, description="Filter by status"),
) -> PaginatedResponse[UserResponse]:
    """Get paginated users with search and filters (admin only).

    Super admins are excluded from the list to prevent
    accidental modification of admin accounts.

    Args:
        page: Page number (starts from 1)
        page_size: Number of items per page (1-100)
        search: Search term for email
        role: Filter by user role
        is_active: Filter by active status

    Returns:
        Paginated list of users with metadata
    """
    params = PaginationParams(page=page, page_size=page_size)
    result = await service.list_users(
        params=params,
        search=search,
        role=role,
        is_active=is_active,
    )

    total_pages = math.ceil(result.total / page_size) if result.total > 0 else 1

    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=total_pages,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> User:
    """Get a single user by ID (admin only)."""
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    request: UpdateUserRoleRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> User:
    """Update user role (admin only)."""
    try:
        user = await service.update_user_role(user_id, request.role)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: int,
    request: UpdateUserStatusRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> User:
    """Update user active status (admin only)."""
    user = await service.update_user_status(user_id, request.is_active)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/balance", response_model=UserResponse)
async def update_user_balance(
    user_id: int,
    request: UpdateUserBalanceRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> User:
    """Update user balance (admin only)."""
    user = await service.update_user_balance(user_id, request.balance)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/credit-limit", response_model=UserResponse)
async def update_user_credit_limit(
    user_id: int,
    request: UpdateUserCreditLimitRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> User:
    """Update user credit limit (admin only)."""
    try:
        user = await service.update_user_credit_limit(user_id, request.credit_limit)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}/fee-config", response_model=UserResponse)
async def update_user_fee_config(
    user_id: int,
    request: UpdateUserFeeConfigRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> User:
    """Update user fee configuration (admin only)."""
    try:
        user = await service.update_user_fee_config(user_id, request.fee_config_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/{user_id}/reset-deposit-key", response_model=ResetKeyResponse)
async def reset_deposit_key(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> ResetKeyResponse:
    """Reset user deposit API key (admin only)."""
    new_key = await service.reset_deposit_key(user_id)
    if not new_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ResetKeyResponse(key=new_key)


@router.post("/{user_id}/reset-withdraw-key", response_model=ResetKeyResponse)
async def reset_withdraw_key(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> ResetKeyResponse:
    """Reset user withdrawal API key (admin only)."""
    new_key = await service.reset_withdraw_key(user_id)
    if not new_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ResetKeyResponse(key=new_key)


@router.post("/{user_id}/reset-google-secret", response_model=ResetGoogleSecretResponse)
async def reset_google_secret(
    user_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: SuperAdmin,
) -> ResetGoogleSecretResponse:
    """Reset user Google authenticator secret (admin only)."""
    result = await service.reset_google_secret(user_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ResetGoogleSecretResponse(secret=result["secret"], qr_uri=result["qr_uri"])


# ============ Support User Management (商户管理客服) ============


@router.get("/support/list", response_model=list[SupportUserResponse])
async def list_support_users(
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: CurrentUser,
) -> list[SupportUserResponse]:
    """List all support users for the current merchant.

    Only merchants can manage support users.
    """
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can manage support users",
        )

    users = await service.list_support_users(current_user)
    return [SupportUserResponse.model_validate(u) for u in users]


@router.get("/support/search", response_model=list[SearchUserResponse])
async def search_users_for_support(
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: CurrentUser,
    email: str = Query(description="Email to search for"),
) -> list[SearchUserResponse]:
    """Search for users that can be added as support.

    Only guest users can be added as support.
    """
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can manage support users",
        )

    users = await service.search_users_for_support(email, current_user)
    return [SearchUserResponse.model_validate(u) for u in users]


@router.post("/support", response_model=SupportUserResponse)
async def add_support_user(
    request: AddSupportUserRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: CurrentUser,
) -> SupportUserResponse:
    """Add a user as support for the current merchant.

    The target user must be a guest user (not already merchant/support/admin).
    """
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can manage support users",
        )

    try:
        user = await service.add_support_user(
            merchant=current_user,
            user_id=request.user_id,
            permissions=request.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return SupportUserResponse.model_validate(user)


@router.patch("/support/{support_id}/permissions", response_model=SupportUserResponse)
async def update_support_permissions(
    support_id: int,
    request: UpdateSupportPermissionsRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: CurrentUser,
) -> SupportUserResponse:
    """Update support user permissions."""
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can manage support users",
        )

    try:
        user = await service.update_support_permissions(
            merchant=current_user,
            support_id=support_id,
            permissions=request.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return SupportUserResponse.model_validate(user)


@router.delete("/support/{support_id}")
async def remove_support_user(
    support_id: int,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: CurrentUser,
) -> dict:
    """Remove a support user (reverts to guest).

    This doesn't delete the user, just removes the support relationship.
    """
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can manage support users",
        )

    try:
        removed = await service.remove_support_user(
            merchant=current_user,
            support_id=support_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Support user not found")

    return {"message": "Support user removed successfully"}
