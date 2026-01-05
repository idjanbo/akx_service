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
    from src.api.auth import router as auth_router
    from src.api.chains_tokens import router as chains_tokens_router
    from src.api.fee_configs import router as fee_configs_router
    from src.api.totp import router as totp_router
    from src.api.users import router as users_router
    from src.api.wallets import router as wallets_router

    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(users_router, prefix="/api", tags=["users"])
    app.include_router(wallets_router, prefix="/api/wallets", tags=["wallets"])
    app.include_router(chains_tokens_router)
    app.include_router(fee_configs_router, prefix="/api")
    app.include_router(totp_router, prefix="/api", tags=["totp"])

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Application instance
app = create_app()
