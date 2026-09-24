import logging
from collections.abc import Iterator
from datetime import datetime

from app.integrations.base import IntegrationUnavailable
from app.integrations.erli.client import MAX_PAGE_SIZE, ErliClient, erli_timestamp
from app.integrations.erli.mapper import OrderMappingError, map_order
from app.models.order import OrderSource
from app.schemas.order import OrderCreate

logger = logging.getLogger(__name__)

# 200 orders a page; a safety stop, not a limit anyone should meet
MAX_PAGES = 500


class ErliAdapter:
    """Erli's side of the MarketplaceAdapter protocol."""

    source = OrderSource.ERLI

    def __init__(self, client: ErliClient | None = None):
        self._client = client or ErliClient()

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

    @staticmethod
    def _map(raw_orders: list[dict]) -> list[OrderCreate]:
        orders: list[OrderCreate] = []
        for raw in raw_orders:
            try:
                orders.append(map_order(raw))
            except OrderMappingError as exc:
                # one unusable order must not cost the rest of the page
                logger.warning("Skipping Erli order that could not be mapped: %s", exc)
        return orders
