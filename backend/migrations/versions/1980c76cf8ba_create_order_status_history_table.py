"""Create order status history table

Revision ID: 1980c76cf8ba
Revises: c1a2b7768c65
Create Date: 2026-09-16 15:13:56.216228

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1980c76cf8ba"
down_revision: str | Sequence[str] | None = "c1a2b7768c65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_VALUES = ("NEW", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED")


def _status_type() -> sa.types.TypeEngine:
    """Reference the existing order_status type rather than redefining it.

    On PostgreSQL an Enum is a real database type, and order_status was
    already created by the orders table migration. Autogenerate emits a plain
    sa.Enum here, which would attempt CREATE TYPE a second time and fail.
    """
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(*STATUS_VALUES, name="order_status", create_type=False)
    return sa.Enum(*STATUS_VALUES, name="order_status")


def upgrade() -> None:
    status_type = _status_type()
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", status_type, nullable=False),
        sa.Column("to_status", status_type, nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_status_history_order_id"),
        "order_status_history",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_order_status_history_order_id"), table_name="order_status_history"
    )
    op.drop_table("order_status_history")
    # order_status is deliberately left in place: the orders table still uses it
