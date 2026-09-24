"""Create app_settings (safe mode) and marketplace_writes (what was, or would be, sent)

Revision ID: e2a9c7f4b813
Revises: d8f2b6a4c917
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a9c7f4b813"
down_revision: str | Sequence[str] | None = "d8f2b6a4c917"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    # no row means safe mode is on, so a fresh or migrated database sends
    # nothing until an operator decides otherwise

    op.create_table(
        "marketplace_writes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum("DRY_RUN", "SENT", "FAILED", name="writeoutcome", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_marketplace_writes_created_at"), "marketplace_writes", ["created_at"]
    )
    op.create_index(op.f("ix_marketplace_writes_order_id"), "marketplace_writes", ["order_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_marketplace_writes_order_id"), table_name="marketplace_writes")
    op.drop_index(op.f("ix_marketplace_writes_created_at"), table_name="marketplace_writes")
    op.drop_table("marketplace_writes")
    op.drop_table("app_settings")
