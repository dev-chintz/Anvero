"""Add anonymized_at to orders, message threads, after-sales cases and marketplace writes

Revision ID: a7d4e2c9f136
Revises: c2a6f9e3b184
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d4e2c9f136"
down_revision: str | Sequence[str] | None = "c2a6f9e3b184"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("orders", "message_threads", "after_sales_cases", "marketplace_writes")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "anonymized_at")
