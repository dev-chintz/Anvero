"""Add changed_by_user_id to order status history

Revision ID: b2d6f4a9c7e1
Revises: 9c4e7f2a8b13
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d6f4a9c7e1"
down_revision: str | Sequence[str] | None = "9c4e7f2a8b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "fk_order_status_history_changed_by_user_id_users"


def upgrade() -> None:
    # nullable: entries recorded before logins existed have no author, and the
    # history must survive the deletion of the user who made a change
    with op.batch_alter_table("order_status_history") as batch_op:
        batch_op.add_column(
            sa.Column("changed_by_user_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            FK_NAME, "users", ["changed_by_user_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("order_status_history") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.drop_column("changed_by_user_id")
