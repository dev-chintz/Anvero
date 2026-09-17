"""Create integration credentials table

Revision ID: 5e8c2a1f7b90
Revises: 2b4f91d7a3c8
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import func

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e8c2a1f7b90"
down_revision: str | Sequence[str] | None = "2b4f91d7a3c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_credentials",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("seed_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("integration_credentials")
