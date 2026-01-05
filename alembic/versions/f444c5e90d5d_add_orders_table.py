"""add_orders_table

Revision ID: f444c5e90d5d
Revises: 4dbe9519315c
Create Date: 2026-01-05 18:08:08.221614

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f444c5e90d5d"
down_revision: str | Sequence[str] | None = "4dbe9519315c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_no", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("out_trade_no", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("order_type", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("merchant_id", sa.Integer(), nullable=False),
        # Payment details
        sa.Column("token", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("chain", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("amount", sa.DECIMAL(precision=32, scale=8), nullable=False),
        sa.Column("fee", sa.DECIMAL(precision=32, scale=8), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.DECIMAL(precision=32, scale=8), nullable=False),
        # Address info
        sa.Column("wallet_address", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("to_address", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        # Blockchain info
        sa.Column("tx_hash", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("confirmations", sa.Integer(), nullable=False, server_default="0"),
        # Status
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
            server_default="pending",
        ),
        # Callback
        sa.Column("callback_url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column(
            "callback_status",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("callback_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_callback_at", sa.DateTime(), nullable=True),
        # Extra data
        sa.Column("extra_data", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True),
        sa.Column("remark", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        # Timestamps
        sa.Column("expire_time", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # Primary key
        sa.PrimaryKeyConstraint("id"),
        # Foreign key
        sa.ForeignKeyConstraint(["merchant_id"], ["users.id"]),
        # Unique constraint
        sa.UniqueConstraint("merchant_id", "out_trade_no", name="uq_merchant_out_trade_no"),
    )
    # Indexes
    op.create_index(op.f("ix_orders_order_no"), "orders", ["order_no"], unique=True)
    op.create_index(op.f("ix_orders_out_trade_no"), "orders", ["out_trade_no"], unique=False)
    op.create_index(op.f("ix_orders_merchant_id"), "orders", ["merchant_id"], unique=False)
    op.create_index(op.f("ix_orders_token"), "orders", ["token"], unique=False)
    op.create_index(op.f("ix_orders_chain"), "orders", ["chain"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_index(op.f("ix_orders_tx_hash"), "orders", ["tx_hash"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f("ix_orders_tx_hash"), table_name="orders")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_chain"), table_name="orders")
    op.drop_index(op.f("ix_orders_token"), table_name="orders")
    op.drop_index(op.f("ix_orders_merchant_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_out_trade_no"), table_name="orders")
    op.drop_index(op.f("ix_orders_order_no"), table_name="orders")
    # Drop table
    op.drop_table("orders")
