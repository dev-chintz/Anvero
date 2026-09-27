"""Create order_item_packing

Revision ID: b4e6f9c2a831
Revises: a2f4c8e1b937
Create Date: 2026-09-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e6f9c2a831"
down_revision: str | Sequence[str] | None = "a2f4c8e1b937"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_item_packing",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("packed_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("order_id", "position", name="uq_order_item_packing_order_id_position"),
    )
    op.create_index("ix_order_item_packing_order_id", "order_item_packing", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_item_packing_order_id", table_name="order_item_packing")
    op.drop_table("order_item_packing")
