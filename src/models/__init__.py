"""Models module - SQLModel database entities."""

from src.models.chain import Chain
from src.models.token import Token, TokenChainSupport
from src.models.user import User, UserRole
from src.models.wallet import (
    ChainEnum,  # DEPRECATED
    TokenEnum,  # DEPRECATED
    Wallet,
    WalletType,
    get_payment_method_expiry_deprecated,  # DEPRECATED
)

__all__ = [
    # User
    "User",
    "UserRole",
    # Chain & Token (New)
    "Chain",
    "Token",
    "TokenChainSupport",
    # Wallet
    "Wallet",
    "WalletType",
    # DEPRECATED - kept for backward compatibility
    "ChainEnum",
    "TokenEnum",
    "get_payment_method_expiry_deprecated",
]
