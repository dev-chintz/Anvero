"""Add shipping_labels

Revision ID: b6d2f8a1c357
Revises: a3e7c5b9d142
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d2f8a1c357"
down_revision: str | Sequence[str] | None = "a3e7c5b9d142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shipping_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("shipment_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "CREATED", "FAILED", "CANCELLED",
                name="labelstatus", native_enum=False, length=16,
            ),
            nullable=False,
        ),
        sa.Column("delivery_method_id", sa.String(length=255), nullable=False),
        sa.Column("carrier_id", sa.String(length=64), nullable=True),
        sa.Column("waybill", sa.String(length=255), nullable=True),
        sa.Column("length_cm", sa.Numeric(8, 1), nullable=False),
        sa.Column("width_cm", sa.Numeric(8, 1), nullable=False),
        sa.Column("height_cm", sa.Numeric(8, 1), nullable=False),
        sa.Column("weight_kg", sa.Numeric(8, 3), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id"),
    )
    op.create_index(op.f("ix_shipping_labels_order_id"), "shipping_labels", ["order_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_shipping_labels_order_id"), table_name="shipping_labels")
    op.drop_table("shipping_labels")
