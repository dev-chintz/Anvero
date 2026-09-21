"""Shipments and tracking: the client's two calls, their mapping, the adapter
reading them for orders that have left, and the import keeping them current."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.integrations.allegro.adapter import AllegroAdapter
from app.integrations.allegro.client import AllegroClient
from app.integrations.allegro.mapper import map_shipment, map_tracking
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.models.order import Order, OrderShipment, OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate, OrderDetails, ShipmentCreate
from app.services.order_import_service import OrderImportService


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


def _responding(payload=None, status=200):
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(status, json=payload or {})

    return handler, seen


# --- the client -------------------------------------------------------------


def test_fetches_the_shipments_of_one_order():
    handler, seen = _responding(
        {"shipments": [{"id": "S1", "waybill": "W1", "carrierId": "DHL"}]}
    )

    shipments = _client(handler).fetch_shipments("ORDER-1")

    assert shipments == [{"id": "S1", "waybill": "W1", "carrierId": "DHL"}]
    assert seen[0].url.path == "/order/checkout-forms/ORDER-1/shipments"


def test_asks_for_tracking_of_all_waybills_in_one_request():
    handler, seen = _responding({"carrierId": "DHL", "waybills": [{"waybill": "W1"}]})

    _client(handler).fetch_tracking("DHL", ["W1", "W2"])

    assert seen[0].url.path == "/order/carriers/DHL/tracking"
    assert seen[0].url.params.get_list("waybill") == ["W1", "W2"]


def test_more_waybills_than_allegro_accepts_is_refused_before_asking():
    handler, seen = _responding()

    with pytest.raises(ValueError):
        _client(handler).fetch_tracking("DHL", [f"W{i}" for i in range(21)])

    assert seen == []


def test_a_missing_scope_is_an_auth_error_and_a_server_error_is_not():
    denied, _ = _responding(status=403)
    broken, _ = _responding(status=503)

    with pytest.raises(IntegrationAuthError):
        _client(denied).fetch_shipments("ORDER-1")
    with pytest.raises(IntegrationUnavailable):
        _client(broken).fetch_shipments("ORDER-1")


# --- the mapping ------------------------------------------------------------


def test_maps_a_shipment():
    shipment = map_shipment(
        "ORDER-1",
        {
            "id": "S1",
            "waybill": "12345678910PL",
            "carrierId": "DHL",
            "createdAt": "2019-02-18T12:07:03.353Z",
        },
    )

    assert shipment is not None
    assert (shipment.carrier_id, shipment.waybill, shipment.external_id) == (
        "DHL",
        "12345678910PL",
        "S1",
    )
    assert shipment.shipped_at == datetime(2019, 2, 18, 12, 7, 3, 353000, tzinfo=UTC)


def test_a_shipment_without_a_waybill_is_dropped():
    assert map_shipment("ORDER-1", {"id": "S1", "carrierId": "DHL"}) is None


def test_tracking_is_the_latest_status_whatever_order_they_come_in():
    tracking = map_tracking(
        {
            "waybill": "W1",
            "trackingDetails": {
                "statuses": [
                    {"occurredAt": "2021-01-25T11:35:01.859Z", "code": "DELIVERED"},
                    {"occurredAt": "2021-01-22T11:30:21.092Z", "code": "PENDING"},
                ]
            },
        }
    )

    assert tracking == (
        "DELIVERED",
        datetime(2021, 1, 25, 11, 35, 1, 859000, tzinfo=UTC),
    )


def test_no_tracking_details_is_no_status():
    assert map_tracking({"waybill": "W1"}) is None
    assert map_tracking({"waybill": "W1", "trackingDetails": {"statuses": []}}) is None


# --- the adapter ------------------------------------------------------------


class FakeClient:
    is_configured = True

    def __init__(self, forms, shipments=None, tracking=None, shipments_error=None):
        self.forms = forms
        self.shipments = shipments or {}
        self.tracking = tracking or {}
        self.shipments_error = shipments_error
        self.shipment_calls = []
        self.tracking_calls = []

    def fetch_checkout_forms(self, limit=100, offset=0, bought_since=None, updated_since=None):
        return self.forms

    def fetch_offer_image(self, offer_id):
        return None

    def fetch_shipments(self, order_id):
        self.shipment_calls.append(order_id)
        if self.shipments_error:
            raise self.shipments_error
        return self.shipments.get(order_id, [])

    def fetch_tracking(self, carrier_id, waybills):
        self.tracking_calls.append((carrier_id, list(waybills)))
        return [self.tracking[w] for w in waybills if w in self.tracking]


def _form(external_id, fulfillment):
    return {
        "id": external_id,
        "status": "READY_FOR_PROCESSING",
        "fulfillment": {"status": fulfillment},
        "buyer": {"email": f"{external_id}@example.com"},
        "summary": {"totalToPay": {"amount": "99.00", "currency": "PLN"}},
    }


def _tracking(waybill, code):
    return {
        "waybill": waybill,
        "trackingDetails": {"statuses": [{"occurredAt": "2026-09-20T10:00:00Z", "code": code}]},
    }


def test_only_orders_that_have_left_are_asked_about_their_parcels():
    client = FakeClient(
        [_form("NEW-1", "NEW"), _form("SENT-1", "SENT"), _form("DONE-1", "PICKED_UP")],
        shipments={"SENT-1": [{"id": "S", "waybill": "W1", "carrierId": "DHL"}]},
    )

    orders = {o.external_id: o for o in AllegroAdapter(client=client).fetch_orders()}

    assert client.shipment_calls == ["SENT-1", "DONE-1"]
    assert orders["NEW-1"].shipments is None
    assert [s.waybill for s in orders["SENT-1"].shipments] == ["W1"]
    assert orders["DONE-1"].shipments == []


def test_tracking_is_read_only_for_parcels_on_their_way():
    client = FakeClient(
        [_form("SENT-1", "SENT"), _form("DONE-1", "PICKED_UP")],
        shipments={
            "SENT-1": [{"id": "S1", "waybill": "W1", "carrierId": "DHL"}],
            "DONE-1": [{"id": "S2", "waybill": "W2", "carrierId": "DHL"}],
        },
        tracking={"W1": _tracking("W1", "IN_TRANSIT"), "W2": _tracking("W2", "DELIVERED")},
    )

    orders = {o.external_id: o for o in AllegroAdapter(client=client).fetch_orders()}

    assert client.tracking_calls == [("DHL", ["W1"])]
    assert orders["SENT-1"].shipments[0].tracking_status == "IN_TRANSIT"
    assert orders["DONE-1"].shipments[0].tracking_status is None


def test_a_refused_request_stops_asking_but_still_returns_the_orders():
    client = FakeClient(
        [_form("SENT-1", "SENT"), _form("SENT-2", "SENT")],
        shipments_error=IntegrationAuthError("Allegro denied access to shipments"),
    )

    orders = AllegroAdapter(client=client).fetch_orders()

    assert len(orders) == 2
    assert client.shipment_calls == ["SENT-1"]
    assert all(o.shipments is None for o in orders)


def test_an_order_whose_parcels_failed_to_load_is_still_imported():
    client = FakeClient(
        [_form("SENT-1", "SENT")], shipments_error=IntegrationUnavailable("boom")
    )

    orders = AllegroAdapter(client=client).fetch_orders()

    assert [o.external_id for o in orders] == ["SENT-1"]
    assert orders[0].shipments is None


# --- storing, and refreshing what the carrier says --------------------------


class StoringAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, orders, tracking=None):
        self.orders = orders
        self.tracking = tracking or {}
        self.tracking_asked = []

    def fetch_orders(self, limit=100, offset=0):
        return self.orders

    def fetch_tracking(self, keys):
        self.tracking_asked.append(list(keys))
        return {key: self.tracking[key] for key in keys if key in self.tracking}


def _order(shipments, status=OrderStatus.SHIPPED):
    return OrderCreate(
        external_id="ALG-1",
        source=OrderSource.ALLEGRO,
        status=status,
        customer_email="buyer@example.com",
        total_amount=Decimal("10.00"),
        shipments=shipments,
    )


def _shipment(waybill="W1", **overrides):
    return ShipmentCreate(carrier_id="DHL", waybill=waybill, **overrides)


def _import(session, orders, tracking=None):
    adapter = StoringAdapter(orders, tracking)
    OrderImportService(OrderRepository(session), adapter).import_orders()
    return adapter


def _stored(session):
    return session.query(Order).one()


def test_parcels_are_stored_with_the_order(session):
    _import(session, [_order([_shipment("W1"), _shipment("W2")])])

    assert [s.waybill for s in _stored(session).shipments] == ["W1", "W2"]


def test_an_import_that_could_not_read_parcels_leaves_the_stored_ones(session):
    _import(session, [_order([_shipment("W1")])])

    _import(session, [_order(None)])

    assert [s.waybill for s in _stored(session).shipments] == ["W1"]


def test_an_empty_list_removes_them(session):
    _import(session, [_order([_shipment("W1")])])

    _import(session, [_order([])])

    assert _stored(session).shipments == []


def test_tracking_read_earlier_survives_an_import_that_could_not_read_it(session):
    at = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    _import(session, [_order([_shipment("W1", tracking_status="IN_TRANSIT", tracking_updated_at=at)])])

    _import(session, [_order([_shipment("W1")])])

    assert _stored(session).shipments[0].tracking_status == "IN_TRANSIT"


def test_refreshing_updates_parcels_still_on_their_way_and_only_those(session):
    other = OrderCreate(
        external_id="ALG-2",
        source=OrderSource.ALLEGRO,
        status=OrderStatus.DELIVERED,
        customer_email="b2@example.com",
        total_amount=Decimal("10.00"),
        shipments=[_shipment("W9")],
    )
    _import(session, [_order([_shipment("W1")]), other])
    later = datetime(2026, 9, 21, 8, 0, tzinfo=UTC)
    adapter = StoringAdapter(
        [], tracking={("DHL", "W1"): ("DELIVERED", later), ("DHL", "W9"): ("DELIVERED", later)}
    )

    OrderImportService(OrderRepository(session), adapter)._refresh_tracking()

    assert adapter.tracking_asked == [[("DHL", "W1")]]
    w1 = session.query(OrderShipment).filter_by(waybill="W1").one()
    w9 = session.query(OrderShipment).filter_by(waybill="W9").one()
    assert w1.tracking_status == "DELIVERED"
    assert w9.tracking_status is None


def test_a_delivered_parcel_is_not_asked_about_again(session):
    _import(session, [_order([_shipment("W1", tracking_status="DELIVERED")])])
    adapter = StoringAdapter([])

    OrderImportService(OrderRepository(session), adapter)._refresh_tracking()

    assert adapter.tracking_asked == []


def test_an_old_parcel_is_not_asked_about_forever(session):
    long_ago = datetime.now(UTC) - timedelta(days=90)
    _import(session, [_order([_shipment("W1", shipped_at=long_ago)])])
    adapter = StoringAdapter([])

    OrderImportService(OrderRepository(session), adapter)._refresh_tracking()

    assert adapter.tracking_asked == []


def test_details_default_to_unknown_parcels():
    assert OrderDetails().shipments is None


def test_the_api_shapes_carry_the_parcels(session):
    from app.schemas.order import OrderDetailRead, OrderRead

    _import(session, [_order([_shipment("W1", tracking_status="IN_TRANSIT")])])
    order = _stored(session)

    assert [s.waybill for s in OrderRead.model_validate(order).shipments] == ["W1"]
    detail = OrderDetailRead.from_order(order)
    assert detail.shipments[0].tracking_status == "IN_TRANSIT"
