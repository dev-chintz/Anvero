"""Add users.token_version: a new password ends the sessions logged in before

Revision ID: a9c4e7d2b815
Revises: ff7e747a62f2
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e7d2b815"
down_revision: Union[str, Sequence[str], None] = "ff7e747a62f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
