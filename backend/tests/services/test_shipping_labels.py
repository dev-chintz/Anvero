"""Buying a shipment through Wysyłam z Allegro, against a fake Allegro."""

from decimal import Decimal

import httpx2
import pytest

from app.integrations.allegro.client import AllegroClient
from app.integrations.base import IntegrationUnavailable
from app.models.marketplace_write import WriteOutcome
from app.models.order import (
    AddressType,
    Order,
    OrderAddress,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.models.shipping_label import LabelStatus
from app.schemas.shipping import PackageSize, ShippingSender, ShippingSettings
from app.services.marketplace_writes import set_safe_mode
from app.services.shipping_labels import LabelRefused, ShippingLabels, shipment_input
from app.services.shipping_settings import get_shipping_settings, save_shipping_settings

# `session` comes from tests/conftest.py

SENDER = ShippingSender(
    name="Jan Kowalski",
    company="Pracownia",
    street="Długa 1",
    postal_code="00-001",
    city="Warszawa",
    email="sklep@example.com",
    phone="500600700",
)
PACKAGE = PackageSize(
    length_cm=Decimal(30), width_cm=Decimal(20), height_cm=Decimal(10), weight_kg=Decimal("1.5")
)


class FakeAllegro:
    """Answers like Allegro's shipment-management API is documented to."""

    def __init__(self, outcomes=("SUCCESS",), create_error=None, method_id="method-1"):
        self.outcomes = list(outcomes)
        self.create_error = create_error
        self.method_id = method_id
        self.created = []
        self.cancelled = []
        self.tracking = []
        self.cancel_status = "SUCCESS"

    def fetch_checkout_form(self, checkout_form_id):
        return {"delivery": {"method": {"id": self.method_id}}} if self.method_id else {}

    def create_shipment(self, command_id, shipment):
        if self.create_error:
            raise self.create_error
        self.created.append((command_id, shipment))
        return {"commandId": command_id}

    def shipment_command(self, command_id):
        status = self.outcomes.pop(0) if self.outcomes else "IN_PROGRESS"
        if status == "SUCCESS":
            return {"commandId": command_id, "status": "SUCCESS", "shipmentId": "ship-1"}
        if status == "ERROR":
            return {"status": "ERROR", "errors": [{"userMessage": "Parcel too heavy"}]}
        return {"status": "IN_PROGRESS"}

    def fetch_shipment(self, shipment_id):
        return {"id": shipment_id, "carrier": "INPOST", "packages": [{"waybill": "WB123"}]}

    def cancel_shipment(self, command_id, shipment_id):
        self.cancelled.append(shipment_id)

    def cancel_command(self, command_id):
        return {"status": self.cancel_status}

    def add_shipment(self, checkout_form_id, carrier_id, waybill, carrier_name=None):
        self.tracking.append((checkout_form_id, carrier_id, waybill))
        return {"id": "tracking-1"}

    def fetch_label(self, shipment_ids, page_size="A6"):
        return b"%PDF-1.4 " + ",".join(shipment_ids).encode() + page_size.encode()


def _order(session, payment_type=PaymentType.ONLINE, source=OrderSource.ALLEGRO):
    order = Order(
        external_id="form-1",
        source=source,
        status=OrderStatus.CONFIRMED,
        customer_email="buyer@example.com",
        customer_phone="600700800",
        total_amount=Decimal("10.00"),
        currency="PLN",
        payment_type=payment_type,
        pickup_point_id="WAW01A",
    )
    order.addresses = [
        OrderAddress(
            type=AddressType.DELIVERY,
            first_name="Anna",
            last_name="Nowak",
            street="Krótka 2",
            postal_code="30-001",
            city="Kraków",
            country_code="PL",
        )
    ]
    session.add(order)
    session.commit()
    return order


@pytest.fixture
def ready(session):
    """Safe mode off and a sender saved: a label can really be bought."""
    set_safe_mode(session, False, None)
    save_shipping_settings(session, ShippingSettings(sender=SENDER, default_package=PACKAGE), None)


def _labels(session, allegro):
    return ShippingLabels(session, client_factory=lambda: allegro, sleep=lambda _s: None)


def test_the_settings_are_kept_and_read_back(session):
    save_shipping_settings(session, ShippingSettings(sender=SENDER, default_package=PACKAGE), None)

    stored = get_shipping_settings(session)

    assert stored.sender == SENDER
    assert stored.default_package == PACKAGE

    save_shipping_settings(session, ShippingSettings(), None)
    assert get_shipping_settings(session) == ShippingSettings()


def test_the_shipment_is_addressed_from_the_order_and_the_settings(session):
    order = _order(session)

    shipment = shipment_input(order, "method-1", SENDER, PACKAGE)

    assert shipment["deliveryMethodId"] == "method-1"
    assert shipment["receiver"] == {
        "name": "Anna Nowak",
        "street": "Krótka 2",
        "postalCode": "30-001",
        "city": "Kraków",
        "countryCode": "PL",
        "email": "buyer@example.com",
        "phone": "600700800",
        "point": "WAW01A",
    }
    assert shipment["sender"]["name"] == "Jan Kowalski"
    assert shipment["referenceNumber"].startswith("AN-")
    assert shipment["packages"] == [
        {
            "type": "PACKAGE",
            "length": {"value": 30.0, "unit": "CENTIMETER"},
            "width": {"value": 20.0, "unit": "CENTIMETER"},
            "height": {"value": 10.0, "unit": "CENTIMETER"},
            "weight": {"value": 1.5, "unit": "KILOGRAMS"},
        }
    ]


def test_in_safe_mode_nothing_is_bought(session):
    save_shipping_settings(session, ShippingSettings(sender=SENDER), None)
    allegro = FakeAllegro()
    order = _order(session)

    label, write = _labels(session, allegro).buy(order, PACKAGE, None)

    assert label is None
    assert write.outcome is WriteOutcome.DRY_RUN
    assert write.record.action == "shipment_label"
    assert allegro.created == []
    assert _labels(session, allegro).for_order(order) == []


def test_a_bought_label_has_its_waybill_and_the_order_gets_the_tracking(session, ready):
    allegro = FakeAllegro(outcomes=["IN_PROGRESS", "SUCCESS"])
    order = _order(session)

    label, write = _labels(session, allegro).buy(order, PACKAGE, None)

    assert write.outcome is WriteOutcome.SENT
    assert label.status is LabelStatus.CREATED
    assert (label.shipment_id, label.carrier_id, label.waybill) == ("ship-1", "INPOST", "WB123")
    assert allegro.tracking == [("form-1", "INPOST", "WB123")]
    session.refresh(order)
    assert [s.waybill for s in order.shipments] == ["WB123"]


def test_allegros_refusal_is_kept_on_the_label(session, ready):
    allegro = FakeAllegro(outcomes=["ERROR"])
    order = _order(session)

    label, _ = _labels(session, allegro).buy(order, PACKAGE, None)

    assert label.status is LabelStatus.FAILED
    assert label.error == "Parcel too heavy"
    assert allegro.tracking == []


def test_a_refused_create_command_buys_nothing(session, ready):
    allegro = FakeAllegro(create_error=IntegrationUnavailable("Allegro refused the shipment (422)"))
    order = _order(session)

    label, write = _labels(session, allegro).buy(order, PACKAGE, None)

    assert label is None
    assert write.outcome is WriteOutcome.FAILED


def test_a_slow_shipment_stays_pending_and_is_settled_later(session, ready):
    allegro = FakeAllegro(outcomes=[])
    order = _order(session)
    labels = _labels(session, allegro)

    label, _ = labels.buy(order, PACKAGE, None)
    assert label.status is LabelStatus.PENDING

    allegro.outcomes = ["SUCCESS"]
    labels.refresh(order, label, None)
    assert label.status is LabelStatus.CREATED


def test_a_second_label_is_refused_while_one_stands(session, ready):
    allegro = FakeAllegro()
    order = _order(session)
    labels = _labels(session, allegro)
    labels.buy(order, PACKAGE, None)

    with pytest.raises(LabelRefused, match="already has a label"):
        labels.buy(order, PACKAGE, None)
    assert len(allegro.created) == 1


def test_a_cancelled_label_can_be_bought_again(session, ready):
    allegro = FakeAllegro(outcomes=["SUCCESS", "SUCCESS"])
    order = _order(session)
    labels = _labels(session, allegro)
    label, _ = labels.buy(order, PACKAGE, None)

    write = labels.cancel(order, label, None)

    assert write.outcome is WriteOutcome.SENT
    assert label.status is LabelStatus.CANCELLED
    assert allegro.cancelled == ["ship-1"]
    second, _ = labels.buy(order, PACKAGE, None)
    assert second.status is LabelStatus.CREATED


def test_a_refused_cancellation_leaves_the_label_standing(session, ready):
    allegro = FakeAllegro()
    order = _order(session)
    labels = _labels(session, allegro)
    label, _ = labels.buy(order, PACKAGE, None)
    allegro.cancel_status = "ERROR"

    labels.cancel(order, label, None)

    assert label.status is LabelStatus.CREATED
    assert label.error.startswith("Not cancelled")


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda s: _order(s, source=OrderSource.ERLI), "Allegro orders only"),
        (lambda s: _order(s, payment_type=PaymentType.CASH_ON_DELIVERY), "Cash on delivery"),
    ],
)
def test_orders_it_cannot_serve_are_refused(session, ready, setup, message):
    with pytest.raises(LabelRefused, match=message):
        _labels(session, FakeAllegro()).buy(setup(session), PACKAGE, None)


