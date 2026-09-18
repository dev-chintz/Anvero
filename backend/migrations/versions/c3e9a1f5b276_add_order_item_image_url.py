"""Add image_url to order_items: the offer's picture, fetched from Allegro

Revision ID: c3e9a1f5b276
Revises: a7f3c9e2b418
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e9a1f5b276"
down_revision: str | Sequence[str] | None = "a7f3c9e2b418"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("image_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("order_items", "image_url")
