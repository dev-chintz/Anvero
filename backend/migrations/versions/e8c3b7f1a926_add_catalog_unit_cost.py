"""Add what making a piece costs to the assortment's offers

docs/CATALOG.md, "What it earns": the owner enters the cost of making one piece of an offer, and the
assortment's margin is what the marketplaces leave of the sales less that cost. The columns are the
owner's own: a sync never writes them.

Revision ID: e8c3b7f1a926
Revises: d5f2a8c1e947
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8c3b7f1a926"
down_revision: str | Sequence[str] | None = "d5f2a8c1e947"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode, so the foreign key can be added on SQLite as well
    with op.batch_alter_table("catalog_items") as batch:
        batch.add_column(sa.Column("unit_cost", sa.Numeric(precision=12, scale=2), nullable=True))
        batch.add_column(sa.Column("cost_updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("cost_updated_by_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_catalog_items_cost_updated_by_user_id_users",
            "users",
            ["cost_updated_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("catalog_items") as batch:
        batch.drop_constraint("fk_catalog_items_cost_updated_by_user_id_users", type_="foreignkey")
        batch.drop_column("cost_updated_by_user_id")
        batch.drop_column("cost_updated_at")
        batch.drop_column("unit_cost")
