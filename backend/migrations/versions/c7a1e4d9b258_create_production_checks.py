"""Create production_checks (what on the to-make list has been made)

Revision ID: c7a1e4d9b258
Revises: b6e2f9a1c473
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7a1e4d9b258"
down_revision: str | Sequence[str] | None = "b6e2f9a1c473"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "production_checks",
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("checked_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["checked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_production_checks_checked_at", "production_checks", ["checked_at"])


def downgrade() -> None:
    op.drop_index("ix_production_checks_checked_at", table_name="production_checks")
    op.drop_table("production_checks")
