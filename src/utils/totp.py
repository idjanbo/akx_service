"""TOTP utilities and FastAPI dependencies for TOTP verification."""

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

import pyotp
from fastapi import HTTPException

from src.core.config import get_settings
from src.core.security import AESCipher
from src.models.user import User


def _get_cipher() -> AESCipher:
    """Get AES cipher for decrypting TOTP secrets."""
    settings = get_settings()
    return AESCipher(settings.aes_encryption_key)


def decrypt_totp_secret(encrypted_secret: str) -> str | None:
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


def verify_totp_code(user: User, totp_code: str) -> bool:
    """Verify TOTP code for user.

    Returns:
        True if valid, False otherwise
    """
    if not user.google_secret:
        return False
    secret = decrypt_totp_secret(user.google_secret)
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(totp_code)


def require_totp_code(user: User, totp_code: str) -> None:
    """验证 TOTP 验证码，失败直接抛出 HTTPException。"""
    if not user.google_secret:
        raise HTTPException(
            status_code=400,
            detail="未绑定 Google Authenticator",
        )
    secret = decrypt_totp_secret(user.google_secret)
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
        from src.utils.totp import totp_required
        from src.api.deps import TOTPUser

        @router.post("/sensitive-action")
        @totp_required
        async def sensitive_action(user: TOTPUser, data: RequestWithTOTP):
            # 已通过 TOTP 验证
            ...
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # 获取原函数的参数签名，将位置参数转换为关键字参数
        sig = inspect.signature(func)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        all_kwargs = bound.arguments

        user = all_kwargs.get("user")
        data = all_kwargs.get("data")

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


def generate_totp_secret() -> str:
    """Generate a new TOTP secret."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, username: str, issuer: str = "AKX") -> str:
    """Generate TOTP URI for QR code."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)
