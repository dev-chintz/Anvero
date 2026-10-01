"""The assortment: the offers in the seller's Allegro account, their pictures, and the same
products on Erli (docs/CATALOG.md)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.order import OrderSource

SOURCE = Enum(OrderSource, native_enum=False, length=32)

# how an Erli product was tied to an Allegro offer, in the order the sync tries them
MATCH_EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
MATCH_EXTERNAL_ID = "EXTERNAL_ID"
MATCH_SKU = "SKU"

# whether an Erli product is in the same category as its Allegro offer
CATEGORY_SAME = "SAME"
CATEGORY_DIFFERENT = "DIFFERENT"
CATEGORY_UNKNOWN = "UNKNOWN"


class CatalogItem(Base):
    """One offer of the seller's Allegro account: a product of the assortment.

    Allegro is where the assortment lives (Erli's offers are copies of it), so one row is one
    Allegro offer. The row is read from Allegro by every sync and never edited in Anvero.
    """

    __tablename__ = "catalog_items"
    __table_args__ = (UniqueConstraint("source", "offer_id", name="uq_catalog_items_source_offer_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[OrderSource] = mapped_column(SOURCE, nullable=False)
    # the marketplace's id of the offer, as order_items.offer_id holds it
    offer_id: Mapped[str] = mapped_column(String(255), nullable=False)

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    # the seller's own code: Allegro's external id of the offer
    sku: Mapped[str | None] = mapped_column(String(255), index=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    stock: Mapped[int | None] = mapped_column(Integer)
    # Allegro's publication status: ACTIVE, INACTIVE, ACTIVATING (ENDED offers are not read)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    # the leaf category, and the way to it from the top of the tree: a list of
    # {"id": ..., "name": ...}, the leaf last. `category_ids` is the same ids as `|1|23|456|`, so
    # "everything under 23" is one LIKE, on any database.
    category_id: Mapped[str | None] = mapped_column(String(64))
    category_path: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    category_ids: Mapped[str] = mapped_column(String(512), nullable=False, default="", index=True)

    # when a sync last found the offer on Allegro, and when one first found it gone (ended or
    # deleted there); a gone offer is kept, with its pictures, but is not part of the assortment
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    images: Mapped[list["CatalogImage"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="CatalogImage.position"
    )
    listings: Mapped[list["CatalogListing"]] = relationship(back_populates="item", cascade="all, delete-orphan")


class CatalogImage(Base):
    """One picture of an offer: its address on Allegro, and the copy kept on this server.

    The address is always kept, so the picture can be shown (or fetched again) from Allegro; the
    copy (`file_name`) is empty until it has been downloaded.
    """

    __tablename__ = "catalog_images"
    __table_args__ = (UniqueConstraint("item_id", "position", name="uq_catalog_images_item_position"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # the offer's own order of pictures; the first is the cover
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # `<sha256 of the bytes>.<jpg|png|webp|gif>`, the file under the pictures folder; the same
    # picture used by two offers is one file
    file_name: Mapped[str | None] = mapped_column(String(80))
    content_type: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # why the last download failed; cleared by the next that succeeds
    fetch_error: Mapped[str | None] = mapped_column(String(255))

    item: Mapped[CatalogItem] = relationship(back_populates="images")


class CatalogListing(Base):
    """The same product on another marketplace (Erli), tied to the Allegro offer it copies."""

    __tablename__ = "catalog_listings"
    __table_args__ = (UniqueConstraint("item_id", "source", name="uq_catalog_listings_item_source"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[OrderSource] = mapped_column(SOURCE, nullable=False)
    # the marketplace's id of its product, as order_items.offer_id holds it for that marketplace
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    matched_by: Mapped[str] = mapped_column(String(24), nullable=False)

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    stock: Mapped[int | None] = mapped_column(Integer)
    # `ACTIVE`, `INACTIVE` or `ARCHIVED`
    status: Mapped[str | None] = mapped_column(String(32))

    # that marketplace's own category, as {"id", "name"} entries from the top, the leaf last
    category_path: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    # SAME, DIFFERENT or UNKNOWN, against the Allegro offer's category
    category_match: Mapped[str] = mapped_column(String(12), nullable=False)

    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    item: Mapped[CatalogItem] = relationship(back_populates="listings")
