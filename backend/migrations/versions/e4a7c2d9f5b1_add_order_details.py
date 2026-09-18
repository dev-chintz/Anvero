"""Add order details: buyer, delivery, payment, invoice, items and addresses

Revision ID: e4a7c2d9f5b1
Revises: b2d6f4a9c7e1
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a7c2d9f5b1"
down_revision: str | Sequence[str] | None = "b2d6f4a9c7e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORDER_COLUMNS = [
    ("customer_login", sa.String(255)),
    ("customer_first_name", sa.String(255)),
    ("customer_last_name", sa.String(255)),
    ("customer_company_name", sa.String(255)),
    ("customer_phone", sa.String(64)),
    ("buyer_message", sa.Text()),
    ("delivery_method", sa.String(255)),
    ("delivery_cost", sa.Numeric(12, 2)),
    ("pickup_point_id", sa.String(255)),
    ("pickup_point_name", sa.String(255)),
    # a plain string, not a database enum type; see models/order.py
    ("payment_type", sa.String(32)),
    ("payment_provider", sa.String(64)),
    ("paid_amount", sa.Numeric(12, 2)),
    ("paid_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    # every detail is nullable, so existing orders need no backfill; they
    # simply have no details, like an order entered by hand
    with op.batch_alter_table("orders") as batch_op:
        for name, type_ in ORDER_COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))
        batch_op.add_column(
            sa.Column(
                "invoice_required",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("offer_id", sa.String(255), nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "order_addresses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("postal_code", sa.String(32), nullable=True),
        sa.Column("city", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(8), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("tax_id", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id", "type", name="uq_order_addresses_order_id_type"
        ),
    )
    op.create_index("ix_order_addresses_order_id", "order_addresses", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_addresses_order_id", table_name="order_addresses")
    op.drop_table("order_addresses")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")

    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("invoice_required")
        for name, _ in reversed(ORDER_COLUMNS):
            batch_op.drop_column(name)
