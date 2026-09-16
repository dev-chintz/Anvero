"""Unique order per source

Revision ID: 2b4f91d7a3c8
Revises: 1980c76cf8ba
Create Date: 2026-09-16

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b4f91d7a3c8"
down_revision: str | Sequence[str] | None = "1980c76cf8ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "uq_orders_source_external_id"


def upgrade() -> None:
    # SQLite cannot ALTER TABLE ADD CONSTRAINT; batch mode recreates the table
    # instead, and passes straight through to a normal ALTER on PostgreSQL
    with op.batch_alter_table("orders") as batch_op:
        batch_op.create_unique_constraint(
            CONSTRAINT_NAME, ["source", "external_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
