"""Erli's payments and payouts as payment operations, and Erli's sales in the non-invoiced record
(docs/NON_INVOICED_SALES.md, stage 7), against fakes shaped like Erli's published API description.

No real answer of `/payments/operations/_search` has been seen yet, so these check that Anvero reads
what Erli documents, not that Erli sends it.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.integrations.erli import ErliAdapter
from app.integrations.erli.client import PAYMENT_PAGE_SIZE, ErliClient
from app.integrations.erli.mapper import map_order
from app.integrations.erli.payments import map_payment, map_payout_operation
from app.models.non_invoiced import LedgerEntry
from app.models.order import Order, OrderSource, PaymentOperation
from app.services.erli_import import build_erli_import_service
from app.services.non_invoiced.classifier import Category, Reason
from tests.integrations.test_erli import _order

API_URL = "https://erli.test/svc/shop-api"
SINCE = datetime(2026, 9, 1, tzinfo=UTC)


def _payment(**overrides):
    payment = {
        "id": 5,
        "orderIds": ["erli-1001"],
        "amount": 112.97,
        "status": "COMPLETED",
        "createdAt": "2026-09-20T10:00:30.000Z",
        "completedAt": "2026-09-20T10:01:00.000Z",
        "operator": "PAYU",
        "methodCode": "PAYU.blik",
        "methodName": "BLIK",
    }
    payment.update(overrides)
    return payment


PAYOUT = {"id": 1984422, "amount": 11297, "currency": "PLN", "createdAt": "2026-09-22T03:42:08.822Z", "operator": "PAYU"}


def _client(orders=(), payments=(), payouts=(PAYOUT,), order_by_id=None, seen=None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content) if request.content else None
        if seen is not None:
            seen.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("/payments/operations/_search"):
            return httpx2.Response(200, json=payments(body) if callable(payments) else list(payments))
        if path.endswith("/payments/payouts/_search"):
            return httpx2.Response(200, json=list(payouts))
        if path.endswith("/orders/_search"):
            return httpx2.Response(200, json=list(orders))
        if request.method == "GET" and "/orders/" in path:
            return order_by_id(path.rsplit("/", 1)[-1]) if order_by_id else httpx2.Response(404)
        if path.endswith(("/dictionaries/billingEntryTypes", "/billing/company/entries")):
            return httpx2.Response(200, json=[])
        return httpx2.Response(404)

    return ErliClient(api_key="key-123", api_url=API_URL, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


# --- mapping -------------------------------------------------------------------------------------


def test_an_order_keeps_the_id_of_the_payment_that_paid_it():
    assert map_order(_order()).payment.id == "5"


def test_an_order_without_its_payment_is_read_as_before():
    assert map_order(_order(payment=None)).payment.id is None


def test_a_completed_payment_is_a_contribution_in_zloty():
    operation = map_payment(_payment())

    assert (operation.type, operation.group, operation.payment_id, operation.wallet_operator) == (
        "CONTRIBUTION",
        "INCOME",
        "5",
        "PAYU",
    )
    # złoty here, unlike the grosze of Erli's orders and payouts
    assert operation.amount == Decimal("112.97")
    assert operation.occurred_at == datetime(2026, 9, 20, 10, 1, tzinfo=UTC)
    assert operation.fingerprint == "ERLI-PAYMENT-5"


@pytest.mark.parametrize("status", ["NEW", "PENDING", "WAITING_FOR_CONFIRMATION", "CANCELED"])
def test_a_payment_not_completed_is_no_contribution(status):
    assert map_payment(_payment(status=status)) is None


def test_a_payout_is_money_out_of_the_wallet():
    operation = map_payout_operation(PAYOUT)

    assert (operation.type, operation.payout_id, operation.wallet_operator, operation.amount) == (
        "PAYOUT",
        "1984422",
        "PAYU",
        Decimal("-112.97"),
    )


# --- reading -------------------------------------------------------------------------------------


def test_payments_and_payouts_are_read_since_the_given_time():
    seen = []
    operations = ErliAdapter(client=_client(payments=[_payment(), _payment(id=6, status="PENDING")], seen=seen)).fetch_payment_operations(SINCE)

    assert [(op.type, op.payment_id or op.payout_id) for op in operations] == [("CONTRIBUTION", "5"), ("PAYOUT", "1984422")]
    (body,) = [b for _m, path, b in seen if path.endswith("/payments/operations/_search")]
    assert body == {
        "type": "payment",
        "pagination": {"sortField": "id", "order": "ASC", "limit": PAYMENT_PAGE_SIZE},
        "filter": {"field": "completedAt", "operator": ">=", "value": "2026-09-01T00:00:00.000Z"},
    }


def test_payments_are_read_page_after_page_by_id():
    def pages(body):
        after = body["pagination"].get("after")
        if after is None:
            return [_payment(id=i) for i in range(1, PAYMENT_PAGE_SIZE + 1)]
        return [_payment(id=after + 1)]

    operations = ErliAdapter(client=_client(payments=pages)).fetch_payment_operations(SINCE)

    assert len([op for op in operations if op.type == "CONTRIBUTION"]) == PAYMENT_PAGE_SIZE + 1


def test_a_full_page_of_payments_without_an_id_fails_the_read():
    page = [_payment(id=None) for _ in range(PAYMENT_PAGE_SIZE)]

    with pytest.raises(IntegrationUnavailable):
        ErliAdapter(client=_client(payments=page)).fetch_payment_operations(SINCE)


def test_orders_are_read_again_by_id_and_one_missing_is_skipped():
    def by_id(order_id):
        if order_id == "erli-1001":
            return httpx2.Response(200, json=_order())
        return httpx2.Response(404)

    orders = ErliAdapter(client=_client(order_by_id=by_id)).fetch_orders_by_id(["erli-1001", "gone"])

    assert [o.external_id for o in orders] == ["erli-1001"]


def test_a_refused_key_ends_reading_orders_again():
    with pytest.raises(IntegrationAuthError):
        ErliAdapter(client=_client(order_by_id=lambda _id: httpx2.Response(401))).fetch_orders_by_id(["erli-1001"])


# --- the import, and the record ------------------------------------------------------------------


def _moment(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def test_an_import_puts_a_paid_erli_sale_in_the_record_with_its_payout(session):
    paid_at = datetime.now(UTC).replace(microsecond=0) - timedelta(days=2)
    order = _order(purchasedAt=_moment(paid_at), created=_moment(paid_at), updated=_moment(paid_at))
    payment = _payment(completedAt=_moment(paid_at + timedelta(seconds=30)))
    payout = {**PAYOUT, "createdAt": _moment(paid_at + timedelta(days=1))}
    service = build_erli_import_service(session, client=_client(orders=[order], payments=[payment], payouts=[payout]))

    service.sync_orders()
    service.sync_orders()

    stored = session.query(Order).filter(Order.source == OrderSource.ERLI).one()
    assert stored.payment_id == "5"
    assert session.query(PaymentOperation).filter(PaymentOperation.source == OrderSource.ERLI).count() == 2
    (row,) = session.query(LedgerEntry).all()
    assert (row.category, row.reason) == (Category.EXEMPT_MAIL_ORDER.value, Reason.E41.value)
    # the buyer's name and address come from the delivery address, all Erli names
    assert (row.buyer_first_name, row.buyer_city) == ("Anna", "Warszawa")
    assert row.payout_id == "1984422"
    assert row.amount == Decimal("112.97")
