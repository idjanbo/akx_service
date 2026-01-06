"""Alembic environment configuration for async MySQL.

Supports both online (async) and offline migrations.
Reads DATABASE_URL from environment variable.
"""

import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context

# Load .env file
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models to ensure they are registered with SQLModel.metadata
# This is required for autogenerate to detect models
from src.models.chain import Chain  # noqa: F401, E402
from src.models.fee_config import FeeConfig  # noqa: F401, E402
from src.models.ledger import BalanceLedger  # noqa: F401, E402
from src.models.order import Order  # noqa: F401, E402
from src.models.recharge import CollectTask, RechargeAddress, RechargeOrder  # noqa: F401, E402
from src.models.token import Token, TokenChainSupport  # noqa: F401, E402
from src.models.user import User  # noqa: F401, E402
from src.models.wallet import Wallet  # noqa: F401, E402
from src.models.webhook_provider import WebhookProvider, WebhookProviderChain  # noqa: F401, E402

# Set target metadata for autogenerate support
target_metadata = SQLModel.metadata

# Get database URL from environment
# Convert mysql+aiomysql to mysql+pymysql for sync operations (offline mode)
# Keep mysql+aiomysql for async operations (online mode)
DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_sync_url() -> str:
    """Convert async URL to sync URL for offline migrations."""
    return DATABASE_URL.replace("+aiomysql", "+pymysql")


def get_async_url() -> str:
    """Get async URL for online migrations."""
    return DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    In this scenario we need to create an async Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_async_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
