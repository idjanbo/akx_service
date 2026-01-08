"""add_support_user_fields_parent_id_permissions

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add parent_id column (foreign key to users.id for support users)
    op.add_column("users", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.create_index("ix_users_parent_id", "users", ["parent_id"], unique=False)
    op.create_foreign_key(
        "fk_users_parent_id", "users", "users", ["parent_id"], ["id"], ondelete="SET NULL"
    )

    # Add permissions column (JSON array for support user permissions)
    # MySQL doesn't allow default values for JSON columns, so:
    # 1. Add as nullable
    # 2. Update existing rows to empty array
    # 3. Set to NOT NULL
    op.add_column("users", sa.Column("permissions", sa.JSON(), nullable=True))
    op.execute("UPDATE users SET permissions = '[]' WHERE permissions IS NULL")
    op.alter_column("users", "permissions", nullable=False)


def downgrade() -> None:
    op.drop_column("users", "permissions")
    op.drop_constraint("fk_users_parent_id", "users", type_="foreignkey")
    op.drop_index("ix_users_parent_id", table_name="users")
    op.drop_column("users", "parent_id")
