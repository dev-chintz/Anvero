"""Create inpost_shipments: parcel locker shipments made through InPost's API

Revision ID: e9b4c2a7d5f1
Revises: c5f1a8d3e7b9
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9b4c2a7d5f1"
down_revision: str | Sequence[str] | None = "c5f1a8d3e7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inpost_shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("inpost_id", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tracking_number", sa.String(length=64), nullable=True),
        sa.Column("target_point", sa.String(length=32), nullable=False),
        sa.Column("template", sa.String(length=16), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inpost_id", name="uq_inpost_shipments_inpost_id"),
    )
    op.create_index("ix_inpost_shipments_order_id", "inpost_shipments", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_inpost_shipments_order_id", table_name="inpost_shipments")
    op.drop_table("inpost_shipments")