def test_without_a_sender_nothing_is_asked(session):
    allegro = FakeAllegro()
    with pytest.raises(LabelRefused, match="sender"):
        _labels(session, allegro).buy(_order(session), PACKAGE, None)


def test_an_order_allegro_gives_no_delivery_method_for_is_refused(session, ready):
    with pytest.raises(LabelRefused, match="delivery method"):
        _labels(session, FakeAllegro(method_id=None)).buy(_order(session), PACKAGE, None)


def test_the_label_prints_as_an_a6_pdf(session, ready):
    allegro = FakeAllegro()
    order = _order(session)
    labels = _labels(session, allegro)
    label, _ = labels.buy(order, PACKAGE, None)

    assert labels.pdf(label) == b"%PDF-1.4 ship-1A6"


# --- the client, against Allegro's documented endpoints ---------------------------


def _client(handler):
    return AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        user_agent="Anvero/test",
        api_url="https://api.allegro.test",
        auth_url="https://allegro.test/auth/oauth",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def _token_or(handler):
    def route(request):
        if request.url.path.endswith("/token"):
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        return handler(request)

    return route


def test_the_client_sends_the_create_command():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.read()))
        return httpx2.Response(201, json={"commandId": "c-1"})

    _client(_token_or(handler)).create_shipment("c-1", {"deliveryMethodId": "m"})

    method, path, body = seen[0]
    assert (method, path) == ("POST", "/shipment-management/shipments/create-commands")
    assert b'"commandId":"c-1"' in body.replace(b" ", b"")


