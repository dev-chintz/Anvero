"""Add user roles and per-area permissions

Revision ID: c2a6f9e3b184
Revises: b4e6f9c2a831
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2a6f9e3b184"
down_revision: str | Sequence[str] | None = "b4e6f9c2a831"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=10), server_default="user", nullable=False),
    )
    # every account that already exists had full access before roles existed;
    # only an account created after this migration starts out as "user"
    op.execute("UPDATE users SET role = 'admin'")

    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("area", sa.String(length=20), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "area", name="uq_user_permissions_user_area"),
    )
    op.create_index("ix_user_permissions_user_id", "user_permissions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_permissions_user_id", table_name="user_permissions")
    op.drop_table("user_permissions")
    op.drop_column("users", "role")
