"""Add shipping_labels.printed_at

Revision ID: c9e4a2d7f581
Revises: b6d2f8a1c357
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e4a2d7f581"
down_revision: str | Sequence[str] | None = "b6d2f8a1c357"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("shipping_labels") as batch_op:
        batch_op.add_column(sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("shipping_labels") as batch_op:
        batch_op.drop_column("printed_at")
