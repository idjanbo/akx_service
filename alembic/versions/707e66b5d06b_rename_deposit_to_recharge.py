"""rename_deposit_to_recharge

Revision ID: 707e66b5d06b
Revises: 27af6ceb1e66
Create Date: 2026-01-07 01:17:54.140830

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "707e66b5d06b"
down_revision: str | Sequence[str] | None = "27af6ceb1e66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: rename deposit_* to recharge_*."""

    # 1. Drop ALL foreign key constraints on deposit_addresses and deposit_orders
    # deposit_addresses FKs
    op.drop_constraint(
        "deposit_addresses_ibfk_1", "deposit_addresses", type_="foreignkey"
    )  # wallet_id
    op.drop_constraint(
        "deposit_addresses_ibfk_2", "deposit_addresses", type_="foreignkey"
    )  # chain_id
    op.drop_constraint(
        "deposit_addresses_ibfk_3", "deposit_addresses", type_="foreignkey"
    )  # token_id
    op.drop_constraint(
        "deposit_addresses_ibfk_4", "deposit_addresses", type_="foreignkey"
    )  # user_id

    # deposit_orders FKs
    op.drop_constraint("deposit_orders_ibfk_1", "deposit_orders", type_="foreignkey")  # user_id
    op.drop_constraint(
        "deposit_orders_ibfk_2", "deposit_orders", type_="foreignkey"
    )  # deposit_address_id
    op.drop_constraint("deposit_orders_ibfk_3", "deposit_orders", type_="foreignkey")  # chain_id
    op.drop_constraint("deposit_orders_ibfk_4", "deposit_orders", type_="foreignkey")  # token_id

    # collect_tasks FK to deposit_addresses
    op.drop_constraint("collect_tasks_ibfk_1", "collect_tasks", type_="foreignkey")

    # 2. Drop all indexes on deposit_addresses
    op.drop_index("ix_deposit_addresses_chain_id", table_name="deposit_addresses")
    op.drop_index("ix_deposit_addresses_status", table_name="deposit_addresses")
    op.drop_index("ix_deposit_addresses_status_chain", table_name="deposit_addresses")
    op.drop_index("ix_deposit_addresses_token_id", table_name="deposit_addresses")
    op.drop_index("ix_deposit_addresses_user_chain_token", table_name="deposit_addresses")
    op.drop_index("ix_deposit_addresses_user_id", table_name="deposit_addresses")
    op.drop_index("ix_deposit_addresses_wallet_id", table_name="deposit_addresses")

    # 3. Drop all indexes on deposit_orders
    op.drop_index("ix_deposit_orders_chain_id", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_created_at", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_deposit_address_id", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_expires_at", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_order_no", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_status", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_status_expires", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_token_id", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_tx_hash", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_user_id", table_name="deposit_orders")
    op.drop_index("ix_deposit_orders_user_status", table_name="deposit_orders")

    # 4. Drop index on collect_tasks
    op.drop_index("ix_collect_tasks_deposit_address_id", table_name="collect_tasks")

    # 5. Rename tables
    op.rename_table("deposit_addresses", "recharge_addresses")
    op.rename_table("deposit_orders", "recharge_orders")

    # 6. Rename columns
    op.alter_column(
        "recharge_addresses",
        "total_deposited",
        new_column_name="total_recharged",
        existing_type=sa.DECIMAL(precision=32, scale=8),
        existing_nullable=False,
    )
    op.alter_column(
        "recharge_addresses",
        "last_deposit_at",
        new_column_name="last_recharge_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "recharge_orders",
        "deposit_address_id",
        new_column_name="recharge_address_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "collect_tasks",
        "deposit_address_id",
        new_column_name="recharge_address_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # 7. Create new indexes on recharge_addresses
    op.create_index("ix_recharge_addresses_chain_id", "recharge_addresses", ["chain_id"])
    op.create_index("ix_recharge_addresses_status", "recharge_addresses", ["status"])
    op.create_index(
        "ix_recharge_addresses_status_chain", "recharge_addresses", ["status", "chain_id"]
    )
    op.create_index("ix_recharge_addresses_token_id", "recharge_addresses", ["token_id"])
    op.create_index(
        "ix_recharge_addresses_user_chain_token",
        "recharge_addresses",
        ["user_id", "chain_id", "token_id"],
    )
    op.create_index("ix_recharge_addresses_user_id", "recharge_addresses", ["user_id"])
    op.create_index(
        "ix_recharge_addresses_wallet_id", "recharge_addresses", ["wallet_id"], unique=True
    )

    # 8. Create new indexes on recharge_orders
    op.create_index("ix_recharge_orders_chain_id", "recharge_orders", ["chain_id"])
    op.create_index("ix_recharge_orders_created_at", "recharge_orders", ["created_at"])
    op.create_index("ix_recharge_orders_expires_at", "recharge_orders", ["expires_at"])
    op.create_index("ix_recharge_orders_order_no", "recharge_orders", ["order_no"], unique=True)
    op.create_index(
        "ix_recharge_orders_recharge_address_id", "recharge_orders", ["recharge_address_id"]
    )
    op.create_index("ix_recharge_orders_status", "recharge_orders", ["status"])
    op.create_index(
        "ix_recharge_orders_status_expires", "recharge_orders", ["status", "expires_at"]
    )
    op.create_index("ix_recharge_orders_token_id", "recharge_orders", ["token_id"])
    op.create_index("ix_recharge_orders_tx_hash", "recharge_orders", ["tx_hash"])
    op.create_index("ix_recharge_orders_user_id", "recharge_orders", ["user_id"])
    op.create_index("ix_recharge_orders_user_status", "recharge_orders", ["user_id", "status"])

    # 9. Create new index on collect_tasks
    op.create_index(
        "ix_collect_tasks_recharge_address_id", "collect_tasks", ["recharge_address_id"]
    )

    # 10. Recreate ALL foreign key constraints
    # recharge_addresses FKs
    op.create_foreign_key(
        "recharge_addresses_ibfk_1", "recharge_addresses", "wallets", ["wallet_id"], ["id"]
    )
    op.create_foreign_key(
        "recharge_addresses_ibfk_2", "recharge_addresses", "chains", ["chain_id"], ["id"]
    )
    op.create_foreign_key(
        "recharge_addresses_ibfk_3", "recharge_addresses", "tokens", ["token_id"], ["id"]
    )
    op.create_foreign_key(
        "recharge_addresses_ibfk_4", "recharge_addresses", "users", ["user_id"], ["id"]
    )

    # recharge_orders FKs
    op.create_foreign_key("recharge_orders_ibfk_1", "recharge_orders", "users", ["user_id"], ["id"])
    op.create_foreign_key(
        "recharge_orders_ibfk_2",
        "recharge_orders",
        "recharge_addresses",
        ["recharge_address_id"],
        ["id"],
    )
    op.create_foreign_key(
        "recharge_orders_ibfk_3", "recharge_orders", "chains", ["chain_id"], ["id"]
    )
    op.create_foreign_key(
        "recharge_orders_ibfk_4", "recharge_orders", "tokens", ["token_id"], ["id"]
    )

    # collect_tasks FK
    op.create_foreign_key(
        "collect_tasks_ibfk_1",
        "collect_tasks",
        "recharge_addresses",
        ["recharge_address_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema: rename recharge_* back to deposit_*."""

    # 1. Drop ALL foreign key constraints
    # recharge_addresses FKs
    op.drop_constraint("recharge_addresses_ibfk_1", "recharge_addresses", type_="foreignkey")
    op.drop_constraint("recharge_addresses_ibfk_2", "recharge_addresses", type_="foreignkey")
    op.drop_constraint("recharge_addresses_ibfk_3", "recharge_addresses", type_="foreignkey")
    op.drop_constraint("recharge_addresses_ibfk_4", "recharge_addresses", type_="foreignkey")

    # recharge_orders FKs
    op.drop_constraint("recharge_orders_ibfk_1", "recharge_orders", type_="foreignkey")
    op.drop_constraint("recharge_orders_ibfk_2", "recharge_orders", type_="foreignkey")
    op.drop_constraint("recharge_orders_ibfk_3", "recharge_orders", type_="foreignkey")
    op.drop_constraint("recharge_orders_ibfk_4", "recharge_orders", type_="foreignkey")

    # collect_tasks FK
    op.drop_constraint("collect_tasks_ibfk_1", "collect_tasks", type_="foreignkey")

    # 2. Drop all indexes on recharge_addresses
    op.drop_index("ix_recharge_addresses_chain_id", table_name="recharge_addresses")
    op.drop_index("ix_recharge_addresses_status", table_name="recharge_addresses")
    op.drop_index("ix_recharge_addresses_status_chain", table_name="recharge_addresses")
    op.drop_index("ix_recharge_addresses_token_id", table_name="recharge_addresses")
    op.drop_index("ix_recharge_addresses_user_chain_token", table_name="recharge_addresses")
    op.drop_index("ix_recharge_addresses_user_id", table_name="recharge_addresses")
    op.drop_index("ix_recharge_addresses_wallet_id", table_name="recharge_addresses")

    # 3. Drop all indexes on recharge_orders
    op.drop_index("ix_recharge_orders_chain_id", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_created_at", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_expires_at", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_order_no", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_recharge_address_id", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_status", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_status_expires", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_token_id", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_tx_hash", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_user_id", table_name="recharge_orders")
    op.drop_index("ix_recharge_orders_user_status", table_name="recharge_orders")

    # 4. Drop index on collect_tasks
    op.drop_index("ix_collect_tasks_recharge_address_id", table_name="collect_tasks")

    # 5. Rename tables back
    op.rename_table("recharge_addresses", "deposit_addresses")
    op.rename_table("recharge_orders", "deposit_orders")

    # 6. Rename columns back
    op.alter_column(
        "deposit_addresses",
        "total_recharged",
        new_column_name="total_deposited",
        existing_type=sa.DECIMAL(precision=32, scale=8),
        existing_nullable=False,
    )
    op.alter_column(
        "deposit_addresses",
        "last_recharge_at",
        new_column_name="last_deposit_at",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
    op.alter_column(
        "deposit_orders",
        "recharge_address_id",
        new_column_name="deposit_address_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "collect_tasks",
        "recharge_address_id",
        new_column_name="deposit_address_id",
        existing_type=sa.Integer(),
        existing_nullable=False,
    )

    # 7. Create indexes on deposit_addresses
    op.create_index("ix_deposit_addresses_chain_id", "deposit_addresses", ["chain_id"])
    op.create_index("ix_deposit_addresses_status", "deposit_addresses", ["status"])
    op.create_index(
        "ix_deposit_addresses_status_chain", "deposit_addresses", ["status", "chain_id"]
    )
    op.create_index("ix_deposit_addresses_token_id", "deposit_addresses", ["token_id"])
    op.create_index(
        "ix_deposit_addresses_user_chain_token",
        "deposit_addresses",
        ["user_id", "chain_id", "token_id"],
    )
    op.create_index("ix_deposit_addresses_user_id", "deposit_addresses", ["user_id"])
    op.create_index(
        "ix_deposit_addresses_wallet_id", "deposit_addresses", ["wallet_id"], unique=True
    )

    # 8. Create indexes on deposit_orders
    op.create_index("ix_deposit_orders_chain_id", "deposit_orders", ["chain_id"])
    op.create_index("ix_deposit_orders_created_at", "deposit_orders", ["created_at"])
    op.create_index(
        "ix_deposit_orders_deposit_address_id", "deposit_orders", ["deposit_address_id"]
    )
    op.create_index("ix_deposit_orders_expires_at", "deposit_orders", ["expires_at"])
    op.create_index("ix_deposit_orders_order_no", "deposit_orders", ["order_no"], unique=True)
    op.create_index("ix_deposit_orders_status", "deposit_orders", ["status"])
    op.create_index("ix_deposit_orders_status_expires", "deposit_orders", ["status", "expires_at"])
    op.create_index("ix_deposit_orders_token_id", "deposit_orders", ["token_id"])
    op.create_index("ix_deposit_orders_tx_hash", "deposit_orders", ["tx_hash"])
    op.create_index("ix_deposit_orders_user_id", "deposit_orders", ["user_id"])
    op.create_index("ix_deposit_orders_user_status", "deposit_orders", ["user_id", "status"])

    # 9. Create index on collect_tasks
    op.create_index("ix_collect_tasks_deposit_address_id", "collect_tasks", ["deposit_address_id"])

    # 10. Recreate ALL foreign key constraints
    # deposit_addresses FKs
    op.create_foreign_key(
        "deposit_addresses_ibfk_1", "deposit_addresses", "wallets", ["wallet_id"], ["id"]
    )
    op.create_foreign_key(
        "deposit_addresses_ibfk_2", "deposit_addresses", "chains", ["chain_id"], ["id"]
    )
    op.create_foreign_key(
        "deposit_addresses_ibfk_3", "deposit_addresses", "tokens", ["token_id"], ["id"]
    )
    op.create_foreign_key(
        "deposit_addresses_ibfk_4", "deposit_addresses", "users", ["user_id"], ["id"]
    )

    # deposit_orders FKs
    op.create_foreign_key("deposit_orders_ibfk_1", "deposit_orders", "users", ["user_id"], ["id"])
    op.create_foreign_key(
        "deposit_orders_ibfk_2",
        "deposit_orders",
        "deposit_addresses",
        ["deposit_address_id"],
        ["id"],
    )
    op.create_foreign_key("deposit_orders_ibfk_3", "deposit_orders", "chains", ["chain_id"], ["id"])
    op.create_foreign_key("deposit_orders_ibfk_4", "deposit_orders", "tokens", ["token_id"], ["id"])

    # collect_tasks FK
    op.create_foreign_key(
        "collect_tasks_ibfk_1", "collect_tasks", "deposit_addresses", ["deposit_address_id"], ["id"]
    )
