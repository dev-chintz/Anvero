"""Add ordered_at to orders

Revision ID: 9c4e7f2a8b13
Revises: 7a3d9e4b1c62
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import func

# revision identifiers, used by Alembic.
revision: str = "9c4e7f2a8b13"
down_revision: str | Sequence[str] | None = "7a3d9e4b1c62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # added nullable first, so existing rows can be given a value before the
    # column is made required
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True)
        )

    # every order so far was entered locally, so it was ordered when it was
    # created; imported orders get their marketplace purchase time from now on
    op.execute("UPDATE orders SET ordered_at = created_at")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.alter_column(
            "ordered_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=func.current_timestamp(),
        )
        batch_op.create_index("ix_orders_ordered_at", ["ordered_at"])


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_index("ix_orders_ordered_at")
        batch_op.drop_column("ordered_at")
