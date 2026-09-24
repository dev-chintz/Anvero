"""Add integration_credentials.token_issued_at

Revision ID: a3e7c5b9d142
Revises: f5c3b8e1d726
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3e7c5b9d142"
down_revision: str | Sequence[str] | None = "f5c3b8e1d726"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("integration_credentials") as batch_op:
        batch_op.add_column(
            sa.Column("token_issued_at", sa.DateTime(timezone=True), nullable=True)
        )
    # The last change to a row holding a token is the best estimate there is:
    # every import rotates the token and touches the row. It can only be later
    # than the real moment (noting an import's outcome touches it too), so the
    # expiry shown for these rows may be a little optimistic until the next
    # rotation sets the real value.
    op.execute(
        "UPDATE integration_credentials SET token_issued_at = updated_at"
        " WHERE refresh_token <> ''"
    )


def downgrade() -> None:
    with op.batch_alter_table("integration_credentials") as batch_op:
        batch_op.drop_column("token_issued_at")
