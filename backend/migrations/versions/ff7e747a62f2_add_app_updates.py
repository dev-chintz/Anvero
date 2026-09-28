"""Add app_updates: the history of the version the backend runs

Revision ID: ff7e747a62f2
Revises: b3e8d1f4a627
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ff7e747a62f2"
down_revision: str | Sequence[str] | None = "b3e8d1f4a627"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("from_commit", sa.String(length=40), nullable=True),
        sa.Column("to_commit", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("via", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=4000), nullable=True),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_app_updates_started_at"), "app_updates", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_updates_started_at"), table_name="app_updates")
    op.drop_table("app_updates")
