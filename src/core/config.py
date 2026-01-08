"""AKX Crypto Payment Gateway - Core Configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, MySQLDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "AKX Payment Gateway"
    debug: bool = False
    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    # Database
    database_url: MySQLDsn = Field(..., description="MySQL connection string with aiomysql driver")

    # Security
    aes_encryption_key: str = Field(
        ..., description="Base64-encoded 32-byte AES key for private key encryption"
    )

    # Clerk Authentication
    clerk_secret_key: str = Field(..., description="Clerk secret key")
    clerk_publishable_key: str = Field(..., description="Clerk publishable key")

    # Frontend URL (for invitation redirects)
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend application URL for redirects",
    )

    # TRON (Primary Chain)
    tron_api_key: str = Field(default="", description="TronGrid API key")
    tron_network: Literal["mainnet", "shasta", "nile"] = Field(
        default="mainnet", description="TRON network"
    )

    # Ethereum
    eth_rpc_url: str = Field(default="", description="Ethereum RPC endpoint")

    # Solana
    solana_rpc_url: str = Field(
        default="https://api.mainnet-beta.solana.com",
        description="Solana RPC endpoint",
    )

    # Redis (for task queue)
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL for task queue",
    )

    # Webhook secrets (optional, for signature verification)
    alchemy_webhook_secret: str = Field(default="", description="Alchemy webhook signing key")
    helius_webhook_secret: str = Field(default="", description="Helius webhook auth token")

    # Payment settings
    deposit_expiry_seconds: int = Field(
        default=30, description="Deposit order expiry time in seconds"
    )
    timestamp_validity_minutes: int = Field(
        default=5, description="API request timestamp validity window in minutes"
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()  # type: ignore[call-arg]
