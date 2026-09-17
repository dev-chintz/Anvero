from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations.allegro.mapper import (
    OrderMappingError,
    map_checkout_form,
    map_ordered_at,
    map_status,
)
from app.models.order import OrderSource, OrderStatus


def _checkout_form(**overrides):
    """A checkout form shaped like GET /order/checkout-forms.

    Two units at 76.00 plus 15.00 delivery, so the order is worth 167.00. Each
    of those numbers is distinct on purpose: a test asserting 167.00 fails if
    the mapper reaches for the unit price, the line total or the delivery cost
    instead of the order summary.
    """
    form = {
        "id": "f1e2d3c4-1111-2222-3333-444455556666",
        "status": "READY_FOR_PROCESSING",
        "fulfillment": {"status": "NEW"},
        "buyer": {
            "id": "buyer-1",
            "email": "buyer@example.com",
            "login": "buyer_login",
            "firstName": "Jan",
            "lastName": "Kowalski",
        },
        "payment": {
            "type": "ONLINE",
            "paidAmount": {"amount": "167.00", "currency": "PLN"},
        },
        "delivery": {
            "method": {"id": "m-1", "name": "Kurier"},
            "cost": {"amount": "15.00", "currency": "PLN"},
        },
        "lineItems": [
            {
                "id": "li-1",
                "offer": {"id": "o-1", "name": "Widget"},
                "quantity": 2,
                "price": {"amount": "76.00", "currency": "PLN"},
                "originalPrice": {"amount": "76.00", "currency": "PLN"},
                "boughtAt": "2026-09-14T09:59:00.000Z",
            }
        ],
        "summary": {"totalToPay": {"amount": "167.00", "currency": "PLN"}},
        "updatedAt": "2026-09-14T10:05:00.000Z",
    }
    form.update(overrides)
    return form


def test_maps_the_documented_fields():
    order = map_checkout_form(_checkout_form())

    assert order.source is OrderSource.ALLEGRO
    assert order.external_id == "f1e2d3c4-1111-2222-3333-444455556666"
    assert order.customer_email == "buyer@example.com"
    assert order.currency == "PLN"


def test_total_comes_from_the_order_summary():
    """Not the unit price (76.00), the line total (152.00) or delivery (15.00)."""
    order = map_checkout_form(_checkout_form())

    assert order.total_amount == Decimal("167.00")


def test_ordered_at_is_the_purchase_time_not_the_import_time():
    order = map_checkout_form(_checkout_form())

    assert order.ordered_at == datetime(2026, 9, 14, 9, 59, tzinfo=UTC)


def test_ordered_at_is_the_earliest_line_item_in_utc():
    """Items can carry different offsets; the earliest instant wins."""
    form = _checkout_form(
        lineItems=[
            {"boughtAt": "2026-09-14T09:59:00.000Z"},
            # 11:00 in +02:00 is 09:00 UTC, one minute earlier than the first
            {"boughtAt": "2026-09-14T11:00:00+02:00"},
        ]
    )

    assert map_ordered_at(form) == datetime(2026, 9, 14, 9, 0, tzinfo=UTC)


def test_missing_purchase_time_still_imports_the_order():
    """A wrong date can be fixed later; a dropped order cannot."""
    form = _checkout_form(lineItems=[{"id": "li-1"}])

    order = map_checkout_form(form)

    assert order.ordered_at is None
    assert order.external_id == form["id"]


def test_unreadable_purchase_time_is_ignored_not_fatal():
    form = _checkout_form(lineItems=[{"boughtAt": "yesterday-ish"}])

    assert map_ordered_at(form) is None


def test_cancellation_outranks_fulfillment():
    """A cancelled order is cancelled whatever its parcel is doing."""
    form = _checkout_form(status="CANCELLED", fulfillment={"status": "SENT"})

    assert map_status(form) is OrderStatus.CANCELLED


@pytest.mark.parametrize(
    ("fulfillment_status", "expected"),
    [
        ("NEW", OrderStatus.NEW),
        ("PROCESSING", OrderStatus.CONFIRMED),
        ("READY_FOR_SHIPMENT", OrderStatus.CONFIRMED),
        ("SENT", OrderStatus.SHIPPED),
        ("READY_FOR_PICKUP", OrderStatus.SHIPPED),
        ("PICKED_UP", OrderStatus.DELIVERED),
    ],
)
def test_fulfillment_status_mapping(fulfillment_status, expected):
    form = _checkout_form(fulfillment={"status": fulfillment_status})

    assert map_status(form) is expected


@pytest.mark.parametrize(
    ("checkout_status", "expected"),
    [
        ("BOUGHT", OrderStatus.NEW),
        ("FILLED_IN", OrderStatus.NEW),
        ("READY_FOR_PROCESSING", OrderStatus.CONFIRMED),
    ],
)
def test_falls_back_to_checkout_status_without_fulfillment(checkout_status, expected):
    """fulfillment is absent until handling starts."""
    form = _checkout_form(status=checkout_status)
    form.pop("fulfillment")

    assert map_status(form) is expected


def test_unknown_fulfillment_status_is_treated_as_new_work():
    """Allegro adds statuses; an unrecognised one must not vanish."""
    form = _checkout_form(status="BOUGHT", fulfillment={"status": "SOMETHING_NEW"})

    assert map_status(form) is OrderStatus.NEW


def test_rejects_a_form_without_a_buyer_email():
    form = _checkout_form(buyer={"id": "b-1", "guest": True})

    with pytest.raises(OrderMappingError, match="buyer email"):
        map_checkout_form(form)


def test_rejects_a_form_without_a_summary():
    form = _checkout_form()
    form.pop("summary")

    with pytest.raises(OrderMappingError, match="totalToPay"):
        map_checkout_form(form)


def test_rejects_a_non_positive_total():
    form = _checkout_form(summary={"totalToPay": {"amount": "0.00", "currency": "PLN"}})

    with pytest.raises(OrderMappingError, match="non-positive"):
        map_checkout_form(form)


def test_a_domain_validation_failure_becomes_a_mapping_error():
    """OrderCreate's own rules must surface as OrderMappingError.

    Regression: pydantic's ValidationError escaped the adapter's per-order
    skip, so one bad email lost every other order on the page.
    """
    form = _checkout_form(buyer={"email": "buyer_at_example.com"})

    with pytest.raises(OrderMappingError, match="customer_email") as excinfo:
        map_checkout_form(form)

    # the message ends up in logs, so it must name the field, not the value
    assert "buyer_at_example.com" not in str(excinfo.value)


def test_an_amount_with_too_many_decimals_becomes_a_mapping_error():
    form = _checkout_form(
        summary={"totalToPay": {"amount": "167.005", "currency": "PLN"}}
    )

    with pytest.raises(OrderMappingError, match="total_amount"):
        map_checkout_form(form)


def test_rejects_an_unreadable_amount():
    form = _checkout_form(
        summary={"totalToPay": {"amount": "not a number", "currency": "PLN"}}
    )

    with pytest.raises(OrderMappingError, match="unreadable"):
        map_checkout_form(form)
