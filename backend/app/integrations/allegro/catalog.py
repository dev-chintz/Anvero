"""The seller's Allegro offers, read for the assortment (docs/CATALOG.md).

Kept apart from adapter.py like messaging and after-sales: offers are a resource of their own, read
on their own, not part of an order import. Built from Allegro's published specification
(`/sale/offers`, `/sale/product-offers/{id}`, `/sale/categories/{id}`); see INTEGRATIONS.md,
"Assortment".
"""

import logging
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.allegro.client import OFFERS_PAGE_SIZE, AllegroClient
from app.integrations.mapping import obj as _obj
from app.integrations.mapping import text as _text
from app.models.order import OrderSource
from app.schemas.catalog import OfferSnapshot

logger = logging.getLogger(__name__)

# a safety stop, not a limit anyone should meet: 500 pages is fifty thousand offers
MAX_PAGES = 500
# how far up a category's parents the way to the top is followed
MAX_CATEGORY_DEPTH = 12


def _decimal(value: Any) -> Decimal | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def image_urls(raw: dict[str, Any]) -> tuple[str, ...]:
    """The addresses in an offer's `images` (a list of addresses, or of `{"url": ...}`), in order,
    each once."""
    images = raw.get("images")
    found: list[str] = []
    if isinstance(images, list):
        for image in images:
            url = _text(image.get("url")) if isinstance(image, dict) else _text(image)
            if url and url.startswith("https://") and url not in found:
                found.append(url)
    return tuple(found)


def map_offer(raw: dict[str, Any]) -> OfferSnapshot | None:
    """One entry of GET /sale/offers, or None without an id or a name."""
    offer_id = _text(raw.get("id"))
    name = _text(raw.get("name"))
    if offer_id is None or name is None:
        return None
    price = _obj(_obj(raw.get("sellingMode")).get("price"))
    cover = _text(_obj(raw.get("primaryImage")).get("url"))
    return OfferSnapshot(
        offer_id=offer_id,
        name=name,
        status=(_text(_obj(raw.get("publication")).get("status")) or "UNKNOWN").upper(),
        sku=_text(_obj(raw.get("external")).get("id")),
        price=_decimal(price.get("amount")),
        currency=_text(price.get("currency")),
        stock=_whole(_obj(raw.get("stock")).get("available")),
        category_id=_text(_obj(raw.get("category")).get("id")),
        image_urls=(cover,) if cover else (),
    )


class AllegroCatalogAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, client: AllegroClient):
        self.client = client
        # id -> (name, parent id), for the length of one sync: a few dozen categories cover
        # hundreds of offers
        self._categories: dict[str, tuple[str, str | None]] = {}

    def iter_offers(self) -> Iterator[OfferSnapshot]:
        """Every offer that is not ended, page by page. A page that fails ends the iteration
        with the error, so a caller never takes a partial list for the whole."""
        offset = 0
        for _ in range(MAX_PAGES):
            raw_offers, total = self.client.fetch_offers_page(offset=offset)
            for raw in raw_offers:
                offer = map_offer(raw)
                if offer is None:
                    logger.warning("Allegro offer without an id or a name skipped")
                    continue
                yield offer
            offset += len(raw_offers)
            if not raw_offers or len(raw_offers) < OFFERS_PAGE_SIZE or (total is not None and offset >= total):
                return

    def fetch_images(self, offer_id: str) -> tuple[str, ...]:
        """All of an offer's pictures, in the offer's order. Raises when they cannot be read."""
        return image_urls(self.client.fetch_product_offer(offer_id))

    def category_path(self, category_id: str) -> list[dict[str, str]]:
        """The way to a category from the top of Allegro's tree, as {"id", "name"} steps with the
        category itself last. Raises when a step cannot be read."""
        steps: list[dict[str, str]] = []
        current: str | None = category_id
        for _ in range(MAX_CATEGORY_DEPTH):
            if current is None:
                break
            if current not in self._categories:
                raw = self.client.fetch_category(current)
                parent = _text(_obj(raw.get("parent")).get("id"))
                self._categories[current] = (_text(raw.get("name")) or current, parent)
            name, parent = self._categories[current]
            steps.append({"id": current, "name": name})
            current = parent
        steps.reverse()
        return steps
