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
    InvitationResponse,
    InviteMerchantRequest,
    InviteSupportRequest,
    PaginatedResponse,
    ResendInvitationRequest,
    ResetGoogleSecretResponse,
    ResetKeyResponse,
    SupportUserResponse,
    UpdateSupportPermissionsRequest,
    UpdateUserBalanceRequest,
    UpdateUserCreditLimitRequest,
    UpdateUserFeeConfigRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserResponse,
)
from src.services.invitation_service import InvitationService
from src.services.user_service import UserService
from src.utils.pagination import PaginationParams

router = APIRouter(prefix="/users", tags=["Users"])


# ============ Dependency ============


def get_user_service(db: Annotated[AsyncSession, Depends(get_db)]) -> UserService:
    """Create UserService instance."""
    return UserService(db)


def get_invitation_service(db: Annotated[AsyncSession, Depends(get_db)]) -> InvitationService:
    """Create InvitationService instance."""
    return InvitationService(db)


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


@router.patch("/support/{support_id}/status", response_model=SupportUserResponse)
async def toggle_support_status(
    support_id: int,
    request: UpdateUserStatusRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    current_user: CurrentUser,
) -> SupportUserResponse:
    """Toggle support user active status (merchant only)."""
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can manage support users",
        )

    try:
        user = await service.toggle_support_status(
            merchant=current_user,
            support_id=support_id,
            is_active=request.is_active,
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
    """Remove (deactivate) a support user.

    This deactivates the user account. To re-add them, send a new invitation.
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


# ============ Invitation Management (邀请管理) ============


@router.post("/invite-merchant", response_model=InvitationResponse)
async def invite_merchant(
    request: InviteMerchantRequest,
    service: Annotated[InvitationService, Depends(get_invitation_service)],
    current_user: SuperAdmin,
) -> InvitationResponse:
    """Invite a new merchant (super admin only).

    Sends an invitation email to the specified address.
    When the user registers via Clerk, they will be assigned the merchant role.
    """
    try:
        invitation = await service.invite_merchant(
            inviter=current_user,
            email=request.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return InvitationResponse(
        id=invitation.id,
        email=invitation.email_address,
        role="merchant",
        permissions=[],
        status=invitation.status or "pending",
        created_at=invitation.created_at,
    )


@router.post("/invite-support", response_model=InvitationResponse)
async def invite_support(
    request: InviteSupportRequest,
    service: Annotated[InvitationService, Depends(get_invitation_service)],
    current_user: CurrentUser,
) -> InvitationResponse:
    """Invite a new support user (merchant only).

    Sends an invitation email to the specified address.
    When the user registers via Clerk, they will be assigned as support
    under the current merchant with the specified permissions.
    """
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchants can invite support users",
        )

    try:
        invitation = await service.invite_support(
            merchant=current_user,
            email=request.email,
            permissions=request.permissions,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    metadata = invitation.public_metadata or {}
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email_address,
        role="support",
        permissions=metadata.get("permissions", []),
        status=invitation.status or "pending",
        created_at=invitation.created_at,
    )


@router.get("/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    service: Annotated[InvitationService, Depends(get_invitation_service)],
    current_user: CurrentUser,
) -> list[InvitationResponse]:
    """List pending invitations sent by the current user.

    - Super admins see merchant invitations they sent
    - Merchants see support invitations they sent
    """

    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.MERCHANT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and merchants can view invitations",
        )

    invitations = await service.list_invitations(current_user)
    return [
        InvitationResponse(
            id=inv["id"],
            email=inv["email"],
            role=inv["role"],
            permissions=inv["permissions"],
            status=inv["status"],
            created_at=inv["created_at"],
            expires_at=inv.get("expires_at"),
        )
        for inv in invitations
    ]


@router.post("/invitations/resend", response_model=InvitationResponse)
async def resend_invitation(
    request: ResendInvitationRequest,
    service: Annotated[InvitationService, Depends(get_invitation_service)],
    current_user: CurrentUser,
) -> InvitationResponse:
    """Resend an invitation.

    This revokes the old invitation and creates a new one with the same details.
    """
    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.MERCHANT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and merchants can resend invitations",
        )

    try:
        invitation = await service.resend_invitation(
            user=current_user,
            invitation_id=request.invitation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    metadata = invitation.public_metadata or {}
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email_address,
        role=metadata.get("role"),
        permissions=metadata.get("permissions", []),
        status=invitation.status or "pending",
        created_at=invitation.created_at,
    )


@router.delete("/invitations/{invitation_id}")
async def revoke_invitation(
    invitation_id: str,
    service: Annotated[InvitationService, Depends(get_invitation_service)],
    current_user: CurrentUser,
) -> dict:
    """Revoke a pending invitation."""
    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.MERCHANT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and merchants can revoke invitations",
        )

    try:
        await service.revoke_invitation(
            user=current_user,
            invitation_id=invitation_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {"message": "Invitation revoked successfully"}


# ============ Single User Operations (动态路由放最后) ============


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
