"""Add the reports of the non-invoiced sales record handed over to the accountant

Stage 4 of docs/NON_INVOICED_SALES.md (section 4c): a report handed over is kept with the ledger rows
it held, in the order it listed them, so that downloading it again gives the same file; the rows
themselves are locked (non_invoiced_ledger.locked_at).

Revision ID: b4d2f8a61c37
Revises: e3b7a1c9d524
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d2f8a61c37"
down_revision: str | Sequence[str] | None = "e3b7a1c9d524"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "non_invoiced_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("handed_over_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handed_over_by_user_id", sa.Integer(), nullable=True),
        sa.Column("ruleset", sa.String(length=32), nullable=False),
        sa.Column("total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["handed_over_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_non_invoiced_reports_date_from", "non_invoiced_reports", ["date_from"])

    op.create_table(
        "non_invoiced_report_rows",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["non_invoiced_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entry_id"], ["non_invoiced_ledger.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("report_id", "position"),
    )
    op.create_index("ix_non_invoiced_report_rows_entry_id", "non_invoiced_report_rows", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_non_invoiced_report_rows_entry_id", table_name="non_invoiced_report_rows")
    op.drop_table("non_invoiced_report_rows")
    op.drop_index("ix_non_invoiced_reports_date_from", table_name="non_invoiced_reports")
    op.drop_table("non_invoiced_reports")
