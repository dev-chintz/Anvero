import logging
from collections.abc import Iterator
from datetime import datetime

from app.integrations.allegro.client import (
    MAX_PAGE_SIZE,
    MAX_TRACKING_WAYBILLS,
    AllegroClient,
)
from app.integrations.allegro.mapper import (
    OrderMappingError,
    map_billing_entry,
    map_checkout_form,
    map_shipment,
    map_tracking,
)
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationUnavailable,
)
from app.models.order import OrderSource, OrderStatus
from app.schemas.order import BillingEntryCreate, OrderCreate

logger = logging.getLogger(__name__)

# 100 orders a page; a safety stop, not a limit anyone should meet
MAX_PAGES = 500


# The seller statuses of an order that is not done. Such an order can still change
# (a shipment is created for it, it is marked ready or sent) without Allegro
# counting that as a change of the order since the last import, so an import reads
# all of them again whatever its window.
OPEN_FULFILLMENT_STATUSES = (
    "NEW",
    "PROCESSING",
    "READY_FOR_SHIPMENT",
    "READY_FOR_PICKUP",
    "SUSPENDED",
)


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

    def iter_open_order_pages(self) -> Iterator[list[OrderCreate]]:
        """Yield every page of the orders that are not done, one status at a time.

        Allegro's list takes one `fulfillment.status` per request. Like every
        pager here, running out of pages is an error, so a caller never takes a
        partial read for a complete one.
        """
        for status in OPEN_FULFILLMENT_STATUSES:
            for page_number in range(MAX_PAGES):
                orders, raw_count = self._fetch_page(
                    MAX_PAGE_SIZE,
                    page_number * MAX_PAGE_SIZE,
                    None,
                    None,
                    fulfillment_status=status,
                )
                yield orders
                if raw_count < MAX_PAGE_SIZE:
                    break
            else:
                raise IntegrationUnavailable(
                    f"Allegro returned more than {MAX_PAGES * MAX_PAGE_SIZE} orders in status "
                    f"{status}; narrow the window and run it again"
                )

    def fetch_billing_entries(self, since: datetime) -> list[BillingEntryCreate]:
        """Every billing entry that occurred at or after `since`, all pages.

        Raises rather than returning what it has if a page fails, so the
        caller does not record a complete read it did not make. Entries that
        cannot be mapped are skipped and logged by count.
        """
        entries: list[BillingEntryCreate] = []
        skipped = 0
        for page_number in range(MAX_PAGES):
            raw = self._client.fetch_billing_entries(
                since, MAX_PAGE_SIZE, page_number * MAX_PAGE_SIZE
            )
            for item in raw:
                entry = map_billing_entry(item)
                if entry is None:
                    skipped += 1
                else:
                    entries.append(entry)
            if len(raw) < MAX_PAGE_SIZE:
                break
        else:
            raise IntegrationUnavailable(
                f"Allegro returned more than {MAX_PAGES * MAX_PAGE_SIZE} billing entries; "
                "narrow the window and run it again"
            )
        if skipped:
            logger.warning("%d billing entries could not be mapped and were skipped", skipped)
        return entries

    def _fetch_page(
        self,
        limit: int,
        offset: int,
        bought_since: datetime | None,
        updated_since: datetime | None,
        fulfillment_status: str | None = None,
    ) -> tuple[list[OrderCreate], int]:
        extra = {"fulfillment_status": fulfillment_status} if fulfillment_status else {}
        checkout_forms = self._client.fetch_checkout_forms(
            limit=limit,
            offset=offset,
            bought_since=bought_since,
            updated_since=updated_since,
            **extra,
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
        self._attach_shipments(orders)
        return orders, len(checkout_forms)

    def _attach_shipments(self, orders: list[OrderCreate]) -> None:
        """Read the parcels of orders, and where each is now.

        Every order that is neither new nor cancelled is asked about, one call
        each: a parcel is created (a label bought in "Wysyłam z Allegro", a
        tracking number entered) while the order is still being processed, and
        Allegro keeps the order in that status until it is marked sent, so waiting
        for "sent" would show the parcel days late. Best effort like the pictures: an order whose shipments could not be read
        keeps `shipments = None`, which leaves the stored ones alone, and a
        refused request (the application lacking the scope) ends the attempt
        for the rest of the run instead of failing every order the same way.
        """
        for order in orders:
            if order.status in (OrderStatus.NEW, OrderStatus.CANCELLED):
                continue
            try:
                raw = self._client.fetch_shipments(order.external_id)
            except IntegrationAuthError as exc:
                logger.warning("Shipments not read, so none will be this run: %s", exc)
                return
            except IntegrationError as exc:
                logger.warning("Shipments of an order could not be read: %s", exc)
                continue
            order.shipments = [
                shipment
                for item in raw
                if (shipment := map_shipment(order.external_id, item)) is not None
            ]

        self._attach_tracking(orders)

    def _attach_tracking(self, orders: list[OrderCreate]) -> None:
        """Fill in the tracking status of parcels still on their way."""
        waiting = [
            shipment
            for order in orders
            if order.status is OrderStatus.SHIPPED
            for shipment in order.shipments or []
        ]
        by_key = {(s.carrier_id, s.waybill): s for s in waiting if s.carrier_id}
        for shipment_key, (code, at) in self.fetch_tracking(list(by_key)).items():
            shipment = by_key[shipment_key]
            shipment.tracking_status = code
            shipment.tracking_updated_at = at

    def fetch_tracking(
        self, keys: list[tuple[str | None, str]]
    ) -> dict[tuple[str | None, str], tuple[str, datetime | None]]:
        """Where each parcel is, by (carrier, waybill); parcels nothing is known about are left out.

        Grouped by carrier and asked in batches of Allegro's limit. Best
        effort: a batch that fails costs those parcels a status, not the run.
        """
        result: dict[tuple[str | None, str], tuple[str, datetime | None]] = {}
        by_carrier: dict[str, list[str]] = {}
        for carrier_id, waybill in keys:
            if carrier_id:
                by_carrier.setdefault(carrier_id, []).append(waybill)

        for carrier_id, waybills in by_carrier.items():
            for start in range(0, len(waybills), MAX_TRACKING_WAYBILLS):
                batch = waybills[start : start + MAX_TRACKING_WAYBILLS]
                try:
                    found = self._client.fetch_tracking(carrier_id, batch)
                except IntegrationAuthError as exc:
                    logger.warning("Tracking not read, so none will be this run: %s", exc)
                    return result
                except IntegrationError as exc:
                    logger.warning("Tracking of %s could not be read: %s", carrier_id, exc)
                    continue
                for item in found:
                    tracking = map_tracking(item)
                    waybill = item.get("waybill")
                    if tracking is not None and isinstance(waybill, str):
                        result[(carrier_id, waybill)] = tracking
        return result

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
