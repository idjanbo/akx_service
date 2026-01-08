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
    """Merchant has insufficient balance for fee payment."""

    def __init__(
        self,
        required: "Decimal | None" = None,
        available: "Decimal | None" = None,
        message: str = "积分余额不足",
    ) -> None:
        details = {}
        if required is not None:
            details["required"] = str(required)
        if available is not None:
            details["available"] = str(available)
        super().__init__(message, details)


from decimal import Decimal  # noqa: E402 - 为避免循环导入放在下面


class ChainError(AKXError):
    """Blockchain interaction error."""

    pass


class TransactionError(ChainError):
    """Transaction broadcast or confirmation error."""

    pass


class WalletError(AKXError):
    """Wallet generation or key management error."""

    pass
