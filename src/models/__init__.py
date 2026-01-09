"""Models module - SQLModel database entities."""

from src.models.chain import Chain
from src.models.exchange_rate import ExchangeRate, ExchangeRateMode, ExchangeRateSource
from src.models.fee_config import FeeConfig
from src.models.ledger import (
    BalanceChangeType,
    BalanceLedger,
)
from src.models.order import CallbackStatus, Order, OrderStatus, OrderType
from src.models.recharge import (
    CollectTask,
    CollectTaskStatus,
    RechargeAddress,
    RechargeAddressStatus,
    RechargeOrder,
    RechargeOrderStatus,
    generate_recharge_order_no,
)
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
    # Exchange Rate
    "ExchangeRateSource",
    "ExchangeRate",
    "ExchangeRateMode",
    # Order
    "Order",
    "OrderType",
    "OrderStatus",
    "CallbackStatus",
    # Chain & Token
    "Chain",
    "Token",
    "TokenChainSupport",
    # Wallet
    "Wallet",
    "WalletType",
    # Recharge (商户在线充值)
    "RechargeAddress",
    "RechargeAddressStatus",
    "RechargeOrder",
    "RechargeOrderStatus",
    "CollectTask",
    "CollectTaskStatus",
    "generate_recharge_order_no",
    # Ledger
    "BalanceLedger",
    "BalanceChangeType",
    # Webhook Provider
    "WebhookProvider",
    "WebhookProviderChain",
    "WebhookProviderType",
    # DEPRECATED - kept for backward compatibility
    "ChainEnum",
    "TokenEnum",
    "get_payment_method_expiry_deprecated",
]