def test_the_client_fetches_the_label_as_pdf():
    def handler(request):
        assert request.url.path == "/shipment-management/label"
        assert request.headers["Accept"] == "application/octet-stream"
        return httpx2.Response(200, content=b"%PDF-1.7 label")

    assert _client(_token_or(handler)).fetch_label(["s-1"]) == b"%PDF-1.7 label"


def test_the_client_refuses_a_label_that_is_not_a_pdf():
    def handler(request):
        return httpx2.Response(200, content=b"<html>maintenance</html>")

    with pytest.raises(IntegrationUnavailable, match="not a PDF"):
        _client(_token_or(handler)).fetch_label(["s-1"])


def test_a_403_names_the_shipments_scope():
    def handler(request):
        return httpx2.Response(403)

    with pytest.raises(Exception, match="allegro:api:shipments:write"):
        _client(_token_or(handler)).create_shipment("c-1", {})


# --- printing many at once ---------------------------------------------------------


def _bought(session, allegro, external_id):
    order = _order(session)
    order.external_id = external_id
    session.commit()
    label, _ = _labels(session, allegro).buy(order, PACKAGE, None)
    return label


class NumberedAllegro(FakeAllegro):
    """Gives each shipment its own id, as Allegro would."""

    def __init__(self):
        super().__init__(outcomes=["SUCCESS"] * 10)
        self.count = 0
        self.label_requests = []

    def shipment_command(self, command_id):
        answer = super().shipment_command(command_id)
        if answer.get("status") == "SUCCESS":
            self.count += 1
            answer["shipmentId"] = f"ship-{self.count}"
        return answer

    def fetch_label(self, shipment_ids, page_size="A6"):
        self.label_requests.append((list(shipment_ids), page_size))
        return super().fetch_label(shipment_ids, page_size)


def test_many_labels_come_as_one_pdf_in_the_order_asked(session, ready):
    allegro = NumberedAllegro()
    first = _bought(session, allegro, "form-a")
    second = _bought(session, allegro, "form-b")
    labels = _labels(session, allegro)

    content = labels.pdf_many([second.id, first.id])

    assert content.startswith(b"%PDF")
    assert allegro.label_requests == [(["ship-2", "ship-1"], "A6")]
    assert first.printed_at is not None and second.printed_at is not None


def test_the_print_list_holds_bought_labels_not_yet_printed(session, ready):
    allegro = NumberedAllegro()
    first = _bought(session, allegro, "form-a")
    second = _bought(session, allegro, "form-b")
    labels = _labels(session, allegro)
    assert [label.id for label in labels.printable()] == [first.id, second.id]

    labels.pdf(first)

    assert [label.id for label in labels.printable()] == [second.id]
    assert {label.id for label in labels.printable(unprinted_only=False)} == {first.id, second.id}


def test_a_label_not_bought_cannot_be_printed_with_the_rest(session, ready):
    allegro = NumberedAllegro()
    good = _bought(session, allegro, "form-a")
    cancelled = _bought(session, allegro, "form-b")
    labels = _labels(session, allegro)
    labels.cancel(cancelled.order, cancelled, None)

    with pytest.raises(LabelRefused, match="Only bought labels"):
        labels.pdf_many([good.id, cancelled.id])
    assert good.printed_at is None
    assert allegro.label_requests == []


def test_an_unknown_label_or_too_many_are_refused(session, ready):
    import uuid

    labels = _labels(session, NumberedAllegro())
    with pytest.raises(LookupError):
        labels.pdf_many([uuid.uuid4()])
    with pytest.raises(LabelRefused, match="At most"):
        labels.pdf_many([uuid.uuid4() for _ in range(51)])
