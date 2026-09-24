"""Changes made in Anvero, sent to Allegro through safe mode."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.integrations.allegro.client import ACCEPT_HEADER, AllegroClient
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.models.marketplace_write import MarketplaceWrite, WriteOutcome
from app.models.order import Order, OrderSource, OrderStatus
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, ShipmentCreate
from app.services import order_writes
from app.services.allegro_sync import import_lock
from app.services.marketplace_writes import set_safe_mode
from app.services.order_import_service import OrderImportService
from app.services.order_writes import OrderWrites

# `session` comes from tests/conftest.py


class FakeAllegro:
    def __init__(self, error=None, shipment_id="shipment-1"):
        self.statuses = []
        self.shipments = []
        self.error = error
        self.shipment_id = shipment_id

    def set_fulfillment_status(self, checkout_form_id, status):
        if self.error:
            raise self.error
        self.statuses.append((checkout_form_id, status))

    def add_shipment(self, checkout_form_id, carrier_id, waybill, carrier_name=None):
        if self.error:
            raise self.error
        self.shipments.append((checkout_form_id, carrier_id, waybill, carrier_name))
        return {"id": self.shipment_id}


def _order(session, source=OrderSource.ALLEGRO, status=OrderStatus.NEW):
    order = Order(
        external_id="form-1",
        source=source,
        status=status,
        marketplace_status=OrderStatus.NEW,
        marketplace_status_label="NEW",
        customer_email="buyer@example.com",
        total_amount=Decimal("10.00"),
        currency="PLN",
    )
    session.add(order)
    session.commit()
    return order


def _set_status(session, order, status, allegro):
    OrderRepository(session).update_status(order, status, changed_by_user_id=None)
    return OrderWrites(session, client_factory=lambda: allegro).push_status(order, None)


# --- the status -----------------------------------------------------------------


def test_in_safe_mode_the_status_is_only_recorded(session):
    allegro = FakeAllegro()
    order = _order(session)

    result = _set_status(session, order, OrderStatus.READY_FOR_SHIPMENT, allegro)

    assert result.outcome is WriteOutcome.DRY_RUN
    assert allegro.statuses == []
    # nothing reached Allegro, so what Allegro says is unchanged
    assert order.marketplace_status is OrderStatus.NEW


@pytest.mark.parametrize(
    ("status", "fulfillment"),
    [
        (OrderStatus.CONFIRMED, "PROCESSING"),
        (OrderStatus.READY_FOR_SHIPMENT, "READY_FOR_SHIPMENT"),
        (OrderStatus.SHIPPED, "SENT"),
        (OrderStatus.DELIVERED, "PICKED_UP"),
    ],
)
def test_with_safe_mode_off_allegro_is_told(session, status, fulfillment):
    set_safe_mode(session, False, None)
    allegro = FakeAllegro()
    order = _order(session)

    result = _set_status(session, order, status, allegro)

    assert result.outcome is WriteOutcome.SENT
    assert allegro.statuses == [("form-1", fulfillment)]
    # the next import must not read this as Allegro moving on its own
    assert (order.marketplace_status, order.marketplace_status_label) == (status, fulfillment)


def test_a_cancellation_is_not_sent(session):
    set_safe_mode(session, False, None)
    allegro = FakeAllegro()

    assert _set_status(session, _order(session), OrderStatus.CANCELLED, allegro) is None
    assert allegro.statuses == []


def test_an_erli_order_is_not_written_to(session):
    set_safe_mode(session, False, None)
    order = _order(session, source=OrderSource.ERLI)

    assert _set_status(session, order, OrderStatus.SHIPPED, FakeAllegro()) is None


def test_a_refusal_is_reported_and_the_status_stays(session):
    set_safe_mode(session, False, None)
    allegro = FakeAllegro(error=IntegrationUnavailable("Allegro refused it (422): bad state"))
    order = _order(session)

    result = _set_status(session, order, OrderStatus.SHIPPED, allegro)

    assert result.outcome is WriteOutcome.FAILED
    assert "bad state" in result.record.detail
    assert order.status is OrderStatus.SHIPPED
    assert order.marketplace_status is OrderStatus.NEW


def test_a_write_waits_for_a_running_import_and_gives_up(session, monkeypatch):
    set_safe_mode(session, False, None)
    monkeypatch.setattr(order_writes, "WRITE_LOCK_TIMEOUT_SECONDS", 0.05)
    allegro = FakeAllegro()
    order = _order(session)

    assert import_lock.acquire(blocking=False)
    try:
        result = _set_status(session, order, OrderStatus.SHIPPED, allegro)
    finally:
        import_lock.release()

    assert result.outcome is WriteOutcome.FAILED
    assert "import is running" in result.record.detail
    assert allegro.statuses == []


# --- the tracking number -----------------------------------------------------------


def test_a_tracking_number_is_kept_and_held_back_in_safe_mode(session):
    allegro = FakeAllegro()
    order = _order(session)

    shipment, result = OrderWrites(session, client_factory=lambda: allegro).add_shipment(
        order, "INPOST", None, "620111", None
    )

    assert result.outcome is WriteOutcome.DRY_RUN
    assert allegro.shipments == []
    assert (shipment.carrier_id, shipment.waybill, shipment.added_in_anvero) == ("INPOST", "620111", True)
    assert shipment.external_id is None


def test_a_sent_tracking_number_takes_allegros_id(session):
    set_safe_mode(session, False, None)
    allegro = FakeAllegro(shipment_id="alg-ship-9")
    order = _order(session)

    shipment, result = OrderWrites(session, client_factory=lambda: allegro).add_shipment(
        order, "OTHER", "Kurier Janek", "JN-1", None
    )

    assert result.outcome is WriteOutcome.SENT
    assert allegro.shipments == [("form-1", "OTHER", "JN-1", "Kurier Janek")]
    assert shipment.external_id == "alg-ship-9"


def test_an_erli_parcel_is_stored_without_writing(session):
    order = _order(session, source=OrderSource.ERLI)

    shipment, result = OrderWrites(session).add_shipment(order, "INPOST", None, "X1", None)

    assert result is None
    assert shipment.waybill == "X1"
    assert session.query(MarketplaceWrite).count() == 0


# --- the import after it: the last change made in Anvero wins --------------------------


class ListAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, orders):
        self.orders = orders

    def fetch_orders(self, limit=100, offset=0):
        return self.orders


def _import(session, status, updated_at, shipments=None):
    data = OrderCreate(
        external_id="form-1",
        source=OrderSource.ALLEGRO,
        status=status,
        customer_email="buyer@example.com",
        total_amount=Decimal("10.00"),
        marketplace_updated_at=updated_at,
        shipments=shipments,
    )
    OrderImportService(OrderRepository(session), ListAdapter([data])).import_orders()


def test_an_allegro_change_older_than_the_operators_does_not_undo_it(session):
    order = _order(session)
    OrderRepository(session).update_status(order, OrderStatus.READY_FOR_SHIPMENT, changed_by_user_id=None)
    order.status_set_at = datetime.now(UTC)
    session.commit()

    # Allegro moved to PROCESSING a minute before the operator's change
    _import(session, OrderStatus.CONFIRMED, datetime.now(UTC) - timedelta(minutes=1))

    session.refresh(order)
    assert order.status is OrderStatus.READY_FOR_SHIPMENT
    # what Allegro said is still noted, for the comparison next time
    assert order.marketplace_status is OrderStatus.CONFIRMED


def test_an_allegro_change_after_the_operators_wins(session):
    order = _order(session)
    order.status_set_at = datetime.now(UTC) - timedelta(minutes=5)
    session.commit()

    _import(session, OrderStatus.CANCELLED, datetime.now(UTC))

    session.refresh(order)
    assert order.status is OrderStatus.CANCELLED


def test_the_operators_status_counts_from_the_api(session):
    order = _order(session)

    OrderRepository(session).update_status(order, OrderStatus.SHIPPED, changed_by_user_id=None)
    assert order.status_set_at is None  # the import itself does not count

    operator = User(email="o@example.com", hashed_password="x")
    session.add(operator)
    session.commit()
    OrderRepository(session).update_status(order, OrderStatus.DELIVERED, changed_by_user_id=operator.id)
    assert order.status_set_at is not None


def test_a_parcel_typed_in_survives_an_import_that_does_not_list_it(session):
    order = _order(session)
    OrderWrites(session).add_shipment(order, "INPOST", None, "HELD-1", None)

    _import(
        session,
        OrderStatus.SHIPPED,
        datetime.now(UTC),
        shipments=[ShipmentCreate(external_id="a-1", carrier_id="DPD", waybill="ALLEGRO-1")],
    )

    session.refresh(order)
    assert sorted(s.waybill for s in order.shipments) == ["ALLEGRO-1", "HELD-1"]


def test_once_allegro_lists_it_the_typed_in_parcel_is_not_doubled(session):
    order = _order(session)
    OrderWrites(session).add_shipment(order, "INPOST", None, "SAME-1", None)

    _import(
        session,
        OrderStatus.SHIPPED,
        datetime.now(UTC),
        shipments=[ShipmentCreate(external_id="a-1", carrier_id="INPOST", waybill="SAME-1")],
    )

    session.refresh(order)
    assert [(s.waybill, s.external_id) for s in order.shipments] == [("SAME-1", "a-1")]


# --- the client's two writes ------------------------------------------------------------


def _client(handler):
    return AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url="https://api.test",
        auth_url="https://auth.test",
        user_agent="anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def _with_token(handler):
    def wrapped(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return handler(request)

    return wrapped


def test_the_fulfillment_status_is_a_put_with_the_versioned_body():
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["type"] = request.headers["Content-Type"]
        seen["body"] = request.content
        return httpx2.Response(204)

    _client(_with_token(handler)).set_fulfillment_status("form-1", "SENT")

    assert (seen["method"], seen["path"]) == ("PUT", "/order/checkout-forms/form-1/fulfillment")
    assert seen["type"] == ACCEPT_HEADER
    assert seen["body"] == b'{"status":"SENT"}'


def test_a_tracking_number_is_posted_and_its_id_returned():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/order/checkout-forms/form-1/shipments"
        return httpx2.Response(201, json={"id": "ship-1", "waybill": "W1"})

    answer = _client(_with_token(handler)).add_shipment("form-1", "INPOST", "W1")

    assert answer["id"] == "ship-1"


def test_a_missing_write_scope_is_an_auth_error():
    with pytest.raises(IntegrationAuthError, match="orders:write"):
        _client(_with_token(lambda r: httpx2.Response(403))).set_fulfillment_status("f", "SENT")


def test_allegros_reason_for_refusing_is_kept():
    refusal = httpx2.Response(422, json={"errors": [{"message": "Invalid status transition"}]})

    with pytest.raises(IntegrationUnavailable, match="Invalid status transition"):
        _client(_with_token(lambda r: refusal)).set_fulfillment_status("f", "NEW")
