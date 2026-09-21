import logging
from collections.abc import Iterator
from datetime import datetime

from app.integrations.allegro.client import MAX_PAGE_SIZE, AllegroClient
from app.integrations.allegro.mapper import OrderMappingError, map_checkout_form
from app.integrations.base import IntegrationUnavailable
from app.models.order import OrderSource
from app.schemas.order import OrderCreate

logger = logging.getLogger(__name__)

# 100 orders a page; a safety stop, not a limit anyone should meet
MAX_PAGES = 500


class AllegroAdapter:
    """Allegro's side of the MarketplaceAdapter protocol."""

    source = OrderSource.ALLEGRO

    def __init__(self, client: AllegroClient | None = None):
        self._client = client or AllegroClient()

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def fetch_orders(
        self,
        limit: int = MAX_PAGE_SIZE,
        offset: int = 0,
        bought_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[OrderCreate]:
        return self._fetch_page(limit, offset, bought_since, updated_since)[0]

    def iter_order_pages(
        self,
        bought_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> Iterator[list[OrderCreate]]:
        """Yield every page of orders matching the filters, oldest page last.

        Paging stops on the first raw page shorter than the page size, not
        the first mapped page: an order that cannot be mapped is dropped from
        a page, and counting what is left would end the run early. Running
        out of pages (MAX_PAGES) is an error rather than a quiet stop, so the
        caller does not record a complete sync it did not make.
        """
        for page_number in range(MAX_PAGES):
            orders, raw_count = self._fetch_page(
                MAX_PAGE_SIZE,
                page_number * MAX_PAGE_SIZE,
                bought_since,
                updated_since,
            )
            yield orders
            if raw_count < MAX_PAGE_SIZE:
                return
        raise IntegrationUnavailable(
            f"Allegro returned more than {MAX_PAGES * MAX_PAGE_SIZE} orders for one "
            "import; narrow the window and run it again"
        )

    def _fetch_page(
        self,
        limit: int,
        offset: int,
        bought_since: datetime | None,
        updated_since: datetime | None,
    ) -> tuple[list[OrderCreate], int]:
        checkout_forms = self._client.fetch_checkout_forms(
            limit=limit,
            offset=offset,
            bought_since=bought_since,
            updated_since=updated_since,
        )

        orders: list[OrderCreate] = []
        for checkout_form in checkout_forms:
            try:
                orders.append(map_checkout_form(checkout_form))
            except OrderMappingError as exc:
                # one unusable order must not cost us the rest of the page;
                # it is logged so the gap is visible rather than silent
                logger.warning("Skipping Allegro order that could not be mapped: %s", exc)

        self._attach_item_images(orders)
        return orders, len(checkout_forms)

    def _attach_item_images(self, orders: list[OrderCreate]) -> None:
        """Fetch each item's picture, one call per distinct offer in the page.

        Best-effort: fetch_offer_image never raises, so a picture that could
        not be read just leaves that item without one.
        """
        images_by_offer: dict[str, str | None] = {}
        for order in orders:
            for item in order.items:
                if not item.offer_id:
                    continue
                if item.offer_id not in images_by_offer:
                    images_by_offer[item.offer_id] = self._client.fetch_offer_image(
                        item.offer_id
                    )
                item.image_url = images_by_offer[item.offer_id]
