"""Add courier_pickups and shipping_labels.pickup_id

Revision ID: d2f7b3e9a614
Revises: c9e4a2d7f581
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2f7b3e9a614"
down_revision: str | Sequence[str] | None = "c9e4a2d7f581"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courier_pickups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("command_id", sa.String(length=64), nullable=False),
        sa.Column("pickup_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ORDERED", "FAILED", name="pickupstatus", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("carrier_id", sa.String(length=64), nullable=True),
        sa.Column("ready_date", sa.Date(), nullable=False),
        sa.Column("proposal_id", sa.String(length=255), nullable=False),
        sa.Column("proposal_label", sa.String(length=255), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id"),
    )
    with op.batch_alter_table("shipping_labels") as batch_op:
        batch_op.add_column(sa.Column("pickup_id", sa.Uuid(), nullable=True))
        batch_op.create_index(batch_op.f("ix_shipping_labels_pickup_id"), ["pickup_id"])
        batch_op.create_foreign_key(
            "fk_shipping_labels_pickup_id_courier_pickups",
            "courier_pickups",
            ["pickup_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("shipping_labels") as batch_op:
        batch_op.drop_constraint("fk_shipping_labels_pickup_id_courier_pickups", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_shipping_labels_pickup_id"))
        batch_op.drop_column("pickup_id")
    op.drop_table("courier_pickups")
