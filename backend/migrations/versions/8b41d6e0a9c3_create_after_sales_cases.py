"""Create after_sales_cases (returns, claims and disputes, plan B4)

Revision ID: 8b41d6e0a9c3
Revises: 643b765a4578
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b41d6e0a9c3"
down_revision: str | Sequence[str] | None = "643b765a4578"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "after_sales_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("RETURN", "CLAIM", "DISPUTE", name="casekind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("is_open", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "NONE",
                "DECIDE",
                "REPLY",
                "RECOVER_COMMISSION",
                name="caseaction",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_number", sa.String(length=64), nullable=True),
        sa.Column("order_external_id", sa.String(length=255), nullable=True),
        sa.Column("buyer_login", sa.String(length=255), nullable=True),
        sa.Column("buyer_email", sa.String(length=255), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source", "external_id", name="uq_after_sales_cases_source_external_id"
        ),
    )
    op.create_index(op.f("ix_after_sales_cases_action"), "after_sales_cases", ["action"])
    op.create_index(op.f("ix_after_sales_cases_due_at"), "after_sales_cases", ["due_at"])
    op.create_index(
        op.f("ix_after_sales_cases_order_external_id"), "after_sales_cases", ["order_external_id"]
    )
    op.create_index(op.f("ix_after_sales_cases_opened_at"), "after_sales_cases", ["opened_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_after_sales_cases_opened_at"), table_name="after_sales_cases")
    op.drop_index(op.f("ix_after_sales_cases_order_external_id"), table_name="after_sales_cases")
    op.drop_index(op.f("ix_after_sales_cases_due_at"), table_name="after_sales_cases")
    op.drop_index(op.f("ix_after_sales_cases_action"), table_name="after_sales_cases")
    op.drop_table("after_sales_cases")
