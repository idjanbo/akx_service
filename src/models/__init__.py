"""Models module - SQLModel database entities."""

from src.models.chain import Chain
from src.models.fee_config import FeeConfig
from src.models.ledger import (
    AddressTransaction,
    AddressTransactionType,
    BalanceChangeType,
    BalanceLedger,
    RechargeRecord,
    RechargeStatus,
    RechargeType,
)
from src.models.order import CallbackStatus, Order, OrderStatus, OrderType
from src.models.payment_channel import ChannelStatus, PaymentChannel
from src.models.token import Token, TokenChainSupport
from src.models.user import User, UserRole
from src.models.wallet import (
    ChainEnum,  # DEPRECATED
    TokenEnum,  # DEPRECATED
    Wallet,
    WalletType,
    get_payment_method_expiry_deprecated,  # DEPRECATED
)
from src.models.webhook_provider import (
    WebhookProvider,
    WebhookProviderChain,
    WebhookProviderType,
)

__all__ = [
    # User
    "User",
    "UserRole",
    # Fee Config
    "FeeConfig",
    # Order
    "Order",
    "OrderType",
    "OrderStatus",
    "CallbackStatus",
    # Payment Channel
    "PaymentChannel",
    "ChannelStatus",
    # Chain & Token (New)
    "Chain",
    "Token",
    "TokenChainSupport",
    # Wallet
    "Wallet",
    "WalletType",
    # Ledger
    "AddressTransaction",
    "AddressTransactionType",
    "BalanceLedger",
    "BalanceChangeType",
    "RechargeRecord",
    "RechargeStatus",
    "RechargeType",
    # Webhook Provider
    "WebhookProvider",
    "WebhookProviderChain",
    "WebhookProviderType",
    # DEPRECATED - kept for backward compatibility
    "ChainEnum",
    "TokenEnum",
    "get_payment_method_expiry_deprecated",
]
