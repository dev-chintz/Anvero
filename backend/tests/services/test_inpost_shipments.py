"""Making parcel locker shipments at InPost from Anvero: which orders are refused, what
is asked of InPost, how the number is waited for and where it goes. InPost is a fake."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import pytest

from app.integrations.base import IntegrationUnavailable
from app.models.inpost_shipment import InpostShipment
from app.models.marketplace_write import MarketplaceWrite, WriteOutcome
from app.models.order import (
    AddressType,
    Order,
    OrderAddress,
    OrderShipment,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.repositories.order_repository import OrderRepository
from app.services import inpost_settings, inpost_shipments
from app.services.inpost_shipments import (
    InpostRefused,
    InpostShipments,
    receiver_of,
    refusal,
    shipment_input,
)
from app.services.marketplace_writes import set_safe_mode


class FakeInpost:
    """Answers the way InPost does: a shipment is accepted at once, and gets its
    number a few looks later."""

    def __init__(self, numbers_after=1, create_error=None):
        self.numbers_after = numbers_after
        self.create_error = create_error
        self.created = []
        self.looks = 0
        self.seen = {}
        self.cancelled = []
        self.labels_asked = []
        self._next_id = 4242

    def create_shipment(self, payload):
        if self.create_error:
            raise self.create_error
        self.created.append(payload)
        self._next_id += 1
        return {"id": self._next_id, "status": "created", "tracking_number": None}

    def get_shipment(self, shipment_id):
        self.looks += 1
        # a shipment gets its number at its own Nth look
        seen = self.seen[shipment_id] = self.seen.get(shipment_id, 0) + 1
        if seen >= self.numbers_after:
            return {"id": shipment_id, "status": "confirmed", "tracking_number": f"620000000000000{str(shipment_id).zfill(9)}"}
        return {"id": shipment_id, "status": "offer_selected", "tracking_number": None}

    def cancel_shipment(self, shipment_id):
        self.cancelled.append(shipment_id)

    def fetch_labels(self, shipment_ids, label_type="A6"):
        self.labels_asked.append((list(shipment_ids), label_type))
        return b"%PDF-1.4 labels"


class StubOrderWrites:
    """Stands for the tracking number going to Allegro: it is stored on the order
    and the call is noted, and nothing leaves the test."""

    calls: ClassVar[list] = []

    def __init__(self, db):
        self.db = db

    def add_shipment(self, order, carrier_id, carrier_name, waybill, user_id):
        StubOrderWrites.calls.append((order.id, carrier_id, carrier_name, waybill, user_id))
        return OrderRepository(self.db).add_shipment(order, carrier_id, carrier_name, waybill), None


@pytest.fixture(autouse=True)
def _quick_and_quiet(monkeypatch):
    monkeypatch.setattr(inpost_shipments, "SETTLE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(inpost_shipments, "OrderWrites", StubOrderWrites)
    StubOrderWrites.calls = []


def _order(session, **overrides):
    fields = {
        "external_id": f"ALG-{overrides.pop('tag', 'A')}",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.CONFIRMED,
        "customer_email": "buyer@user.allegromail.pl",
        "customer_first_name": "Anna",
        "customer_last_name": "Nowak",
        "total_amount": Decimal("45.00"),
        "currency": "PLN",
        "delivery_method": "Allegro Paczkomaty InPost",
        "pickup_point_id": "KRA010",
        "pickup_point_name": "Paczkomat KRA010",
        "payment_type": PaymentType.ONLINE,
        "paid_amount": Decimal("45.00"),
    }
    fields.update(overrides)
    order = Order(**fields)
    order.addresses.append(
        OrderAddress(
            type=AddressType.DELIVERY, first_name="Anna", last_name="Nowak", phone="+48 600-100-200"
        )
    )
    session.add(order)
    session.commit()
    return order


def _configure(session, template="small"):
    inpost_settings.save_settings(session, "token-1234567890", "777", "sandbox", template, None)


def _service(session, fake=None):
    fake = fake or FakeInpost()
    return InpostShipments(session, client_factory=lambda: fake), fake


def _sending(session):
    """Safe mode off, so a write is sent (to the fake)."""
    set_safe_mode(session, False, None)


# --- who the parcel is for -----------------------------------------------------------


def test_the_receiver_is_read_from_the_delivery_address_with_a_nine_digit_phone(session):
    order = _order(session)

    assert receiver_of(order) == {
        "first_name": "Anna",
        "last_name": "Nowak",
        "email": "buyer@user.allegromail.pl",
        "phone": "600100200",
    }


@pytest.mark.parametrize(
    ("typed", "expected"),
    [("600 100 200", "600100200"), ("+48600100200", "600100200"), ("48 600-100-200", "600100200"), ("600100200", "600100200")],
)
def test_a_phone_number_is_reduced_to_nine_digits(session, typed, expected):
    order = _order(session)
    order.addresses[0].phone = typed

    assert receiver_of(order)["phone"] == expected


def test_without_a_name_on_the_address_the_buyers_is_used(session):
    order = _order(session)
    order.addresses[0].first_name = None
    order.addresses[0].last_name = None

    receiver = receiver_of(order)

    assert (receiver["first_name"], receiver["last_name"]) == ("Anna", "Nowak")


def test_what_is_asked_of_inpost_is_a_service_a_size_and_a_locker(session):
    order = _order(session)

    payload = shipment_input(order, "medium")

    assert payload["service"] == "inpost_locker_standard"
    assert payload["parcels"] == {"template": "medium"}
    assert payload["custom_attributes"] == {"target_point": "KRA010"}
    assert payload["reference"].startswith("AN-")
    assert payload["receiver"]["phone"] == "600100200"


# --- which orders are refused -----------------------------------------------------------


def test_an_ordinary_locker_order_can_have_a_parcel(session):
    assert refusal(_order(session), []) is None


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"marketplace_cancelled_at": datetime(2026, 9, 1, tzinfo=UTC)}, "cancelled"),
        ({"status": OrderStatus.CANCELLED}, "cancelled"),
        ({"payment_type": PaymentType.CASH_ON_DELIVERY}, "Cash on delivery"),
        ({"pickup_point_id": None}, "not a delivery to an InPost parcel locker"),
        ({"delivery_method": "Allegro Automat ORLEN Paczka"}, "not a delivery to an InPost parcel locker"),
        ({"delivery_method": "ERLI InPost Kurier", "pickup_point_id": None}, "courier delivery"),
        ({"deleted_at": datetime(2026, 9, 1, tzinfo=UTC)}, "deleted"),
    ],
)
def test_an_order_that_should_not_get_a_parcel_is_refused_with_a_reason(session, overrides, fragment):
    order = _order(session, **overrides)

    assert fragment in (refusal(order, []) or "")


def test_an_order_with_a_tracking_number_from_elsewhere_is_refused(session):
    order = _order(session)
    order.shipments.append(OrderShipment(position=0, carrier_id="INPOST", waybill="620000000000000000000099"))
    session.commit()

    assert "620000000000000000000099" in (refusal(order, []) or "")


def test_an_order_with_a_parcel_at_inpost_is_refused_unless_it_was_cancelled(session):
    order = _order(session)
    made = InpostShipment(
        order_id=order.id, created_at=datetime.now(UTC), inpost_id="1", status="confirmed",
        target_point="KRA010", template="small",
    )

    assert "already has an InPost shipment" in (refusal(order, [made]) or "")
    made.status = "cancelled"
    assert refusal(order, [made]) is None


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"phone": None}, "phone number"),
        ({"phone": "12345"}, "nine-digit"),
    ],
)
def test_a_missing_or_bad_phone_number_is_named(session, changes, fragment):
    order = _order(session)
    order.addresses[0].phone = changes["phone"]

    assert fragment in (refusal(order, []) or "")


def test_a_missing_name_and_email_are_all_named_at_once(session):
    order = _order(session, customer_first_name=None, customer_last_name=None, customer_email="")
    order.addresses[0].first_name = None
    order.addresses[0].last_name = None

    reason = refusal(order, []) or ""

    assert "first name" in reason and "last name" in reason and "e-mail" in reason


# --- making one ---------------------------------------------------------------------------


def test_without_settings_nothing_is_asked(session):
    service, fake = _service(session)

    with pytest.raises(InpostRefused, match="Settings"):
        service.create(_order(session), None, None)

    assert fake.created == []


def test_in_safe_mode_the_request_is_only_recorded(session):
    _configure(session)
    order = _order(session)
    service, fake = _service(session)

    outcome = service.create(order, None, user_id=None)

    assert outcome.shipment is None
    assert outcome.write.outcome is WriteOutcome.DRY_RUN
    assert fake.created == []
    assert session.query(InpostShipment).count() == 0
    record = session.query(MarketplaceWrite).filter_by(action="inpost_shipment").one()
    assert '"target_point": "KRA010"' in record.payload


def test_a_shipment_is_made_and_its_number_waited_for_and_put_on_the_order(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, fake = _service(session, FakeInpost(numbers_after=3))

    outcome = service.create(order, None, user_id=None)

    shipment = outcome.shipment
    assert shipment is not None
    assert fake.created[0]["parcels"] == {"template": "small"}
    assert (shipment.status, shipment.target_point, shipment.template) == ("confirmed", "KRA010", "small")
    assert shipment.tracking_number and shipment.tracking_number.startswith("62000000")
    assert fake.looks == 3
    # the number is on the order as an InPost parcel, and handed to Allegro
    assert [(s.carrier_id, s.waybill) for s in order.shipments] == [("INPOST", shipment.tracking_number)]
    assert [call[1:4] for call in StubOrderWrites.calls] == [("INPOST", None, shipment.tracking_number)]


def test_the_size_asked_for_beats_the_one_in_settings(session):
    _configure(session, template="small")
    _sending(session)
    service, fake = _service(session)

    service.create(_order(session), "large", None)

    assert fake.created[0]["parcels"] == {"template": "large"}


def test_settings_decide_the_size_when_none_is_asked_for(session):
    _configure(session, template="medium")
    _sending(session)
    service, fake = _service(session)

    outcome = service.create(_order(session), None, None)

    assert fake.created[0]["parcels"] == {"template": "medium"}
    assert outcome.shipment.template == "medium"


def test_a_number_that_is_slow_leaves_the_shipment_for_a_later_look(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, fake = _service(session, FakeInpost(numbers_after=1000))

    outcome = service.create(order, None, None)

    assert outcome.shipment is not None
    assert outcome.shipment.tracking_number is None
    assert outcome.shipment.status == "offer_selected"
    assert order.shipments == []
    assert fake.looks == inpost_shipments.SETTLE_ATTEMPTS

    fake.numbers_after = 1
    service.refresh(order, outcome.shipment, None)

    assert outcome.shipment.tracking_number is not None
    assert outcome.shipment.status == "confirmed"
    assert [s.waybill for s in order.shipments] == [outcome.shipment.tracking_number]


def test_refreshing_twice_puts_the_number_on_the_order_once(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, _ = _service(session)
    shipment = service.create(order, None, None).shipment

    service.refresh(order, shipment, None)
    service.refresh(order, shipment, None)

    assert len(order.shipments) == 1
    assert len(StubOrderWrites.calls) == 1


def test_inposts_refusal_is_recorded_and_no_shipment_is_kept(session):
    _configure(session)
    _sending(session)
    service, _ = _service(
        session, FakeInpost(create_error=IntegrationUnavailable("InPost returned 400: receiver phone invalid"))
    )

    outcome = service.create(_order(session), None, None)

    assert outcome.shipment is None
    assert outcome.write.outcome is WriteOutcome.FAILED
    assert "phone invalid" in (outcome.write.record.detail or "")
    assert session.query(InpostShipment).count() == 0


def test_a_second_parcel_is_refused_while_one_stands(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, fake = _service(session)
    service.create(order, None, None)
    order.shipments.clear()
    session.commit()

    with pytest.raises(InpostRefused, match="already has an InPost shipment"):
        service.create(order, None, None)

    assert len(fake.created) == 1


# --- cancelling ---------------------------------------------------------------------------------


def test_a_shipment_is_cancelled_at_inpost(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, fake = _service(session)
    shipment = service.create(order, None, None).shipment

    result = service.cancel(order, shipment, None)

    assert result.outcome is WriteOutcome.SENT
    assert fake.cancelled == [shipment.inpost_id]
    assert shipment.status == "cancelled"


def test_cancelling_in_safe_mode_changes_nothing(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, fake = _service(session)
    shipment = service.create(order, None, None).shipment
    set_safe_mode(session, True, None)

    result = service.cancel(order, shipment, None)

    assert result.outcome is WriteOutcome.DRY_RUN
    assert fake.cancelled == []
    assert shipment.status == "confirmed"


def test_a_cancelled_shipment_cannot_be_cancelled_again(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, _ = _service(session)
    shipment = service.create(order, None, None).shipment
    service.cancel(order, shipment, None)

    with pytest.raises(InpostRefused, match="already cancelled"):
        service.cancel(order, shipment, None)


def test_a_cancelled_shipment_lets_the_order_have_another(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, fake = _service(session)
    first = service.create(order, None, None).shipment
    service.cancel(order, first, None)
    order.shipments.clear()
    session.commit()

    second = service.create(order, None, None).shipment

    assert second is not None and second.id != first.id
    assert len(fake.created) == 2


def test_inposts_failure_to_cancel_is_kept_on_the_shipment(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    fake = FakeInpost()
    service, _ = _service(session, fake)
    shipment = service.create(order, None, None).shipment

    def refuse(_):
        raise IntegrationUnavailable("InPost returned 422: too late")

    fake.cancel_shipment = refuse
    result = service.cancel(order, shipment, None)

    assert result.outcome is WriteOutcome.FAILED
    assert shipment.status == "confirmed"
    assert "too late" in (shipment.error or "")


# --- the labels -------------------------------------------------------------------------------------


def _made(session, count=2):
    _configure(session)
    _sending(session)
    service, fake = _service(session)
    shipments = [
        service.create(_order(session, tag=str(i)), None, None).shipment for i in range(count)
    ]
    return service, fake, shipments


def test_labels_are_fetched_together_in_the_order_asked_and_noted_printed(session):
    service, fake, (first, second) = _made(session)

    pdf = service.pdf_many([second.id, first.id])

    assert pdf.startswith(b"%PDF")
    assert fake.labels_asked == [([second.inpost_id, first.inpost_id], "A6")]
    assert first.printed_at is not None and second.printed_at is not None


def test_a_label_asked_for_twice_is_fetched_once(session):
    service, fake, (first, _) = _made(session)

    service.pdf_many([first.id, first.id])

    assert fake.labels_asked == [([first.inpost_id], "A6")]


def test_nothing_is_noted_printed_when_the_labels_could_not_be_fetched(session):
    service, fake, (first, _) = _made(session)

    def fail(*args, **kwargs):
        raise IntegrationUnavailable("InPost is slow")

    fake.fetch_labels = fail
    with pytest.raises(IntegrationUnavailable):
        service.pdf_many([first.id])

    assert first.printed_at is None


def test_a_shipment_without_a_number_or_a_cancelled_one_has_no_label(session):
    service, fake, (first, second) = _made(session)
    first.tracking_number = None
    second.status = "cancelled"
    session.commit()

    with pytest.raises(InpostRefused):
        service.pdf_many([first.id])
    with pytest.raises(InpostRefused):
        service.pdf_many([second.id])
    assert fake.labels_asked == []


def test_an_unknown_shipment_is_not_found_and_no_choice_is_refused(session):
    service, _, _ = _made(session, count=1)

    with pytest.raises(LookupError):
        service.pdf_many([__import__("uuid").uuid4()])
    with pytest.raises(InpostRefused):
        service.pdf_many([])


def test_the_labels_to_print_are_those_with_a_number_not_yet_printed_oldest_first(session):
    service, _, (first, second) = _made(session)
    third = service.create(_order(session, tag="9"), None, None).shipment
    service.pdf_many([second.id])
    third.tracking_number = None
    session.commit()

    assert [s.id for s in service.printable()] == [first.id]
    assert [s.id for s in service.printable(printed=True)] == [second.id]
    assert {s.id for s in service.printable(printed=None)} == {first.id, second.id}


# --- many at once ---------------------------------------------------------------------------------------


def test_a_batch_makes_a_parcel_for_each_order_and_waits_for_the_numbers_together(session):
    _configure(session)
    _sending(session)
    orders = [_order(session, tag=str(i)) for i in range(3)]
    service, fake = _service(session, FakeInpost(numbers_after=2))

    outcomes = service.create_many(orders, "small", None)

    assert [o.outcome for o in outcomes] == ["created", "created", "created"]
    assert all(o.shipment.tracking_number for o in outcomes)
    assert all(len(o.order.shipments) == 1 for o in outcomes)
    # every order is asked about in each round, not one after the other: two rounds, not six
    assert fake.looks == 6
    assert len(fake.created) == 3


def test_in_a_batch_one_refusal_does_not_stop_the_others(session):
    _configure(session)
    _sending(session)
    fine = _order(session, tag="1")
    orlen = _order(session, tag="2", delivery_method="Allegro Automat ORLEN Paczka")
    also_fine = _order(session, tag="3")
    service, fake = _service(session)

    outcomes = service.create_many([fine, orlen, also_fine], None, None)

    assert [o.outcome for o in outcomes] == ["created", "refused", "created"]
    assert "not a delivery to an InPost parcel locker" in (outcomes[1].message or "")
    assert len(fake.created) == 2


def test_a_batch_in_safe_mode_is_held_back_without_a_message(session):
    _configure(session)
    orders = [_order(session, tag=str(i)) for i in range(2)]
    service, fake = _service(session)

    outcomes = service.create_many(orders, None, None)

    assert [o.outcome for o in outcomes] == ["held_back", "held_back"]
    assert fake.created == []


def test_a_batch_reports_inposts_refusal_as_a_failure_with_its_words(session):
    _configure(session)
    _sending(session)
    service, _ = _service(
        session, FakeInpost(create_error=IntegrationUnavailable("InPost returned 400: bad locker"))
    )

    (outcome,) = service.create_many([_order(session)], None, None)

    assert outcome.outcome == "failed"
    assert "bad locker" in (outcome.message or "")


# --- the orders waiting for a parcel -----------------------------------------------------------------------


def test_the_orders_awaiting_a_parcel_are_the_open_inpost_locker_ones_with_no_number(session):
    wanted = _order(session, tag="wanted")
    _order(session, tag="orlen", delivery_method="Allegro Automat ORLEN Paczka")
    _order(session, tag="shipped", status=OrderStatus.SHIPPED)
    _order(session, tag="cancelled", marketplace_cancelled_at=datetime(2026, 9, 1, tzinfo=UTC))
    _order(session, tag="cod", payment_type=PaymentType.CASH_ON_DELIVERY)
    _order(session, tag="deleted", deleted_at=datetime(2026, 9, 1, tzinfo=UTC))
    elsewhere = _order(session, tag="elsewhere")
    elsewhere.shipments.append(OrderShipment(position=0, carrier_id="INPOST", waybill="620000000000000000000098"))
    session.commit()
    service, _ = _service(session)

    assert [o.id for o in service.awaiting_parcel()] == [wanted.id]


def test_an_order_with_a_parcel_at_inpost_is_no_longer_awaiting_one(session):
    _configure(session)
    _sending(session)
    order = _order(session)
    service, _ = _service(session)
    shipment = service.create(order, None, None).shipment
    order.shipments.clear()
    session.commit()
    assert service.awaiting_parcel() == []

    service.cancel(order, shipment, None)

    assert [o.id for o in service.awaiting_parcel()] == [order.id]
