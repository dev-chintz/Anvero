import logging
from collections.abc import Iterator
from datetime import datetime

from app.integrations.base import IntegrationUnavailable
from app.integrations.erli.billing import (
    is_known_other,
    map_billing_entry,
    map_billing_types,
    map_payout,
)
from app.integrations.erli.client import (
    BILLING_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PAYOUT_PAGE_SIZE,
    ErliClient,
    erli_timestamp,
)
from app.integrations.erli.mapper import OrderMappingError, map_order
from app.integrations.mapping import KnownImages, attach_item_images
from app.models.order import OrderSource
from app.schemas.order import BillingEntryCreate, OrderCreate, PayoutCreate

logger = logging.getLogger(__name__)

# 200 orders a page; a safety stop, not a limit anyone should meet
MAX_PAGES = 500


class ErliAdapter:
    """Erli's side of the MarketplaceAdapter protocol."""

    source = OrderSource.ERLI

    def __init__(self, client: ErliClient | None = None, known_images: KnownImages | None = None):
        self._client = client or ErliClient()
        self._known_images = known_images

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def fetch_orders(self, limit: int = MAX_PAGE_SIZE, offset: int = 0) -> list[OrderCreate]:
        """The first page of orders by update time, oldest change first.

        Erli pages by cursor, not by offset, so only the first page can be
        asked for this way; `iter_order_pages` is what an import uses.
        """
        if offset:
            raise ValueError("Erli pages by cursor; use iter_order_pages")
        return self._map(self._client.search_orders(limit=limit))

    def iter_order_pages(
        self,
        bought_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> Iterator[list[OrderCreate]]:
        """Yield every page of orders placed, or changed, since the given time.

        Each page after the first starts at the last order's `cursor`, which
        Erli makes unique, so orders changed at the same moment are neither
        repeated nor skipped. Paging stops on the first raw page shorter than
        the page size; running out of pages is an error rather than a quiet
        stop, so the caller does not record a complete sync it did not make.
        """
        after = erli_timestamp(updated_since) if updated_since is not None else None
        for _ in range(MAX_PAGES):
            raw = self._client.search_orders(
                after=after, limit=MAX_PAGE_SIZE, created_since=bought_since
            )
            yield self._map(raw)
            if len(raw) < MAX_PAGE_SIZE:
                return
            after = raw[-1].get("cursor")
            if not isinstance(after, str) or not after:
                raise IntegrationUnavailable(
                    "Erli returned a full page without a cursor to continue from"
                )
        raise IntegrationUnavailable(
            f"Erli returned more than {MAX_PAGES * MAX_PAGE_SIZE} orders for one "
            "import; narrow the window and run it again"
        )

    def fetch_billing_entries(self, since: datetime) -> list[BillingEntryCreate]:
        """The fees and settlements on Erli's billing account since `since`, all pages.

        Raises rather than returning part of them if a page fails, so the
        caller does not record a complete read it did not make. Entries of a
        kind Erli names but that is neither (a rebate set aside, an amount
        blocked) are left out quietly; one Erli does not name is logged.
        """
        types = map_billing_types(self._client.fetch_billing_types())
        entries: list[BillingEntryCreate] = []
        unknown: set[str] = set()
        before_id: int | None = None
        for _ in range(MAX_PAGES):
            raw = self._client.fetch_billing_entries(since, before_id, BILLING_PAGE_SIZE)
            for item in raw:
                entry = map_billing_entry(item, types)
                if entry is not None:
                    entries.append(entry)
                elif not is_known_other(item, types):
                    unknown.add(str(item.get("type")))
            if len(raw) < BILLING_PAGE_SIZE:
                break
            last = raw[-1].get("id")
            if not isinstance(last, int):
                raise IntegrationUnavailable(
                    "Erli returned a full page of billing entries without an id to continue from"
                )
            before_id = last
        else:
            raise IntegrationUnavailable(
                "Erli returned too many billing entries; narrow the window and run it again"
            )
        if unknown:
            logger.warning("Erli billing entries of unknown kinds left out: %s", ", ".join(sorted(unknown)))
        return entries

    def fetch_payouts(self, since: datetime) -> list[PayoutCreate]:
        """The payouts to the seller's bank account made since `since`, all pages."""
        payouts: list[PayoutCreate] = []
        after_id: int | None = None
        for _ in range(MAX_PAGES):
            raw = self._client.search_payouts(since, after_id, PAYOUT_PAGE_SIZE)
            payouts.extend(p for p in (map_payout(item) for item in raw) if p is not None)
            if len(raw) < PAYOUT_PAGE_SIZE:
                return payouts
            last = raw[-1].get("id")
            if not isinstance(last, int):
                raise IntegrationUnavailable("Erli returned a full page of payouts without an id to continue from")
            after_id = last
        raise IntegrationUnavailable("Erli returned too many payouts; narrow the window and run it again")

    def _map(self, raw_orders: list[dict]) -> list[OrderCreate]:
        orders: list[OrderCreate] = []
        for raw in raw_orders:
            try:
                orders.append(map_order(raw))
            except OrderMappingError as exc:
                # one unusable order must not cost the rest of the page
                logger.warning("Skipping Erli order that could not be mapped: %s", exc)
        self._attach_item_images(orders)
        return orders

    def _attach_item_images(self, orders: list[OrderCreate]) -> None:
        """Give each item its picture: the one already held, else one call per product.

        Best-effort: fetch_product_image never raises, so a picture that could
        not be read just leaves that item without one.
        """
        attach_item_images(orders, self._client.fetch_product_image, self._known_images)
