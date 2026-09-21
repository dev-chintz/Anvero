"""Add the outcome of the last import to integration_credentials

Revision ID: a1c5e9d3b742
Revises: f7a2c4e8b613
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c5e9d3b742"
down_revision: str | Sequence[str] | None = "f7a2c4e8b613"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integration_credentials",
        sa.Column("last_import_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_credentials", sa.Column("last_import_created", sa.Integer(), nullable=True)
    )
    op.add_column(
        "integration_credentials", sa.Column("last_import_updated", sa.Integer(), nullable=True)
    )
    op.add_column(
        "integration_credentials", sa.Column("last_import_error", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("integration_credentials", "last_import_error")
    op.drop_column("integration_credentials", "last_import_updated")
    op.drop_column("integration_credentials", "last_import_created")
    op.drop_column("integration_credentials", "last_import_at")
