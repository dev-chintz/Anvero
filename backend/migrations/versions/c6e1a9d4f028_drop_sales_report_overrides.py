"""Drop sales_report_overrides

Stage 8 of docs/NON_INVOICED_SALES.md: the report ported on 2026-09-27 is replaced by the
non-invoiced sales record, whose decisions live on its ledger rows (non_invoiced_ledger.override_*).
The table held no rows when it was dropped (read on the shared database, 2026-10-01).

Revision ID: c6e1a9d4f028
Revises: b4d2f8a61c37
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6e1a9d4f028"
down_revision: str | Sequence[str] | None = "b4d2f8a61c37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("sales_report_overrides")


def downgrade() -> None:
    op.create_table(
        "sales_report_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("order_external_id", sa.String(length=255), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source", "order_external_id", name="uq_sales_report_overrides_source_external_id"),
    )
