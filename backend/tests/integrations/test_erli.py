"""The Erli adapter against fakes shaped like Erli's OpenAPI description.

No real Erli response has been seen yet, so these check that the adapter
reads what Erli documents; they cannot check that Erli sends it.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx2
import pytest

from app.integrations.base import (
    IntegrationAuthError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)
from app.integrations.erli import ErliAdapter
from app.integrations.erli.client import MAX_PAGE_SIZE, ErliClient
from app.integrations.erli.mapper import NO_EMAIL_DOMAIN, OrderMappingError, map_order
from app.models.order import OrderSource, OrderStatus, PaymentType

API_URL = "https://erli.test/svc/shop-api"


def _order(**overrides):
    """An Erli order: 2 × 49.99 zł plus 12.99 zł delivery, 112.97 zł in all.

    Amounts are in grosze, as Erli sends them; each is distinct, so a test
    asserting the total fails if the mapper reads the wrong one.
    """
    order = {
        "id": "erli-1001",
        "status": "purchased",
        "user": {
            "email": "abc123@proxy.erli.pl",
            "deliveryAddress": {
                "firstName": "Anna",
                "lastName": "Nowak",
                "address": "",
                "street": "Prosta",
                "buildingNumber": "1",
                "flatNumber": "4",
                "zip": "00-001",
                "city": "Warszawa",
                "country": "pl",
                "phone": "+48600300400",
            },
        },
        "items": [
            {
                "id": 1,
                "externalId": "prod-77",
                "quantity": 2,
                "unitPrice": 4999,
                "unitPriceBeforeRebate": 5999,
                "name": "Kubek",
                "slug": "kubek",
                "sku": "KUB-350",
            }
        ],
        "delivery": {"name": "Kurier InPost", "typeId": "inpostKurier", "price": 1299, "cod": False},
        "comment": "Proszę o staranne zapakowanie",
        "totalPrice": 11297,
        "currency": "PLN",
        "market": "pl",
        "payment": {"id": 5, "status": "COMPLETED"},
        "sellerStatus": "created",
        "created": "2026-09-20T10:00:00.000Z",
        "updated": "2026-09-20T10:05:00.000Z",
        "purchasedAt": "2026-09-20T10:01:00.000Z",
        "cursor": "1790000000;1001",
    }
    order.update(overrides)
    return order


# --- mapping ------------------------------------------------------------------


def test_maps_an_erli_order():
    order = map_order(_order())

    assert order.source is OrderSource.ERLI
    assert order.external_id == "erli-1001"
    assert order.customer_email == "abc123@proxy.erli.pl"
    assert order.total_amount == Decimal("112.97")
    assert order.ordered_at == datetime(2026, 9, 20, 10, 1, tzinfo=UTC)
    assert order.buyer_message == "Proszę o staranne zapakowanie"
    (item,) = order.items
    assert (item.sku, item.offer_id, item.name, item.quantity) == ("KUB-350", "prod-77", "Kubek", 2)
    # after the rebate, not the list price
    assert item.unit_price == Decimal("49.99")
    assert order.delivery.cost == Decimal("12.99")
    assert order.delivery.method == "Kurier InPost"
    address = order.delivery.address
    assert (address.street, address.postal_code, address.city) == ("Prosta 1/4", "00-001", "Warszawa")
    assert address.country_code == "PL"
    assert (order.customer.first_name, order.customer.last_name) == ("Anna", "Nowak")


def test_a_paid_order_is_paid_in_full_online():
    payment = map_order(_order()).payment

    assert payment.type is PaymentType.ONLINE
    assert payment.paid_amount == Decimal("112.97")
    assert payment.paid_at == datetime(2026, 9, 20, 10, 1, tzinfo=UTC)


def test_an_unpaid_order_is_known_to_be_unpaid():
    payment = map_order(_order(status="pending", payment={"id": 5, "status": "PENDING"})).payment

    # zero, not null: the unpaid queue needs to know
    assert payment.paid_amount == Decimal("0.00")
    assert payment.paid_at is None


def test_cash_on_delivery_owes_nothing_before_shipping():
    form = _order(status="purchased", payment=None)
    form["delivery"]["cod"] = True

    payment = map_order(form).payment

    assert payment.type is PaymentType.CASH_ON_DELIVERY
    assert payment.paid_amount is None


@pytest.mark.parametrize(
    ("overrides", "expected", "label"),
    [
        ({"status": "cancelled"}, OrderStatus.CANCELLED, "cancelled"),
        ({"sellerStatus": "inProgress"}, OrderStatus.CONFIRMED, "inProgress"),
        ({"deliveryTracking": {"status": "readyToSend"}}, OrderStatus.READY_FOR_SHIPMENT, "readyToSend"),
        ({"deliveryTracking": {"status": "sent"}}, OrderStatus.SHIPPED, "sent"),
        ({"deliveryTracking": {"status": "delivered"}}, OrderStatus.DELIVERED, "delivered"),
        # the parcel says more than the seller's own status
        (
            {"sellerStatus": "inProgress", "deliveryTracking": {"status": "sent"}},
            OrderStatus.SHIPPED,
            "sent",
        ),
        # a cancelled order is cancelled whatever its parcel is doing
        (
            {"status": "cancelled", "deliveryTracking": {"status": "sent"}},
            OrderStatus.CANCELLED,
            "cancelled",
        ),
        ({"sellerStatus": "somethingNew"}, OrderStatus.NEW, "purchased"),
        # returned goods never go back to the to-make queue
        ({"status": "returned", "sellerStatus": "created"}, OrderStatus.DELIVERED, "returned"),
    ],
)
def test_status_mapping(overrides, expected, label):
    order = map_order(_order(**overrides))

    assert (order.status, order.marketplace_status_label) == (expected, label)


def test_a_pickup_point_and_its_parcel():
    form = _order(
        deliveryTracking={
            "status": "readyToPickup",
            "vendor": "inpost",
            "trackingNumber": "620111222333444555666777",
        }
    )
    form["delivery"]["pickupPlace"] = {
        "id": 9,
        "externalId": "WAW01M",
        "name": "Paczkomat WAW01M",
        "address": "Długa 5",
        "city": "Warszawa",
        "zip": "00-002",
        "country": "pl",
    }

    order = map_order(form)

    point = order.delivery.pickup_point
    assert (point.id, point.name, point.address.street) == ("WAW01M", "Paczkomat WAW01M", "Długa 5")
    (shipment,) = order.shipments
    assert (shipment.carrier_id, shipment.waybill) == ("inpost", "620111222333444555666777")
    assert shipment.tracking_status == "AVAILABLE_FOR_PICKUP"


def test_no_tracking_number_leaves_the_stored_parcels_alone():
    assert map_order(_order()).shipments is None


def test_a_company_invoice():
    form = _order()
    form["user"]["invoiceAddress"] = {
        "type": "company",
        "companyName": "Firma Sp. z o.o.",
        "nip": "1234563218",
        "street": "Firmowa",
        "buildingNumber": "2",
        "zip": "30-001",
        "city": "Kraków",
        "country": "pl",
    }

    invoice = map_order(form).invoice

    assert invoice.required is True
    assert (invoice.address.company_name, invoice.address.tax_id) == ("Firma Sp. z o.o.", "1234563218")
    assert invoice.address.street == "Firmowa 2"


def test_no_invoice_address_means_no_invoice():
    assert map_order(_order()).invoice.required is False


def test_an_order_before_erli_assigns_the_email_is_still_imported():
    form = _order()
    del form["user"]["email"]

    order = map_order(form)

    assert order.customer_email == f"order-erli-1001@{NO_EMAIL_DOMAIN}"


@pytest.mark.parametrize("total", [None, 0, "11297", 112.97])
def test_an_order_without_a_whole_positive_total_is_refused(total):
    with pytest.raises(OrderMappingError):
        map_order(_order(totalPrice=total))


def test_an_unreadable_item_costs_only_that_item():
    form = _order()
    form["items"].append({"id": 2, "quantity": 1, "unitPrice": 100})  # no name

    assert [item.name for item in map_order(form).items] == ["Kubek"]


# --- the HTTP client ----------------------------------------------------------


def _client(handler, api_key="key-123"):
    return ErliClient(
        api_key=api_key,
        api_url=API_URL,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def test_searches_orders_by_update_time_with_the_key_as_bearer():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=[_order()])

    orders = _client(handler).search_orders(
        after="1790000000;999", created_since=datetime(2026, 9, 1, tzinfo=UTC)
    )

    assert [o["id"] for o in orders] == ["erli-1001"]
    assert seen["url"] == f"{API_URL}/orders/_search"
    assert seen["auth"] == "Bearer key-123"
    assert seen["body"] == {
        "pagination": {
            "sortField": "updated",
            "order": "ASC",
            "limit": MAX_PAGE_SIZE,
            "after": "1790000000;999",
        },
        "filter": {"field": "created", "operator": ">=", "value": "2026-09-01T00:00:00.000Z"},
    }


def test_without_a_key_nothing_is_sent():
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request expected")

    with pytest.raises(IntegrationNotConfigured):
        _client(handler, api_key="").search_orders()


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, IntegrationAuthError), (403, IntegrationAuthError), (429, IntegrationUnavailable), (500, IntegrationUnavailable)],
)
def test_refusals_and_failures_are_integration_errors(status, error):
    with pytest.raises(error):
        _client(lambda request: httpx2.Response(status)).search_orders()


def test_an_answer_that_is_not_a_list_is_an_error():
    with pytest.raises(IntegrationUnavailable):
        _client(lambda request: httpx2.Response(200, json={"orders": []})).search_orders()


def test_an_unreachable_erli_is_an_error():
    def handler(request):
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(IntegrationUnavailable):
        _client(handler).search_orders()


# --- paging -------------------------------------------------------------------


def test_pages_by_cursor_until_a_short_page():
    afters = []
    pages = [
        [_order(id=f"erli-{n}", cursor=f"179;{n}") for n in range(MAX_PAGE_SIZE)],
        [_order(id="erli-last", cursor="180;1")],
    ]

    def handler(request):
        afters.append(json.loads(request.content)["pagination"].get("after"))
        return httpx2.Response(200, json=pages[len(afters) - 1])

    adapter = ErliAdapter(client=_client(handler))
    fetched = list(adapter.iter_order_pages(updated_since=datetime(2026, 9, 20, 12, tzinfo=UTC)))

    assert [len(page) for page in fetched] == [MAX_PAGE_SIZE, 1]
    # the first page from the time asked for, the next from the last cursor
    assert afters == ["2026-09-20T12:00:00.000Z", f"179;{MAX_PAGE_SIZE - 1}"]


def test_a_full_page_without_a_cursor_stops_the_import():
    page = [_order(id=f"erli-{n}", cursor=None) for n in range(MAX_PAGE_SIZE)]
    adapter = ErliAdapter(client=_client(lambda request: httpx2.Response(200, json=page)))

    with pytest.raises(IntegrationUnavailable):
        list(adapter.iter_order_pages())


def test_an_unmappable_order_is_skipped_not_fatal():
    page = [_order(), _order(id="erli-bad", totalPrice=0)]
    adapter = ErliAdapter(client=_client(lambda request: httpx2.Response(200, json=page)))

    (fetched,) = list(adapter.iter_order_pages())

    assert [order.external_id for order in fetched] == ["erli-1001"]
