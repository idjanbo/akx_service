"""API module - route handlers and common dependencies."""

from fastapi import FastAPI

from src.api.deps import (
    CurrentUser,
    SuperAdmin,
    TOTPUser,
    totp_required,
)

__all__ = [
    "CurrentUser",
    "SuperAdmin",
    "TOTPUser",
    "register_routers",
    "totp_required",
]


def register_routers(app: FastAPI) -> None:
    """Register all API routers to the application.

    Args:
        app: FastAPI application instance
    """
    # Auth & User management
    from src.api.auth import router as auth_router
    from src.api.totp import router as totp_router
    from src.api.users import router as users_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(totp_router, prefix="/api")
    app.include_router(users_router, prefix="/api")

    # Wallet & Asset management
    from src.api.wallets import router as wallets_router

    app.include_router(wallets_router, prefix="/api/wallets", tags=["Wallets"])

    # Order & Payment
    from src.api.orders import router as orders_router
    from src.api.payment import router as payment_router

    app.include_router(orders_router, prefix="/api")
    app.include_router(payment_router)  # Payment API v1 (external)

    # Recharge & Collection (Merchant balance top-up)
    from src.api.recharges import router as recharges_router

    app.include_router(recharges_router, prefix="/api")

    # Ledger & Financial records
    from src.api.fee_configs import router as fee_configs_router
    from src.api.ledger import router as ledger_router

    app.include_router(fee_configs_router, prefix="/api")
    app.include_router(ledger_router, prefix="/api")

    # Merchant Settings
    from src.api.merchant_settings import router as merchant_settings_router

    app.include_router(merchant_settings_router, prefix="/api")

    # Exchange Rate management
    from src.api.exchange_rate_sources import router as exchange_rate_sources_router
    from src.api.exchange_rates import router as exchange_rates_router

    app.include_router(exchange_rate_sources_router, prefix="/api")
    app.include_router(exchange_rates_router, prefix="/api")

    # Web3 & Blockchain
    from src.api.chains_tokens import router as chains_tokens_router
    from src.api.webhook_providers import router as webhook_providers_router
    from src.api.webhooks import router as webhooks_router

    app.include_router(chains_tokens_router)
    app.include_router(webhook_providers_router, prefix="/api")
    app.include_router(webhooks_router)  # Blockchain webhook callbacks

    # Telegram Bot webhook
    from src.api.telegram_bot import router as telegram_bot_router

    app.include_router(telegram_bot_router, prefix="/api")

    # Cashier (public payment pages)
    from src.api.cashier import router as cashier_router

    app.include_router(cashier_router)  # Public pages at /pay/{order_no}
