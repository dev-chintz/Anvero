"""Changes made in Anvero that belong on the order's marketplace too.

A status set by hand and a tracking number typed in are sent to Allegro
through MarketplaceWriter, so safe mode decides whether they really go. Erli
is not written to yet: its orders change in Anvero only.
"""

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.integrations.allegro.client import AllegroClient
from app.integrations.base import IntegrationUnavailable
from app.models.marketplace_write import WriteOutcome
from app.models.order import Order, OrderShipment, OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.services.allegro_import import build_allegro_client
from app.services.allegro_sync import import_lock
from app.services.marketplace_writes import MarketplaceWriter, WriteResult

logger = logging.getLogger(__name__)

# Anvero's status as Allegro's fulfillment status. CANCELLED is left out on
# purpose: marking an Allegro order cancelled this way refunds no one, and
# cancelling one is done on Allegro, whose cancellation the import then brings
# back (DECISIONS.md).
FULFILLMENT_FOR_STATUS = {
    OrderStatus.NEW: "NEW",
    OrderStatus.CONFIRMED: "PROCESSING",
    OrderStatus.READY_FOR_SHIPMENT: "READY_FOR_SHIPMENT",
    OrderStatus.SHIPPED: "SENT",
    OrderStatus.DELIVERED: "PICKED_UP",
}

# The carriers offered when a tracking number is typed in, by Allegro's ids
# (GET /order/carriers). OTHER takes a name of its own.
ALLEGRO_CARRIERS = (
    "INPOST",
    "DPD",
    "DHL",
    "POCZTA_POLSKA",
    "UPS",
    "GLS",
    "FEDEX",
    "ALLEGRO",
    "OTHER",
)

# Allegro rotates the refresh token on every use, and an import holds this
# lock while it does; a write waits for it rather than refreshing alongside
# and invalidating the import's token (or its own)
WRITE_LOCK_TIMEOUT_SECONDS = 60

ClientFactory = Callable[[], AllegroClient]


def _with_import_lock(action: Callable[[], object]) -> object:
    if not import_lock.acquire(timeout=WRITE_LOCK_TIMEOUT_SECONDS):
        raise IntegrationUnavailable(
            "An Allegro import is running; the change was not sent, try again in a minute"
        )
    try:
        return action()
    finally:
        import_lock.release()


class OrderWrites:
    def __init__(self, db: Session, client_factory: ClientFactory | None = None):
        self.db = db
        self.repository = OrderRepository(db)
        self.writer = MarketplaceWriter(db)
        self._client_factory = client_factory or (lambda: build_allegro_client(db))

    def push_status(self, order: Order, user_id: int | None) -> WriteResult | None:
        """Tell the marketplace the status just set in Anvero.

        None when there is nothing to tell: an order that is not Allegro's,
        or a status Allegro is not told (CANCELLED). A failure to send is
        recorded and returned, not raised: the status stays as the operator
        set it, and they are told it did not reach Allegro.
        """
        fulfillment = FULFILLMENT_FOR_STATUS.get(order.status)
        if order.source is not OrderSource.ALLEGRO or fulfillment is None:
            return None

        def send() -> None:
            client = self._client_factory()
            _with_import_lock(lambda: client.set_fulfillment_status(order.external_id, fulfillment))

        result = self._write(
            order,
            "fulfillment_status",
            {"checkoutFormId": order.external_id, "status": fulfillment},
            send,
            user_id,
        )
        if result.outcome is WriteOutcome.SENT:
            # Allegro now says what Anvero says, so the next import does not
            # read this change as Allegro moving on its own
            self.repository.record_marketplace_status(order, order.status, fulfillment)
        return result

    def add_shipment(
        self,
        order: Order,
        carrier_id: str,
        carrier_name: str | None,
        waybill: str,
        user_id: int | None,
    ) -> tuple[OrderShipment, WriteResult | None]:
        """Store a parcel typed in, and send its tracking number to Allegro.

        The parcel is kept in Anvero whatever happens to the sending; the
        import keeps a parcel Allegro does not list yet (see order_details).
        """
        shipment = self.repository.add_shipment(order, carrier_id, carrier_name, waybill)
        if order.source is not OrderSource.ALLEGRO:
            return shipment, None

        payload = {"checkoutFormId": order.external_id, "carrierId": carrier_id, "waybill": waybill}
        if carrier_name:
            payload["carrierName"] = carrier_name

        def send():
            client = self._client_factory()
            return _with_import_lock(
                lambda: client.add_shipment(order.external_id, carrier_id, waybill, carrier_name)
            )

        result = self._write(order, "shipment", payload, send, user_id)
        answer = result.response if isinstance(result.response, dict) else {}
        if result.outcome is WriteOutcome.SENT and isinstance(answer.get("id"), str):
            # from now on the import knows it by Allegro's id
            self.repository.set_shipment_external_id(shipment, answer["id"])
        return shipment, result

    def _write(self, order, action, payload, send, user_id) -> WriteResult:
        # a failure comes back as a FAILED result rather than an error: the
        # operator's change in Anvero stands, and they are shown why Allegro
        # did not take it
        result = self.writer.write(
            OrderSource.ALLEGRO,
            action,
            payload,
            send,
            order_id=order.id,
            user_id=user_id,
            raise_errors=False,
        )
        # the writer rolled back on failure, which expires loaded objects
        self.db.refresh(order)
        return result
