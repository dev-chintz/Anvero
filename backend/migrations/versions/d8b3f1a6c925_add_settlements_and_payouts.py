"""Mark the billing entries that settle fees; create payouts

Revision ID: d8b3f1a6c925
Revises: c7a1e4d9b258
Create Date: 2026-09-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8b3f1a6c925"
down_revision: str | Sequence[str] | None = "c7a1e4d9b258"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "billing_entries",
        sa.Column("is_settlement", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    # the one settlement stored so far: Allegro's "Pobranie opłat z wpływów"
    op.execute("UPDATE billing_entries SET is_settlement = true WHERE source = 'ALLEGRO' AND type_id = 'PAD'")

    op.create_table(
        "payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("operator", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_payouts_source_external_id"),
    )
    op.create_index("ix_payouts_paid_at", "payouts", ["paid_at"])


def downgrade() -> None:
    op.drop_index("ix_payouts_paid_at", table_name="payouts")
    op.drop_table("payouts")
    op.drop_column("billing_entries", "is_settlement")
