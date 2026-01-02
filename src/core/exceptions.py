"""AKX Crypto Payment Gateway - Custom exceptions."""

from typing import Any


class AKXError(Exception):
    """Base exception for all AKX errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(AKXError):
    """Authentication failed."""

    pass


class AuthorizationError(AKXError):
    """User lacks permission for this action."""

    pass


class ValidationError(AKXError):
    """Input validation failed."""

    pass


class InsufficientBalanceError(AKXError):
    """Merchant has insufficient balance for withdrawal."""

    pass


class ChainError(AKXError):
    """Blockchain interaction error."""

    pass


class TransactionError(ChainError):
    """Transaction broadcast or confirmation error."""

    pass


class WalletError(AKXError):
    """Wallet generation or key management error."""

    pass
