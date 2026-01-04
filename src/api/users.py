"""User management API routes."""

import math
from datetime import datetime
from typing import Annotated

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from src.api.auth import require_admin
from src.db import get_db
from src.models.fee_config import FeeConfig
from src.models.user import User, UserRole, generate_api_key
from src.schemas.user import (
    PaginatedResponse,
    ResetGoogleSecretResponse,
    ResetKeyResponse,
    UpdateUserBalanceRequest,
    UpdateUserCreditLimitRequest,
    UpdateUserFeeConfigRequest,
    UpdateUserRoleRequest,
    UpdateUserStatusRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


async def _get_user_or_404(db: AsyncSession, user_id: int) -> User:
    """Get user by ID or raise 404."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.fee_config))
        .where(User.id == user_id)
        .where(User.role != UserRole.SUPER_ADMIN)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
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
    # Build base query
    query = (
        select(User).options(selectinload(User.fee_config)).where(User.role != UserRole.SUPER_ADMIN)
    )

    # Apply filters
    if search:
        query = query.where(User.email.ilike(f"%{search}%"))
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Calculate pagination
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size

    # Fetch paginated results
    query = query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    return PaginatedResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> User:
    """Get a single user by ID (admin only)."""
    return await _get_user_or_404(db, user_id)


@router.patch("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    request: UpdateUserRoleRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> User:
    """Update user role (admin only)."""
    user = await _get_user_or_404(db, user_id)

    # Cannot set role to super_admin
    if request.role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot assign super_admin role",
        )

    user.role = request.role
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.patch("/{user_id}/status", response_model=UserResponse)
async def update_user_status(
    user_id: int,
    request: UpdateUserStatusRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> User:
    """Update user active status (admin only)."""
    user = await _get_user_or_404(db, user_id)

    user.is_active = request.is_active
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.patch("/{user_id}/balance", response_model=UserResponse)
async def update_user_balance(
    user_id: int,
    request: UpdateUserBalanceRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> User:
    """Update user balance (admin only)."""
    user = await _get_user_or_404(db, user_id)

    user.balance = request.balance
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.patch("/{user_id}/credit-limit", response_model=UserResponse)
async def update_user_credit_limit(
    user_id: int,
    request: UpdateUserCreditLimitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> User:
    """Update user credit limit (admin only)."""
    user = await _get_user_or_404(db, user_id)

    if request.credit_limit < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credit limit cannot be negative",
        )

    user.credit_limit = request.credit_limit
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.patch("/{user_id}/fee-config", response_model=UserResponse)
async def update_user_fee_config(
    user_id: int,
    request: UpdateUserFeeConfigRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> User:
    """Update user fee configuration (admin only)."""
    user = await _get_user_or_404(db, user_id)

    if request.fee_config_id is not None:
        # Verify fee config exists
        result = await db.execute(select(FeeConfig).where(FeeConfig.id == request.fee_config_id))
        fee_config = result.scalar_one_or_none()
        if not fee_config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fee config not found",
            )

    user.fee_config_id = request.fee_config_id
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.post("/{user_id}/reset-deposit-key", response_model=ResetKeyResponse)
async def reset_deposit_key(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> ResetKeyResponse:
    """Reset user deposit API key (admin only)."""
    user = await _get_user_or_404(db, user_id)

    new_key = generate_api_key()
    user.deposit_key = new_key
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()

    return ResetKeyResponse(key=new_key)


@router.post("/{user_id}/reset-withdraw-key", response_model=ResetKeyResponse)
async def reset_withdraw_key(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> ResetKeyResponse:
    """Reset user withdrawal API key (admin only)."""
    user = await _get_user_or_404(db, user_id)

    new_key = generate_api_key()
    user.withdraw_key = new_key
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()

    return ResetKeyResponse(key=new_key)


@router.post("/{user_id}/reset-google-secret", response_model=ResetGoogleSecretResponse)
async def reset_google_secret(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin())],
) -> ResetGoogleSecretResponse:
    """Reset user Google authenticator secret (admin only)."""
    user = await _get_user_or_404(db, user_id)

    # Generate new TOTP secret
    secret = pyotp.random_base32()
    user.google_secret = secret
    user.updated_at = datetime.utcnow()
    db.add(user)
    await db.commit()

    # Generate QR code URI
    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(name=user.email, issuer_name="AKX Payment")

    return ResetGoogleSecretResponse(secret=secret, qr_uri=qr_uri)
