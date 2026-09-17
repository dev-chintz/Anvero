"""Add marketplace_status to orders

Revision ID: f3b8d1e6a204
Revises: e4a7c2d9f5b1
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b8d1e6a204"
down_revision: str | Sequence[str] | None = "e4a7c2d9f5b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_VALUES = ("NEW", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED")


def _status_type() -> sa.types.TypeEngine:
    """Reference the existing order_status type rather than redefining it.

    On PostgreSQL an Enum is a real database type, created with the orders
    table; a plain sa.Enum here would attempt CREATE TYPE a second time.
    """
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(*STATUS_VALUES, name="order_status", create_type=False)
    return sa.Enum(*STATUS_VALUES, name="order_status")


def upgrade() -> None:
    # nullable: existing orders have never been compared with a marketplace,
    # and an order created by hand never will be
    with op.batch_alter_table("orders") as batch_op:
        batch_op.add_column(
            sa.Column("marketplace_status", _status_type(), nullable=True)
        )
        # the same status unmapped, since Anvero's five collapse distinctions
        # the marketplace's own panel shows
        batch_op.add_column(
            sa.Column("marketplace_status_label", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("marketplace_status_label")
        batch_op.drop_column("marketplace_status")
    # order_status stays: the status column still uses it
