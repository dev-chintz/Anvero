"""Add marketplace_cancelled_at to orders

Revision ID: 7a3d9e4b1c62
Revises: 5e8c2a1f7b90
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a3d9e4b1c62"
down_revision: str | Sequence[str] | None = "5e8c2a1f7b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode because SQLite cannot drop a column in downgrade otherwise;
    # on PostgreSQL it passes straight through to ALTER TABLE
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column(
                "marketplace_cancelled_at", sa.DateTime(timezone=True), nullable=True
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("marketplace_cancelled_at")
