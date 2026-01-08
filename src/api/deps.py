"""Common FastAPI dependencies for API endpoints."""

from typing import Annotated

from fastapi import Depends, HTTPException

from src.api.auth import get_current_user
from src.models.user import User, UserRole
from src.utils.totp import decrypt_totp_secret, require_totp_code, totp_required

__all__ = [
    "CurrentUser",
    "SuperAdmin",
    "TOTPUser",
    "require_totp_code",
    "totp_required",
]


async def get_totp_verified_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """确保用户已绑定 TOTP 的依赖。

    用于敏感操作前检查用户是否已绑定 Google Authenticator。
    注意：此依赖只检查是否绑定，不验证验证码。
    """
    if not user.google_secret:
        raise HTTPException(
            status_code=400,
            detail="未绑定 Google Authenticator，请先绑定后再操作",
        )
    # 检查是否真正启用（不是 pending 状态）
    secret = decrypt_totp_secret(user.google_secret)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="未绑定 Google Authenticator，请先绑定后再操作",
        )
    return user


async def require_super_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """确保用户是超级管理员。"""
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="需要超级管理员权限",
        )
    return user


# ============ Type Aliases for Common Dependencies ============
# 使用这些类型别名可以让代码更简洁

# 当前用户（已认证）
CurrentUser = Annotated[User, Depends(get_current_user)]

# 已绑定 TOTP 的用户（只检查绑定，不验证码）
TOTPUser = Annotated[User, Depends(get_totp_verified_user)]

# 超级管理员
SuperAdmin = Annotated[User, Depends(require_super_admin)]
