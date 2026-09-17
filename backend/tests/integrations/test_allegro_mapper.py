import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations.allegro.mapper import (
    OrderMappingError,
    map_checkout_form,
    map_details,
    map_ordered_at,
    map_status,
    map_status_label,
)
from app.models.order import OrderSource, OrderStatus, PaymentType
from app.schemas.order import BUYER_MESSAGE_MAX_LENGTH


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
        "messageToSeller": "Please pack it well",
        "buyer": {
            "id": "buyer-1",
            "email": "buyer@example.com",
            "login": "buyer_login",
            "firstName": "Jan",
            "lastName": "Kowalski",
            "companyName": "Kowalski Sp. z o.o.",
            "guest": False,
            "phoneNumber": "+48 600 100 200",
        },
        "payment": {
            "id": "p-1",
            "type": "ONLINE",
            "provider": "P24",
            "finishedAt": "2026-09-14T10:01:00.000Z",
            "paidAmount": {"amount": "167.00", "currency": "PLN"},
        },
        "delivery": {
            "address": {
                "firstName": "Anna",
                "lastName": "Nowak",
                "street": "Prosta 1",
                "city": "Warszawa",
                "zipCode": "00-001",
                "countryCode": "PL",
                "phoneNumber": "+48 600 300 400",
            },
            "method": {"id": "m-1", "name": "Kurier"},
            "cost": {"amount": "15.00", "currency": "PLN"},
        },
        "invoice": {
            "required": True,
            "address": {
                "street": "Firmowa 2",
                "city": "Kraków",
                "zipCode": "30-001",
                "countryCode": "PL",
                "company": {
                    "name": "Kowalski Sp. z o.o.",
                    "ids": [{"type": "PL_NIP", "value": "1234563218"}],
                    "vatPayerStatus": "ACTIVE",
                },
            },
        },
        "lineItems": [
            {
                "id": "li-1",
                "offer": {"id": "o-1", "name": "Widget", "external": {"id": "SKU-W1"}},
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


@pytest.mark.parametrize(
    ("form_kwargs", "expected"),
    [
        ({"fulfillment": {"status": "READY_FOR_SHIPMENT"}}, "READY_FOR_SHIPMENT"),
        ({"fulfillment": {"status": "PROCESSING"}}, "PROCESSING"),
        # Allegro adds statuses; the label passes them through untranslated
        ({"fulfillment": {"status": "SOMETHING_NEW"}}, "SOMETHING_NEW"),
    ],
)
def test_the_label_keeps_allegros_own_status(form_kwargs, expected):
    """PROCESSING and READY_FOR_SHIPMENT are both CONFIRMED in Anvero, so
    only the label tells the operator which one Allegro means."""
    form = _checkout_form(status="READY_FOR_PROCESSING", **form_kwargs)

    assert map_status_label(form) == expected
    assert map_status(form) is OrderStatus.CONFIRMED


def test_the_label_falls_back_to_the_checkout_status():
    form = _checkout_form(status="BOUGHT")
    form.pop("fulfillment")

    assert map_status_label(form) == "BOUGHT"


def test_a_cancelled_order_is_labelled_cancelled():
    form = _checkout_form(status="CANCELLED", fulfillment={"status": "PROCESSING"})

    assert map_status_label(form) == "CANCELLED"


def test_no_label_when_allegro_reports_no_status():
    form = _checkout_form()
    form.pop("fulfillment")
    form.pop("status")

    assert map_status_label(form) is None


def test_an_over_long_label_is_shortened_to_what_the_column_holds():
    form = _checkout_form(fulfillment={"status": "X" * 200})

    assert len(map_status_label(form)) == 64


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


# --- order details ---------------------------------------------------------


def test_maps_the_buyer():
    customer = map_checkout_form(_checkout_form()).customer

    assert customer.login == "buyer_login"
    assert (customer.first_name, customer.last_name) == ("Jan", "Kowalski")
    assert customer.company_name == "Kowalski Sp. z o.o."
    assert customer.phone == "+48 600 100 200"


def test_maps_line_items():
    (item,) = map_checkout_form(_checkout_form()).items

    assert item.external_id == "li-1"
    assert item.offer_id == "o-1"
    assert item.sku == "SKU-W1"
    assert item.name == "Widget"
    assert item.quantity == 2
    assert item.unit_price == Decimal("76.00")


def test_unit_price_is_after_discounts_not_the_original_price():
    form = _checkout_form()
    form["lineItems"][0]["originalPrice"] = {"amount": "90.00", "currency": "PLN"}

    (item,) = map_checkout_form(form).items

    assert item.unit_price == Decimal("76.00")


def test_maps_delivery_and_its_address():
    delivery = map_checkout_form(_checkout_form()).delivery

    assert delivery.method == "Kurier"
    assert delivery.cost == Decimal("15.00")
    assert delivery.pickup_point is None
    address = delivery.address
    assert (address.first_name, address.last_name) == ("Anna", "Nowak")
    assert (address.street, address.postal_code, address.city) == (
        "Prosta 1",
        "00-001",
        "Warszawa",
    )
    assert address.country_code == "PL"
    assert address.phone == "+48 600 300 400"


def test_maps_a_pickup_point():
    form = _checkout_form()
    form["delivery"]["pickupPoint"] = {
        "id": "WAW01A",
        "name": "Paczkomat WAW01A",
        "description": "by the shop",
        "address": {
            "street": "Długa 5",
            "zipCode": "00-002",
            "city": "Warszawa",
            "countryCode": "PL",
        },
    }

    pickup_point = map_checkout_form(form).delivery.pickup_point

    assert (pickup_point.id, pickup_point.name) == ("WAW01A", "Paczkomat WAW01A")
    assert pickup_point.address.street == "Długa 5"
    assert pickup_point.address.postal_code == "00-002"


def test_maps_payment():
    payment = map_checkout_form(_checkout_form()).payment

    assert payment.type is PaymentType.ONLINE
    assert payment.provider == "P24"
    assert payment.paid_amount == Decimal("167.00")
    assert payment.paid_at == datetime(2026, 9, 14, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("allegro_type", "expected"),
    [
        ("ONLINE", PaymentType.ONLINE),
        ("CASH_ON_DELIVERY", PaymentType.CASH_ON_DELIVERY),
        ("WIRE_TRANSFER", PaymentType.BANK_TRANSFER),
        ("SPLIT_PAYMENT", PaymentType.BANK_TRANSFER),
        ("EXTENDED_TERM", PaymentType.DEFERRED),
        # a type Allegro adds later is still a payment, not a missing one
        ("SOMETHING_NEW", PaymentType.OTHER),
    ],
)
def test_payment_type_mapping(allegro_type, expected):
    form = _checkout_form()
    form["payment"]["type"] = allegro_type

    assert map_checkout_form(form).payment.type is expected


def test_an_unpaid_cash_on_delivery_order_has_no_paid_amount():
    form = _checkout_form(payment={"id": "p-1", "type": "CASH_ON_DELIVERY"})

    payment = map_checkout_form(form).payment

    assert payment.type is PaymentType.CASH_ON_DELIVERY
    assert payment.paid_amount is None
    assert payment.paid_at is None


def test_maps_the_invoice_with_the_company_tax_id():
    invoice = map_checkout_form(_checkout_form()).invoice

    assert invoice.required is True
    assert invoice.address.company_name == "Kowalski Sp. z o.o."
    assert invoice.address.tax_id == "1234563218"
    assert invoice.address.postal_code == "30-001"


def test_falls_back_to_the_deprecated_tax_id():
    form = _checkout_form()
    form["invoice"]["address"]["company"] = {
        "name": "Firma",
        "vatPayerStatus": "ACTIVE",
        "taxId": "5260250274",
    }

    assert map_checkout_form(form).invoice.address.tax_id == "5260250274"


def test_an_invoice_for_a_private_person():
    form = _checkout_form()
    address = form["invoice"]["address"]
    address.pop("company")
    address["naturalPerson"] = {"firstName": "Jan", "lastName": "Kowalski"}

    invoice_address = map_checkout_form(form).invoice.address

    assert (invoice_address.first_name, invoice_address.last_name) == ("Jan", "Kowalski")
    assert invoice_address.company_name is None
    assert invoice_address.tax_id is None


def test_maps_the_buyer_message():
    assert map_checkout_form(_checkout_form()).buyer_message == "Please pack it well"


def test_a_form_without_details_still_maps():
    """Only the fields an order cannot exist without are required."""
    form = {
        "id": "f-min",
        "status": "BOUGHT",
        "buyer": {"email": "buyer@example.com"},
        "summary": {"totalToPay": {"amount": "10.00", "currency": "PLN"}},
    }

    order = map_checkout_form(form)

    assert order.items == []
    assert order.delivery.address is None
    assert order.payment.type is None
    assert order.invoice.required is False
    assert order.invoice.address is None
    assert order.buyer_message is None


def test_blank_values_become_null_not_empty_strings():
    form = _checkout_form(messageToSeller="")
    form["buyer"]["companyName"] = "   "

    order = map_checkout_form(form)

    assert order.customer.company_name is None
    assert order.buyer_message is None


def test_an_unreadable_line_item_is_skipped_but_the_order_and_other_items_kept(caplog):
    form = _checkout_form()
    # no offer name
    form["lineItems"].append(
        {"id": "li-2", "offer": {"id": "o-2"}, "quantity": 1, "price": {"amount": "5.00"}}
    )
    form["lineItems"].append(
        {
            "id": "li-3",
            "offer": {"id": "o-3", "name": "Gadget"},
            "quantity": 1,
            "price": {"amount": "9.00", "currency": "PLN"},
        }
    )

    with caplog.at_level(logging.WARNING):
        order = map_checkout_form(form)

    assert [item.name for item in order.items] == ["Widget", "Gadget"]
    assert "line item 2" in caplog.text


def test_an_unreadable_optional_field_is_dropped_and_the_rest_kept(caplog):
    phone = "+48 " + "9" * 100
    form = _checkout_form()
    form["buyer"]["phoneNumber"] = phone

    with caplog.at_level(logging.WARNING):
        customer = map_checkout_form(form).customer

    assert customer.phone is None
    assert customer.last_name == "Kowalski"
    # logged by field name only: the value is personal data
    assert "phone" in caplog.text
    assert phone not in caplog.text


def test_malformed_detail_sections_do_not_lose_the_order():
    form = _checkout_form(
        delivery="not an object",
        payment={"type": "ONLINE", "paidAmount": {"amount": "NaN"}, "finishedAt": "soon"},
        invoice=["not", "an", "object"],
    )
    form["lineItems"].extend([None, 42])

    order = map_checkout_form(form)

    assert order.external_id == form["id"]
    assert order.delivery.address is None
    assert order.payment.type is PaymentType.ONLINE
    assert order.payment.paid_amount is None
    assert order.payment.paid_at is None
    assert order.invoice.required is False
    assert [item.name for item in order.items] == ["Widget"]


def test_an_overlong_buyer_message_is_shortened_not_dropped():
    form = _checkout_form(messageToSeller="x" * (BUYER_MESSAGE_MAX_LENGTH + 50))

    message = map_details(form).buyer_message

    assert len(message) == BUYER_MESSAGE_MAX_LENGTH
    assert message.startswith("xxx")
