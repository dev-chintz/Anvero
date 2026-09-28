"""Add delivery_smart to orders

Revision ID: b3e8d1f4a627
Revises: a7d4e2c9f136
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e8d1f4a627"
down_revision: str | Sequence[str] | None = "a7d4e2c9f136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("delivery_smart", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_smart")
