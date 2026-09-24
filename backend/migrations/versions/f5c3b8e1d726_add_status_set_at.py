"""Add orders.status_set_at and order_shipments.added_in_anvero

Revision ID: f5c3b8e1d726
Revises: e2a9c7f4b813
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5c3b8e1d726"
down_revision: str | Sequence[str] | None = "e2a9c7f4b813"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("status_set_at", sa.DateTime(timezone=True), nullable=True))
    # Filled from the history: the latest change a person made. Orders nobody
    # has touched stay null, so an import is free to move them.
    op.execute(
        "UPDATE orders SET status_set_at = ("
        " SELECT MAX(h.changed_at) FROM order_status_history h"
        " WHERE h.order_id = orders.id AND h.changed_by_user_id IS NOT NULL)"
    )

    with op.batch_alter_table("order_shipments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "added_in_anvero", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("order_shipments") as batch_op:
        batch_op.drop_column("added_in_anvero")
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("status_set_at")
