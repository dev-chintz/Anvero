"""Add the non-invoiced sales ledger and the product flag for excluded goods

Stage 3 of docs/NON_INVOICED_SALES.md: product_settings (an offer flagged as goods that can never
use the poz. 41 exemption, § 4 of the regulation) and non_invoiced_ledger (one row per money event:
a sale, or a correction of one).

Revision ID: e3b7a1c9d524
Revises: c7e2a9f4d318
Create Date: 2026-09-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3b7a1c9d524"
down_revision: str | Sequence[str] | None = "c7e2a9f4d318"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _source() -> sa.Enum:
    return sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32)


def upgrade() -> None:
    op.create_table(
        "product_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", _source(), nullable=False),
        sa.Column("offer_id", sa.String(length=255), nullable=False),
        sa.Column("excluded_from_exemption", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "offer_id", name="uq_product_settings_source_offer_id"),
    )

    op.create_table(
        "non_invoiced_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("SALE", "CORRECTION", name="ledgerkind", native_enum=False, length=16), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("source", _source(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("order_external_id", sa.String(length=255), nullable=False),
        sa.Column("order_number", sa.Integer(), nullable=False),
        sa.Column("corrects_entry_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("buyer_first_name", sa.String(length=255), nullable=True),
        sa.Column("buyer_last_name", sa.String(length=255), nullable=True),
        sa.Column("buyer_street", sa.String(length=255), nullable=True),
        sa.Column("buyer_postal_code", sa.String(length=32), nullable=True),
        sa.Column("buyer_city", sa.String(length=255), nullable=True),
        sa.Column("buyer_country_code", sa.String(length=8), nullable=True),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payment_type",
            sa.Enum(
                "ONLINE", "BANK_TRANSFER", "CASH_ON_DELIVERY", "DEFERRED", "OTHER",
                name="paymenttype", native_enum=False, length=32,
            ),
            nullable=True,
        ),
        sa.Column("payment_operator", sa.String(length=64), nullable=True),
        sa.Column("payment_id", sa.String(length=64), nullable=True),
        sa.Column("operation_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("payout_id", sa.String(length=64), nullable=True),
        sa.Column("payout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_link", sa.String(length=16), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=48), nullable=False),
        sa.Column("ruleset", sa.String(length=32), nullable=False),
        sa.Column("override_category", sa.String(length=32), nullable=True),
        sa.Column("override_note", sa.Text(), nullable=True),
        sa.Column("overridden_by_user_id", sa.Integer(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["corrects_entry_id"], ["non_invoiced_ledger.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["overridden_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "event_key", name="uq_non_invoiced_ledger_source_event_key"),
    )
    op.create_index(op.f("ix_non_invoiced_ledger_entry_date"), "non_invoiced_ledger", ["entry_date"], unique=False)
    op.create_index(op.f("ix_non_invoiced_ledger_order_id"), "non_invoiced_ledger", ["order_id"], unique=False)
    op.create_index(
        op.f("ix_non_invoiced_ledger_corrects_entry_id"), "non_invoiced_ledger", ["corrects_entry_id"], unique=False
    )
    op.create_index(op.f("ix_non_invoiced_ledger_payment_id"), "non_invoiced_ledger", ["payment_id"], unique=False)
    op.create_index(op.f("ix_non_invoiced_ledger_locked_at"), "non_invoiced_ledger", ["locked_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_non_invoiced_ledger_locked_at"), table_name="non_invoiced_ledger")
    op.drop_index(op.f("ix_non_invoiced_ledger_payment_id"), table_name="non_invoiced_ledger")
    op.drop_index(op.f("ix_non_invoiced_ledger_corrects_entry_id"), table_name="non_invoiced_ledger")
    op.drop_index(op.f("ix_non_invoiced_ledger_order_id"), table_name="non_invoiced_ledger")
    op.drop_index(op.f("ix_non_invoiced_ledger_entry_date"), table_name="non_invoiced_ledger")
    op.drop_table("non_invoiced_ledger")
    op.drop_table("product_settings")
