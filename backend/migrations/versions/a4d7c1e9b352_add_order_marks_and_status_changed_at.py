"""Add starred, flagged and status_changed_at to orders

Revision ID: a4d7c1e9b352
Revises: e9b4c2a7d5f1
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d7c1e9b352"
down_revision: str | Sequence[str] | None = "e9b4c2a7d5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # the marks start off for every existing order; the server default keeps the
    # column required without a value being given
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column("starred", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("flagged", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("status_changed_at", sa.DateTime(timezone=True)))

    # what is known of when each status began: the latest recorded change. An
    # order with none has never changed status, so it stays null.
    op.execute(
        """
        UPDATE orders
        SET status_changed_at = (
            SELECT MAX(changed_at)
            FROM order_status_history
            WHERE order_status_history.order_id = orders.id
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("status_changed_at")
        batch_op.drop_column("flagged")
        batch_op.drop_column("starred")
