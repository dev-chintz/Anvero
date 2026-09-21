"""Create order_shipments: the parcels sent for an order

Revision ID: b3d7f1a5c928
Revises: a1c5e9d3b742
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d7f1a5c928"
down_revision: str | Sequence[str] | None = "a1c5e9d3b742"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_shipments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("carrier_id", sa.String(length=64), nullable=True),
        sa.Column("carrier_name", sa.String(length=255), nullable=True),
        sa.Column("waybill", sa.String(length=255), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tracking_status", sa.String(length=32), nullable=True),
        sa.Column("tracking_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_shipments_order_id"), "order_shipments", ["order_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_order_shipments_order_id"), table_name="order_shipments")
    op.drop_table("order_shipments")
