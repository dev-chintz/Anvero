"""Add integration_settings and integration_credentials.account_login

Revision ID: e6c1d9a4f725
Revises: d5b8e2f7a391
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c1d9a4f725"
down_revision: str | Sequence[str] | None = "d5b8e2f7a391"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_settings",
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider"),
    )
    op.add_column(
        "integration_credentials",
        sa.Column("account_login", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("integration_credentials", "account_login")
    op.drop_table("integration_settings")
