"""Add the assortment: the Allegro offers, their pictures, and the same products on Erli

docs/CATALOG.md. `catalog_items` is one Allegro offer, `catalog_images` its pictures (the address on
Allegro and the copy kept on this server), `catalog_listings` the same product on Erli.

Revision ID: d5f2a8c1e947
Revises: c6e1a9d4f028
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f2a8c1e947"
down_revision: str | Sequence[str] | None = "c6e1a9d4f028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32), nullable=False),
        sa.Column("offer_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("sku", sa.String(length=255), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("category_id", sa.String(length=64), nullable=True),
        sa.Column("category_path", sa.JSON(), nullable=False),
        sa.Column("category_ids", sa.String(length=512), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "offer_id", name="uq_catalog_items_source_offer_id"),
    )
    op.create_index("ix_catalog_items_sku", "catalog_items", ["sku"])
    op.create_index("ix_catalog_items_category_ids", "catalog_items", ["category_ids"])
    op.create_index("ix_catalog_items_gone_at", "catalog_items", ["gone_at"])

    op.create_table(
        "catalog_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(length=80), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetch_error", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["catalog_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "position", name="uq_catalog_images_item_position"),
    )
    op.create_index("ix_catalog_images_item_id", "catalog_images", ["item_id"])

    op.create_table(
        "catalog_listings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Enum("ALLEGRO", "ERLI", name="ordersource", native_enum=False, length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("matched_by", sa.String(length=24), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("category_path", sa.JSON(), nullable=False),
        sa.Column("category_match", sa.String(length=12), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["catalog_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "source", name="uq_catalog_listings_item_source"),
    )
    op.create_index("ix_catalog_listings_item_id", "catalog_listings", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_catalog_listings_item_id", table_name="catalog_listings")
    op.drop_table("catalog_listings")
    op.drop_index("ix_catalog_images_item_id", table_name="catalog_images")
    op.drop_table("catalog_images")
    op.drop_index("ix_catalog_items_gone_at", table_name="catalog_items")
    op.drop_index("ix_catalog_items_category_ids", table_name="catalog_items")
    op.drop_index("ix_catalog_items_sku", table_name="catalog_items")
    op.drop_table("catalog_items")
