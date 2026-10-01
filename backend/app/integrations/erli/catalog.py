"""The shop's Erli products, read for the assortment (docs/CATALOG.md).

Built from Erli's published API description (`POST /products/_search`) and not yet seen on the real
service: which of a product's references and categories Erli fills for a copy of an Allegro offer
is exactly what the first real sync shows (INTEGRATIONS.md, "Assortment").
"""

import logging
import re
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

from app.integrations.erli.client import PRODUCT_PAGE_SIZE, ErliClient
from app.integrations.mapping import obj as _obj
from app.integrations.mapping import text as _text
from app.models.order import OrderSource
from app.schemas.catalog import ErliProductSnapshot

logger = logging.getLogger(__name__)

# a safety stop, not a limit anyone should meet: 500 pages is a hundred thousand products
MAX_PAGES = 500

# Erli's short way to write a reference: "allegro:12345678901"
_SHORT_ALLEGRO_REFERENCE = re.compile(r"^allegro:(\d{6,14})$")


def _steps(chain: Any) -> tuple[dict[str, str], ...]:
    """A category chain as {"id", "name"} steps, from the top; entries without a name are dropped."""
    steps: list[dict[str, str]] = []
    if isinstance(chain, list):
        for step in chain:
            name = _text(_obj(step).get("name"))
            if name:
                steps.append({"id": _text(_obj(step).get("id")) or name, "name": name})
    return tuple(steps)


def allegro_offer_ids(raw: dict[str, Any]) -> tuple[str, ...]:
    """The Allegro offers a product says it copies: the `allegro` entries of `externalReferences`,
    written as `{"kind": "allegro", "id": ...}` or as the string `allegro:<id>`."""
    found: list[str] = []
    references = raw.get("externalReferences")
    for reference in references if isinstance(references, list) else []:
        if isinstance(reference, dict):
            if _text(reference.get("kind")) == "allegro":
                offer_id = _text(reference.get("id"))
                if offer_id and offer_id not in found:
                    found.append(offer_id)
        elif isinstance(reference, str):
            match = _SHORT_ALLEGRO_REFERENCE.match(reference.strip())
            if match and match.group(1) not in found:
                found.append(match.group(1))
    return tuple(found)


def map_product(raw: dict[str, Any]) -> ErliProductSnapshot | None:
    """One entry of POST /products/_search, or None without an `externalId`."""
    external_id = _text(raw.get("externalId"))
    if external_id is None:
        return None

    # Erli's own category: the first chain of `categories` (a list of chains)
    own: tuple[dict[str, str], ...] = ()
    chains = raw.get("categories")
    for chain in chains if isinstance(chains, list) else []:
        own = _steps(chain)
        if own:
            break
    # and the one the product came with, preferring Allegro's
    given: tuple[dict[str, str], ...] = ()
    raw_externals = raw.get("externalCategories")
    externals = [e for e in raw_externals if isinstance(e, dict)] if isinstance(raw_externals, list) else []
    externals.sort(key=lambda e: _text(e.get("source")) != "allegro")
    for external in externals:
        given = _steps(external.get("breadcrumb"))
        if given:
            break

    price = raw.get("price")
    stock = raw.get("stock")
    status = _text(raw.get("status"))
    return ErliProductSnapshot(
        external_id=external_id,
        # an archived product cannot be bought and is gone from the shop panel, whatever else
        status="ARCHIVED" if raw.get("archived") is True else (status.upper() if status else None),
        sku=_text(raw.get("sku")),
        # Erli's prices are in grosze
        price=(Decimal(price) / 100) if isinstance(price, int) and not isinstance(price, bool) else None,
        currency=_text(raw.get("currency")),
        stock=stock if isinstance(stock, int) and not isinstance(stock, bool) else None,
        allegro_offer_ids=allegro_offer_ids(raw),
        category_path=own,
        source_category_path=given,
    )


class ErliCatalogAdapter:
    source = OrderSource.ERLI

    def __init__(self, client: ErliClient):
        self.client = client

    def iter_products(self) -> Iterator[ErliProductSnapshot]:
        """Every product of the shop, page by page, by `externalId`. A page that fails ends the
        iteration with the error, so a caller never takes a partial list for the whole."""
        after: str | None = None
        for _ in range(MAX_PAGES):
            page = self.client.search_products(after=after)
            last: str | None = None
            for raw in page:
                last = _text(raw.get("externalId")) or last
                product = map_product(raw)
                if product is None:
                    logger.warning("Erli product without an externalId skipped")
                    continue
                yield product
            if len(page) < PRODUCT_PAGE_SIZE or last is None or last == after:
                return
            after = last
