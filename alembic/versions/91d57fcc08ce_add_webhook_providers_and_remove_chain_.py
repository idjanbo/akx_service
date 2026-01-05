"""add_webhook_providers_and_remove_chain_rpc_url

Revision ID: 91d57fcc08ce
Revises: f444c5e90d5d
Create Date: 2026-01-05 19:07:06.313573

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91d57fcc08ce"
down_revision: str | Sequence[str] | None = "f444c5e90d5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema."""
    # Create webhook_providers table if not exists
    if not table_exists("webhook_providers"):
        op.create_table(
            "webhook_providers",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
            sa.Column(
                "provider_type",
                sa.Enum(
                    "trongrid",
                    "alchemy",
                    "helius",
                    "quicknode",
                    "moralis",
                    "custom",
                    name="webhookprovidertype",
                ),
                nullable=False,
            ),
            sa.Column("api_key", sa.Text(), nullable=True),
            sa.Column("api_secret", sa.Text(), nullable=True),
            sa.Column("webhook_secret", sa.Text(), nullable=True),
            sa.Column("webhook_url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
            sa.Column("webhook_id", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, default=True),
            sa.Column("remark", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # Create webhook_provider_chains table if not exists
    if not table_exists("webhook_provider_chains"):
        op.create_table(
            "webhook_provider_chains",
            sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
            sa.Column("provider_id", sa.Integer(), nullable=False),
            sa.Column("chain_id", sa.Integer(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, default=True),
            sa.Column("contract_addresses", sa.Text(), nullable=True),
            sa.Column("wallet_addresses", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["provider_id"], ["webhook_providers.id"]),
            sa.ForeignKeyConstraint(["chain_id"], ["chains.id"]),
        )
        op.create_index(
            "ix_webhook_provider_chains_provider_id", "webhook_provider_chains", ["provider_id"]
        )
        op.create_index(
            "ix_webhook_provider_chains_chain_id", "webhook_provider_chains", ["chain_id"]
        )

    # Remove rpc_url from chains table if exists
    if column_exists("chains", "rpc_url"):
        op.drop_column("chains", "rpc_url")


def downgrade() -> None:
    """Downgrade schema."""
    # Add back rpc_url to chains table if not exists
    if not column_exists("chains", "rpc_url"):
        op.add_column("chains", sa.Column("rpc_url", mysql.VARCHAR(length=500), nullable=True))

    # Drop webhook_provider_chains table if exists
    if table_exists("webhook_provider_chains"):
        op.drop_index("ix_webhook_provider_chains_chain_id", table_name="webhook_provider_chains")
        op.drop_index(
            "ix_webhook_provider_chains_provider_id", table_name="webhook_provider_chains"
        )
        op.drop_table("webhook_provider_chains")

    # Drop webhook_providers table if exists
    if table_exists("webhook_providers"):
        op.drop_table("webhook_providers")
