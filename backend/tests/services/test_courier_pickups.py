"""Ordering a courier through Wysyłam z Allegro, against a fake Allegro."""

import uuid
from datetime import timedelta

import pytest

from app.models.courier_pickup import PickupStatus
from app.models.marketplace_write import WriteOutcome
from app.schemas.shipping import ShippingSettings
from app.services.courier_pickups import (
    CourierPickups,
    business_today,
    proposal_options,
)
from app.services.marketplace_writes import set_safe_mode
from app.services.shipping_labels import LabelRefused
from app.services.shipping_settings import save_shipping_settings
from tests.services.test_shipping_labels import (
    SENDER,
    NumberedAllegro,
    _bought,
    _labels,
)

# `session` comes from tests/conftest.py

PROPOSALS = {
    "proposals": [
        {
            "shipmentIds": ["ship-1"],
            "proposals": [
                {
                    "proposalId": "day-1",
                    "name": "2026-09-25",
                    "proposalItems": [
                        {"id": "slot-a", "name": "09:00-12:00"},
                        {"id": "slot-b", "name": "12:00-15:00"},
                    ],
                }
            ],
        }
    ]
}


class PickupAllegro(NumberedAllegro):
    def __init__(self, pickup_outcomes=("SUCCESS",)):
        super().__init__()
        self.pickup_outcomes = list(pickup_outcomes)
        self.asked = []
        self.pickups = []

    def pickup_proposals(self, shipment_ids, ready_date):
        self.asked.append((list(shipment_ids), ready_date))
        return PROPOSALS

    def create_pickup(self, command_id, shipment_ids, proposal_id):
        self.pickups.append((list(shipment_ids), proposal_id))

    def pickup_command(self, command_id):
        status = self.pickup_outcomes.pop(0) if self.pickup_outcomes else "IN_PROGRESS"
        if status == "SUCCESS":
            return {"status": "SUCCESS", "pickupId": "pickup-1"}
        if status == "ERROR":
            return {"status": "ERROR", "errors": [{"userMessage": "No courier that day"}]}
        return {"status": "IN_PROGRESS"}


@pytest.fixture
def ready(session):
    """Safe mode off and a sender saved: parcels can be bought and collected."""
    set_safe_mode(session, False, None)
    save_shipping_settings(session, ShippingSettings(sender=SENDER), None)


def _pickups(session, allegro):
    return CourierPickups(session, client_factory=lambda: allegro, sleep=lambda _s: None)


def _two_parcels(session, allegro):
    return _bought(session, allegro, "form-a"), _bought(session, allegro, "form-b")


TODAY = business_today()


def test_proposals_are_read_as_slots_in_either_shape():
    assert [(o.id, o.label) for o in proposal_options(PROPOSALS)] == [
        ("slot-a", "2026-09-25 09:00-12:00"),
        ("slot-b", "2026-09-25 12:00-15:00"),
    ]
    flat = {"proposals": [{"proposals": [{"id": "p-1", "date": "2026-09-25"}]}]}
    assert [(o.id, o.label) for o in proposal_options(flat)] == [("p-1", "2026-09-25")]
    assert proposal_options({}) == []


def test_the_slots_are_asked_for_the_chosen_parcels_and_day(session, ready):
    allegro = PickupAllegro()
    first, second = _two_parcels(session, allegro)

    options = _pickups(session, allegro).proposals([first.id, second.id], TODAY)

    assert [o.id for o in options] == ["slot-a", "slot-b"]
    assert allegro.asked == [(["ship-1", "ship-2"], TODAY.isoformat())]


def test_an_ordered_courier_is_kept_with_its_parcels(session, ready):
    allegro = PickupAllegro(pickup_outcomes=["IN_PROGRESS", "SUCCESS"])
    first, second = _two_parcels(session, allegro)

    pickup, write = _pickups(session, allegro).order(
        [first.id, second.id], TODAY, "slot-a", "2026-09-25 09:00-12:00", None
    )

    assert write.outcome is WriteOutcome.SENT
    assert write.record.action == "courier_pickup"
    assert pickup.status is PickupStatus.ORDERED
    assert (pickup.pickup_id, pickup.carrier_id) == ("pickup-1", "INPOST")
    assert allegro.pickups == [(["ship-1", "ship-2"], "slot-a")]
    assert first.pickup_id == pickup.id and second.pickup_id == pickup.id
    # no longer waiting for a courier
    assert _labels(session, allegro).printable("no_pickup") == []


def test_in_safe_mode_no_courier_is_ordered(session, ready):
    allegro = PickupAllegro()
    first, _ = _two_parcels(session, allegro)
    set_safe_mode(session, True, None)

    pickup, write = _pickups(session, allegro).order([first.id], TODAY, "slot-a", "slot", None)

    assert pickup is None
    assert write.outcome is WriteOutcome.DRY_RUN
    assert allegro.pickups == []
    assert first.pickup_id is None


def test_a_refused_pickup_frees_its_parcels(session, ready):
    allegro = PickupAllegro(pickup_outcomes=["ERROR"])
    first, _ = _two_parcels(session, allegro)

    pickup, _ = _pickups(session, allegro).order([first.id], TODAY, "slot-a", "slot", None)

    assert pickup.status is PickupStatus.FAILED
    assert pickup.error == "No courier that day"
    session.refresh(first)
    assert first.pickup_id is None


def test_a_slow_pickup_stays_pending_and_is_settled_later(session, ready):
    allegro = PickupAllegro(pickup_outcomes=[])
    first, _ = _two_parcels(session, allegro)
    pickups = _pickups(session, allegro)

    pickup, _ = pickups.order([first.id], TODAY, "slot-a", "slot", None)
    assert pickup.status is PickupStatus.PENDING

    allegro.pickup_outcomes = ["SUCCESS"]
    pickups.refresh(pickup)
    assert pickup.status is PickupStatus.ORDERED


def test_a_parcel_is_not_collected_twice(session, ready):
    allegro = PickupAllegro()
    first, second = _two_parcels(session, allegro)
    pickups = _pickups(session, allegro)
    pickups.order([first.id], TODAY, "slot-a", "slot", None)

    with pytest.raises(LabelRefused, match="already ordered"):
        pickups.order([first.id, second.id], TODAY, "slot-a", "slot", None)


def test_one_pickup_serves_one_carrier(session, ready):
    allegro = PickupAllegro()
    first, second = _two_parcels(session, allegro)
    second.carrier_id = "DPD"
    session.commit()

    with pytest.raises(LabelRefused, match="one carrier"):
        _pickups(session, allegro).proposals([first.id, second.id], TODAY)


def test_a_day_already_past_is_refused(session, ready):
    allegro = PickupAllegro()
    first, _ = _two_parcels(session, allegro)

    with pytest.raises(LabelRefused, match="past"):
        _pickups(session, allegro).proposals([first.id], TODAY - timedelta(days=1))


def test_a_cancelled_or_unknown_parcel_is_refused(session, ready):
    allegro = PickupAllegro()
    first, second = _two_parcels(session, allegro)
    _labels(session, allegro).cancel(second.order, second, None)
    pickups = _pickups(session, allegro)

    with pytest.raises(LabelRefused, match="Only bought parcels"):
        pickups.proposals([first.id, second.id], TODAY)
    with pytest.raises(LookupError):
        pickups.proposals([uuid.uuid4()], TODAY)
