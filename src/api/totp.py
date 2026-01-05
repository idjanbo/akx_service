"""AKX Crypto Payment Gateway - TOTP (2FA) API."""

from typing import Annotated

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser
from src.core.config import get_settings
from src.core.security import AESCipher
from src.db import get_db

router = APIRouter(prefix="/totp", tags=["totp"])


# --- Schemas ---


class TOTPSetupResponse(BaseModel):
    """Response for TOTP setup - contains secret and QR URI."""

    secret: str = Field(description="Base32 encoded secret for manual entry")
    qr_uri: str = Field(description="otpauth:// URI for QR code scanning")


class TOTPVerifyRequest(BaseModel):
    """Request to verify a TOTP code."""

    code: str = Field(min_length=6, max_length=6, description="6-digit TOTP code")


class TOTPVerifyResponse(BaseModel):
    """Response for TOTP verification."""

    valid: bool
    message: str


class TOTPStatusResponse(BaseModel):
    """Response for TOTP status check."""

    enabled: bool
    message: str


# --- Helper Functions ---


def get_cipher() -> AESCipher:
    """Get AES cipher for encrypting/decrypting TOTP secrets."""
    settings = get_settings()
    return AESCipher(settings.aes_encryption_key)


# --- API Endpoints ---


@router.get("/status", response_model=TOTPStatusResponse)
async def get_totp_status(
    current_user: CurrentUser,
) -> TOTPStatusResponse:
    """Check if TOTP is enabled for current user."""
    # Check both None and empty string, also exclude pending secrets
    secret = current_user.google_secret
    enabled = bool(secret) and not secret.startswith("pending:")
    return TOTPStatusResponse(
        enabled=enabled,
        message="2FA 已启用" if enabled else "2FA 未启用",
    )


@router.post("/setup", response_model=TOTPSetupResponse)
async def setup_totp(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TOTPSetupResponse:
    """Generate a new TOTP secret for the user.

    Note: This does NOT enable 2FA yet. User must verify the code first
    using the /totp/enable endpoint.
    """
    # Generate new secret
    secret = pyotp.random_base32()

    # Create TOTP instance for URI generation
    totp = pyotp.TOTP(secret)
    qr_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name="AKX Payment",
    )

    # Store encrypted secret temporarily (not enabled until verified)
    # We'll use a temporary field approach - store but mark as pending
    cipher = get_cipher()
    encrypted_secret = cipher.encrypt(f"pending:{secret}")
    current_user.google_secret = encrypted_secret

    db.add(current_user)
    await db.commit()

    return TOTPSetupResponse(
        secret=secret,
        qr_uri=qr_uri,
    )


@router.post("/enable", response_model=TOTPVerifyResponse)
async def enable_totp(
    request: TOTPVerifyRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TOTPVerifyResponse:
    """Enable TOTP after verifying the code.

    User must first call /setup to get the secret, scan the QR code,
    then call this endpoint with the generated code to enable 2FA.
    """
    if not current_user.google_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先调用 /setup 获取密钥",
        )

    cipher = get_cipher()
    try:
        decrypted = cipher.decrypt(current_user.google_secret)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="解密密钥失败",
        ) from e

    # Check if already enabled (not pending)
    if not decrypted.startswith("pending:"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 已经启用",
        )

    # Extract the actual secret
    secret = decrypted.replace("pending:", "")

    # Verify the code
    totp = pyotp.TOTP(secret)
    if not totp.verify(request.code, valid_window=1):
        return TOTPVerifyResponse(
            valid=False,
            message="验证码无效，请重试",
        )

    # Code is valid - enable 2FA by storing without "pending:" prefix
    current_user.google_secret = cipher.encrypt(secret)
    db.add(current_user)
    await db.commit()

    return TOTPVerifyResponse(
        valid=True,
        message="2FA 已成功启用",
    )


@router.post("/verify", response_model=TOTPVerifyResponse)
async def verify_totp(
    request: TOTPVerifyRequest,
    current_user: CurrentUser,
) -> TOTPVerifyResponse:
    """Verify a TOTP code for sensitive operations.

    Use this endpoint before performing sensitive operations like:
    - Withdrawals
    - API key regeneration
    - Exporting private keys
    """
    if not current_user.google_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 未启用",
        )

    cipher = get_cipher()
    try:
        decrypted = cipher.decrypt(current_user.google_secret)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="解密密钥失败",
        ) from e

    # Check if still pending
    if decrypted.startswith("pending:"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 设置未完成，请先完成启用流程",
        )

    # Verify the code
    totp = pyotp.TOTP(decrypted)
    is_valid = totp.verify(request.code, valid_window=1)

    return TOTPVerifyResponse(
        valid=is_valid,
        message="验证成功" if is_valid else "验证码无效",
    )


@router.post("/disable", response_model=TOTPVerifyResponse)
async def disable_totp(
    request: TOTPVerifyRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TOTPVerifyResponse:
    """Disable TOTP for current user.

    Requires verification with current TOTP code for security.
    """
    if not current_user.google_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 未启用",
        )

    cipher = get_cipher()
    try:
        decrypted = cipher.decrypt(current_user.google_secret)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="解密密钥失败",
        ) from e

    # Check if still pending (can disable without verification)
    if decrypted.startswith("pending:"):
        current_user.google_secret = None
        db.add(current_user)
        await db.commit()
        return TOTPVerifyResponse(
            valid=True,
            message="已取消 2FA 设置",
        )

    # Verify the code before disabling
    totp = pyotp.TOTP(decrypted)
    if not totp.verify(request.code, valid_window=1):
        return TOTPVerifyResponse(
            valid=False,
            message="验证码无效，无法禁用 2FA",
        )

    # Disable 2FA
    current_user.google_secret = None
    db.add(current_user)
    await db.commit()

    return TOTPVerifyResponse(
        valid=True,
        message="2FA 已禁用",
    )
