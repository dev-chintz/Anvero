"""The assortment (docs/CATALOG.md): what an adapter reads from a marketplace, and what the API says."""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from app.schemas.types import UtcDateTime

# ---- what the adapters read -------------------------------------------------


@dataclass(frozen=True)
class OfferSnapshot:
    """One Allegro offer as the adapter reads it."""

    offer_id: str
    name: str
    status: str
    sku: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    stock: int | None = None
    category_id: str | None = None
    image_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class ErliProductSnapshot:
    """One Erli product as the adapter reads it."""

    external_id: str
    status: str | None = None
    sku: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    stock: int | None = None
    # the Allegro offers the product says it copies (Erli's `externalReferences`)
    allegro_offer_ids: tuple[str, ...] = ()
    # Erli's own category, and the one the product came with, each as {"id", "name"} from the top
    category_path: tuple[dict[str, str], ...] = ()
    source_category_path: tuple[dict[str, str], ...] = ()


@dataclass
class CatalogSyncResult:
    """How one sync went, for the button and the note the page shows."""

    items: int = 0
    added: int = 0
    gone: int = 0
    images_downloaded: int = 0
    images_failed: int = 0
    # pictures still without a copy on this server, for the next run
    images_pending: int = 0
    # Erli: products read, tied to an offer, and left over; None when Erli is not connected
    erli_products: int | None = None
    erli_matched: int = 0
    erli_unmatched: int = 0
    # why the Erli part was skipped, when it was; Allegro's part still stands
    erli_error: str | None = None
    # offers whose details (pictures) could not be read this time
    details_failed: int = 0
    notes: list[str] = field(default_factory=list)


# ---- what the API says ------------------------------------------------------


class CatalogFlag(str, Enum):
    """The quick filters of the page: what is missing from an offer."""

    NO_IMAGE = "no_image"
    NO_SKU = "no_sku"
    NOT_ON_ERLI = "not_on_erli"
    CATEGORY_DIFFERS = "category_differs"


class CatalogStatusFilter(str, Enum):
    # every offer Allegro still lists (the default)
    CURRENT = "current"
    ACTIVE = "active"
    INACTIVE = "inactive"
    GONE = "gone"


class CatalogSort(str, Enum):
    NAME = "name"
    PRICE = "price"
    STOCK = "stock"


class CategoryStep(BaseModel):
    id: str
    name: str


class CatalogImageRead(BaseModel):
    position: int
    # the address on Allegro, always present
    url: str
    # the copy on this server, null until downloaded
    local_url: str | None


class CatalogListingRead(BaseModel):
    source: str
    external_id: str
    matched_by: str
    price: Decimal | None
    currency: str | None
    stock: int | None
    status: str | None
    category_path: list[CategoryStep]
    category_match: str


class CatalogItemRead(BaseModel):
    id: uuid.UUID
    offer_id: str
    name: str
    sku: str | None
    price: Decimal | None
    currency: str | None
    stock: int | None
    status: str
    gone: bool
    category_path: list[CategoryStep]
    # where the offer is on Allegro
    allegro_url: str
    # the cover for the list: the local copy when there is one, else Allegro's address
    thumbnail_url: str | None
    images: list[CatalogImageRead]
    # the same product on Erli, when it was found there
    erli: CatalogListingRead | None


class CatalogItemList(BaseModel):
    items: list[CatalogItemRead]
    total: int


class CatalogCategoryNode(BaseModel):
    id: str
    name: str
    # offers in this category and everything under it
    count: int
    children: list["CatalogCategoryNode"]


class CatalogCategories(BaseModel):
    tree: list[CatalogCategoryNode]
    # offers Allegro gave no category for
    uncategorized: int


class CatalogSyncNote(BaseModel):
    """How the last sync ended, as kept for the page."""

    at: UtcDateTime
    error: str | None = None
    items: int | None = None
    erli_error: str | None = None
    # Erli products that matched no offer; null when Erli was not read
    erli_unmatched: int | None = None


class CatalogSummary(BaseModel):
    total: int
    active: int
    inactive: int
    gone: int
    no_image: int
    no_sku: int
    # offers with no Erli product found; only meaningful when Erli is connected
    not_on_erli: int
    category_differs: int
    images_total: int
    images_local: int
    # Erli products that matched no offer (read at the last sync)
    erli_unmatched: int | None
    erli_connected: bool
    last_sync: CatalogSyncNote | None


class CatalogSyncRead(BaseModel):
    items: int
    added: int
    gone: int
    images_downloaded: int
    images_failed: int
    images_pending: int
    erli_products: int | None
    erli_matched: int
    erli_unmatched: int
    erli_error: str | None
    details_failed: int
