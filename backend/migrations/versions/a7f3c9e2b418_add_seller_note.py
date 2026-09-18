"""Add seller_note: the seller's own note on the order

Revision ID: a7f3c9e2b418
Revises: f3b8d1e6a204
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f3c9e2b418"
down_revision: str | Sequence[str] | None = "f3b8d1e6a204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("seller_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "seller_note")
