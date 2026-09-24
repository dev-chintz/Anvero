"""Add deleted_at and deleted_by_user_id to orders

Revision ID: b8e3d5a7c246
Revises: 8b41d6e0a9c3
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e3d5a7c246"
down_revision: str | Sequence[str] | None = "8b41d6e0a9c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "fk_orders_deleted_by_user_id_users"


def upgrade() -> None:
    # nullable: an order is in use until someone deletes it, and the record of
    # who did must outlive their account
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            FK_NAME, "users", ["deleted_by_user_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.drop_column("deleted_by_user_id")
        batch_op.drop_column("deleted_at")
