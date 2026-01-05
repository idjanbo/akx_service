"""Common FastAPI dependencies for API endpoints."""

from collections.abc import Callable
from functools import wraps
from typing import Annotated

import pyotp
from fastapi import Depends, HTTPException

from src.api.auth import get_current_user
from src.core.config import get_settings
from src.core.security import AESCipher
from src.models.user import User, UserRole


def _get_cipher() -> AESCipher:
    """Get AES cipher for decrypting TOTP secrets."""
    settings = get_settings()
    return AESCipher(settings.aes_encryption_key)


def _decrypt_totp_secret(encrypted_secret: str) -> str | None:
    """Decrypt TOTP secret from database.

    Returns:
        Decrypted secret or None if invalid/pending
    """
    try:
        cipher = _get_cipher()
        decrypted = cipher.decrypt(encrypted_secret)
        # 排除 pending 状态的密钥
        if decrypted.startswith("pending:"):
            return None
        return decrypted
    except Exception:
        return None


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
    secret = _decrypt_totp_secret(user.google_secret)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="未绑定 Google Authenticator，请先绑定后再操作",
        )
    return user


def require_totp_code(user: User, totp_code: str) -> None:
    """验证 TOTP 验证码，失败直接抛出 HTTPException。"""
    if not user.google_secret:
        raise HTTPException(
            status_code=400,
            detail="未绑定 Google Authenticator",
        )
    secret = _decrypt_totp_secret(user.google_secret)
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="未绑定 Google Authenticator",
        )
    totp = pyotp.TOTP(secret)
    if not totp.verify(totp_code):
        raise HTTPException(
            status_code=400,
            detail="TOTP 验证码错误",
        )


def totp_required(func: Callable) -> Callable:
    """装饰器：验证 TOTP 验证码。

    自动从函数参数中获取 user 和 data.totp_code 进行验证。

    Usage:
        @router.post("/sensitive-action")
        @totp_required
        async def sensitive_action(user: TOTPUser, data: RequestWithTOTP):
            # 已通过 TOTP 验证
            ...
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        user = kwargs.get("user")
        data = kwargs.get("data")

        if not user:
            raise HTTPException(status_code=400, detail="Missing user information")
        if not data:
            raise HTTPException(status_code=400, detail="Missing request data")

        totp_code = getattr(data, "totp_code", None)
        if not totp_code:
            raise HTTPException(status_code=400, detail="Missing TOTP code")

        require_totp_code(user, totp_code)
        return await func(*args, **kwargs)

    return wrapper


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
