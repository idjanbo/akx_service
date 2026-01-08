"""add_username_field_to_users

Revision ID: a1b2c3d4e5f6
Revises: 093cc7a50c77
Create Date: 2026-01-08

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "093cc7a50c77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "username")
