"""Add internal_note to orders

Revision ID: b6e2f9a1c473
Revises: a4d7c1e9b352
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6e2f9a1c473"
down_revision: str | Sequence[str] | None = "a4d7c1e9b352"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # nullable: an order has no note of the operator's own until one is written
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("internal_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("internal_note")
