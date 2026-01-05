"""AKX Crypto Payment Gateway - FastAPI Application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import register_routers
from src.core.config import get_settings
from src.db import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Startup: Initialize database tables
    Shutdown: Close database connections
    """
    await init_db()
    yield
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
    allowed_origins = (
        ["*"]
        if settings.debug
        else [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register all API routers
    register_routers(app)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Application instance
app = create_app()
