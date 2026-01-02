"""initial_schema

Revision ID: 0001
Revises:
Create Date: 2025-12-13

Initial database schema for AKX Payment Gateway.
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create initial database schema."""
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("clerk_id", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_clerk_id"), "users", ["clerk_id"], unique=True)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    # Merchants table
    op.create_table(
        "merchants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("merchant_no", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("deposit_key", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("withdraw_key", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("webhook_secret", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_merchants_merchant_no"), "merchants", ["merchant_no"], unique=True)
    op.create_index(op.f("ix_merchants_user_id"), "merchants", ["user_id"], unique=True)

    # Wallets table
    op.create_table(
        "wallets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("chain", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("wallet_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("address", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column(
            "encrypted_private_key", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wallets_address"), "wallets", ["address"], unique=True)
    op.create_index(op.f("ix_wallets_chain"), "wallets", ["chain"], unique=False)
    op.create_index(op.f("ix_wallets_user_id"), "wallets", ["user_id"], unique=False)
    op.create_index(op.f("ix_wallets_wallet_type"), "wallets", ["wallet_type"], unique=False)

    # Orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_no", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("merchant_ref", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("chain", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("token", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("fee", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("net_amount", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("wallet_address", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("to_address", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("tx_hash", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
        sa.Column("confirmations", sa.Integer(), nullable=False),
        sa.Column("chain_metadata", mysql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_chain"), "orders", ["chain"], unique=False)
    op.create_index(op.f("ix_orders_created_at"), "orders", ["created_at"], unique=False)
    op.create_index(op.f("ix_orders_merchant_ref"), "orders", ["merchant_ref"], unique=False)
    op.create_index(op.f("ix_orders_order_no"), "orders", ["order_no"], unique=True)
    op.create_index(op.f("ix_orders_order_type"), "orders", ["order_type"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_index(op.f("ix_orders_token"), "orders", ["token"], unique=False)
    op.create_index(op.f("ix_orders_tx_hash"), "orders", ["tx_hash"], unique=False)
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False)

    # Transactions (ledger) table
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("direction", sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("pre_balance", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("post_balance", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transactions_created_at"), "transactions", ["created_at"], unique=False
    )
    op.create_index(op.f("ix_transactions_direction"), "transactions", ["direction"], unique=False)
    op.create_index(op.f("ix_transactions_order_id"), "transactions", ["order_id"], unique=False)
    op.create_index(
        op.f("ix_transactions_transaction_type"), "transactions", ["transaction_type"], unique=False
    )
    op.create_index(op.f("ix_transactions_user_id"), "transactions", ["user_id"], unique=False)

    # Webhook deliveries table
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("event_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.Column("payload", mysql.JSON(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_webhook_deliveries_created_at"), "webhook_deliveries", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_deliveries_event_id"), "webhook_deliveries", ["event_id"], unique=True
    )
    op.create_index(
        op.f("ix_webhook_deliveries_event_type"), "webhook_deliveries", ["event_type"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_deliveries_order_id"), "webhook_deliveries", ["order_id"], unique=False
    )
    op.create_index(
        op.f("ix_webhook_deliveries_success"), "webhook_deliveries", ["success"], unique=False
    )

    # Fee config table
    op.create_table(
        "fee_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("chain", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("order_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("fee_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("fee_value", sa.Numeric(precision=32, scale=8), nullable=False),
        sa.Column("min_amount", sa.Numeric(precision=32, scale=8), nullable=True),
        sa.Column("max_amount", sa.Numeric(precision=32, scale=8), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fee_configs_chain"), "fee_configs", ["chain"], unique=False)
    op.create_index(op.f("ix_fee_configs_name"), "fee_configs", ["name"], unique=True)
    op.create_index(op.f("ix_fee_configs_order_type"), "fee_configs", ["order_type"], unique=False)


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("fee_configs")
    op.drop_table("webhook_deliveries")
    op.drop_table("transactions")
    op.drop_table("orders")
    op.drop_table("wallets")
    op.drop_table("merchants")
    op.drop_table("users")
