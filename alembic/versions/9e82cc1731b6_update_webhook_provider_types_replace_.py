"""update_webhook_provider_types_replace_trongrid_with_tatum_getblock

Revision ID: 9e82cc1731b6
Revises: 91d57fcc08ce
Create Date: 2026-01-05 19:31:23.219772

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e82cc1731b6"
down_revision: str | Sequence[str] | None = "91d57fcc08ce"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Old enum: trongrid, alchemy, helius, quicknode, moralis, custom
# New enum: tatum, alchemy, helius, quicknode, moralis, getblock, custom


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Change column to VARCHAR temporarily
    op.execute("ALTER TABLE webhook_providers MODIFY COLUMN provider_type VARCHAR(20)")

    # Step 2: Update existing trongrid records to tatum (if any)
    op.execute(
        "UPDATE webhook_providers SET provider_type = 'tatum' WHERE provider_type = 'trongrid'"
    )

    # Step 3: Change column back to ENUM with new values
    op.execute(
        "ALTER TABLE webhook_providers MODIFY COLUMN provider_type "
        "ENUM('tatum', 'alchemy', 'helius', 'quicknode', 'moralis', 'getblock', 'custom') NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Step 1: Change column to VARCHAR temporarily
    op.execute("ALTER TABLE webhook_providers MODIFY COLUMN provider_type VARCHAR(20)")

    # Step 2: Update tatum records back to trongrid
    op.execute(
        "UPDATE webhook_providers SET provider_type = 'trongrid' WHERE provider_type = 'tatum'"
    )

    # Step 3: Remove getblock records (or convert to custom)
    op.execute(
        "UPDATE webhook_providers SET provider_type = 'custom' WHERE provider_type = 'getblock'"
    )

    # Step 4: Change column back to ENUM with old values
    op.execute(
        "ALTER TABLE webhook_providers MODIFY COLUMN provider_type "
        "ENUM('trongrid', 'alchemy', 'helius', 'quicknode', 'moralis', 'custom') NOT NULL"
    )
