"""AKX Crypto Payment Gateway - FastAPI Application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.db import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Startup: Initialize database tables
    Shutdown: Close database connections
    """
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    """Application factory.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Cryptocurrency Payment Gateway API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure properly in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from src.api.admin import router as admin_router
    from src.api.auth import router as auth_router
    from src.api.dashboard import router as dashboard_router
    from src.api.merchant import router as merchant_router
    from src.api.orders import router as orders_router
    from src.api.payment import router as payment_router
    from src.api.wallets import router as wallets_router

    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(payment_router, prefix="/api/v1/payment", tags=["payment"])
    app.include_router(merchant_router, prefix="/api/v1/merchant", tags=["merchant"])
    app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(orders_router, prefix="/api/orders", tags=["orders"])
    app.include_router(wallets_router, prefix="/api/wallets", tags=["wallets"])

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Application instance
app = create_app()
