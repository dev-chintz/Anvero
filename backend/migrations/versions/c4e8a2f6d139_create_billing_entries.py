"""Create billing_entries, and where reading them resumes

Revision ID: c4e8a2f6d139
Revises: b3d7f1a5c928
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8a2f6d139"
down_revision: str | Sequence[str] | None = "b3d7f1a5c928"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type_id", sa.String(length=32), nullable=False),
        sa.Column("type_name", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("order_external_id", sa.String(length=255), nullable=True),
        sa.Column("offer_id", sa.String(length=255), nullable=True),
        sa.Column("offer_name", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_billing_entries_source_external_id"),
    )
    op.create_index(
        op.f("ix_billing_entries_order_external_id"),
        "billing_entries",
        ["order_external_id"],
        unique=False,
    )
    op.add_column(
        "integration_credentials",
        sa.Column("last_billing_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("integration_credentials", "last_billing_synced_at")
    op.drop_index(op.f("ix_billing_entries_order_external_id"), table_name="billing_entries")
    op.drop_table("billing_entries")
