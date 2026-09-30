"""Add what traces an order's money: payment id, surcharges and cash, item tax, payment operations

For the non-invoiced sales record (docs/NON_INVOICED_SALES.md): the payment's own id and the
delivery method's, whether the invoice names a company and its VAT status, the tax each item's
offer declares, the order's surcharges and cash collected on delivery (order_payments), and the
operations on the seller's wallets at the payment operators (payment_operations).

Revision ID: c7e2a9f4d318
Revises: a9c4e7d2b815
Create Date: 2026-09-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e2a9f4d318"
down_revision: str | Sequence[str] | None = "a9c4e7d2b815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_method_id", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("payment_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_orders_payment_id"), "orders", ["payment_id"], unique=False)
    op.add_column("orders", sa.Column("invoice_is_company", sa.Boolean(), nullable=True))
    op.add_column("orders", sa.Column("invoice_vat_payer_status", sa.String(length=16), nullable=True))

    op.add_column("order_items", sa.Column("tax_rate", sa.String(length=16), nullable=True))
    op.add_column("order_items", sa.Column("tax_subject", sa.String(length=64), nullable=True))
    op.add_column("order_items", sa.Column("tax_exemption", sa.String(length=64), nullable=True))

    op.create_table(
        "order_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("SURCHARGE", "CASH_ON_DELIVERY", name="orderpaymentkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column(
            "payment_type",
            sa.Enum(
                "ONLINE", "BANK_TRANSFER", "CASH_ON_DELIVERY", "DEFERRED", "OTHER",
                name="paymenttype", native_enum=False, length=32,
            ),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("paid_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_payments_order_id"), "order_payments", ["order_id"], unique=False)

    op.create_table(
        "payment_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=48), nullable=False),
        sa.Column("group", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("wallet_operator", sa.String(length=16), nullable=True),
        sa.Column("wallet_type", sa.String(length=16), nullable=True),
        sa.Column("wallet_balance", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("payment_id", sa.String(length=64), nullable=True),
        sa.Column("payout_id", sa.String(length=64), nullable=True),
        sa.Column("surcharge_id", sa.String(length=64), nullable=True),
        sa.Column("marketplace_id", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "fingerprint", name="uq_payment_operations_source_fingerprint"),
    )
    op.create_index(op.f("ix_payment_operations_occurred_at"), "payment_operations", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_payment_operations_payment_id"), "payment_operations", ["payment_id"], unique=False)
    op.create_index(op.f("ix_payment_operations_payout_id"), "payment_operations", ["payout_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_operations_payout_id"), table_name="payment_operations")
    op.drop_index(op.f("ix_payment_operations_payment_id"), table_name="payment_operations")
    op.drop_index(op.f("ix_payment_operations_occurred_at"), table_name="payment_operations")
    op.drop_table("payment_operations")
    op.drop_index(op.f("ix_order_payments_order_id"), table_name="order_payments")
    op.drop_table("order_payments")
    op.drop_column("order_items", "tax_exemption")
    op.drop_column("order_items", "tax_subject")
    op.drop_column("order_items", "tax_rate")
    op.drop_column("orders", "invoice_vat_payer_status")
    op.drop_column("orders", "invoice_is_company")
    op.drop_index(op.f("ix_orders_payment_id"), table_name="orders")
    op.drop_column("orders", "payment_id")
    op.drop_column("orders", "delivery_method_id")
