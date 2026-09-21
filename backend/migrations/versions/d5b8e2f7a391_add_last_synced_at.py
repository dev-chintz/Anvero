"""Add last_synced_at to integration_credentials: where the next import resumes

Revision ID: d5b8e2f7a391
Revises: c3e9a1f5b276
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5b8e2f7a391"
down_revision: str | Sequence[str] | None = "c3e9a1f5b276"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integration_credentials",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("integration_credentials", "last_synced_at")
