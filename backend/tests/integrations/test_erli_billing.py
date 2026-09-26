"""Erli's billing account and payouts, against a fake shaped like the real answers.

The shapes are copied from Erli's real responses of 2026-09-27 (amounts and ids
changed): the billing entries in grosze with their `type`, the dictionary
saying which kind each type is, and the payouts.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx2
import pytest

from app.integrations.base import IntegrationUnavailable
from app.integrations.erli import ErliAdapter
from app.integrations.erli.client import BILLING_PAGE_SIZE, PAYOUT_PAGE_SIZE, ErliClient
from app.models.order import BillingEntry, OrderSource, Payout
from app.services.erli_import import build_erli_import_service

API_URL = "https://erli.test/svc/shop-api"
SINCE = datetime(2026, 9, 1, tzinfo=UTC)

TYPES = [
    {"type": "COMM", "description": "naliczenie prowizji", "displayLabel": "naliczenie prowizji", "fiscalFunction": "plusCharges"},
    {"type": "SHIP", "description": "Metoda dostawy ERLI.pl", "displayLabel": "metoda dostawy ERLI.pl", "fiscalFunction": "plusCharges"},
    {"type": "PAYM", "description": "płatność", "displayLabel": "pobranie opłaty", "fiscalFunction": "plusPayments"},
    {"type": "CRUC", "description": "wykorzystany rabat za prowizję", "displayLabel": "wykorzystanie rabatu transakcyjnego", "fiscalFunction": "minusCharges"},
    {"type": "CRAD", "description": "dodanie kredytów", "displayLabel": "dodanie rabatu transakcyjnego"},
]


def _entry(entry_id, type_, amount, **extra):
    entry = {
        "id": entry_id,
        "occurredAt": "2026-09-26T00:27:05.385Z",
        "amount": amount,
        "balanceAfter": 0,
        "type": type_,
        "description": type_,
        "orderId": "260926x10469",
        "shopId": 103021,
        "currency": "PLN",
        "market": "pl",
    }
    entry.update(extra)
    return entry


ENTRIES = [
    _entry(380094469, "PAYM", 2190),
    _entry(380094464, "COMM", -858, productId=345921069),
    _entry(380094461, "CRUC", 38),
    _entry(380094460, "CRAD", 62),
    _entry(380094459, "SHIP", -1269),
]
PAYOUTS = [
    {"id": 1940609, "amount": 4359, "currency": "PLN", "createdAt": "2026-09-01T03:46:28.744Z", "operator": "PAYU"},
    {"id": 1984422, "amount": 2237, "currency": "PLN", "createdAt": "2026-09-26T03:42:08.822Z", "operator": "PAYU"},
]


def _client(entries=ENTRIES, payouts=PAYOUTS, orders=(), seen=None):
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content) if request.content else None
        if seen is not None:
            seen.append((request.url.path, body))
        path = request.url.path
        if path.endswith("/dictionaries/billingEntryTypes"):
            return httpx2.Response(200, json=TYPES)
        if path.endswith("/billing/company/entries"):
            return httpx2.Response(200, json=entries(body) if callable(entries) else entries)
        if path.endswith("/payments/payouts/_search"):
            return httpx2.Response(200, json=payouts(body) if callable(payouts) else payouts)
        if path.endswith("/orders/_search"):
            return httpx2.Response(200, json=list(orders))
        return httpx2.Response(404)

    return ErliClient(api_key="key-123", api_url=API_URL, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_fees_and_settlements_are_kept_by_what_erli_says_they_are():
    entries = ErliAdapter(client=_client()).fetch_billing_entries(SINCE)

    by_type = {e.type_id: e for e in entries}
    # a rebate set aside is neither a fee nor a settlement
    assert set(by_type) == {"PAYM", "COMM", "CRUC", "SHIP"}
    assert by_type["PAYM"].is_settlement and by_type["PAYM"].amount == Decimal("21.90")
    commission = by_type["COMM"]
    assert (commission.is_settlement, commission.amount, commission.type_name) == (
        False, Decimal("-8.58"), "naliczenie prowizji"
    )
    assert (commission.source, commission.external_id, commission.order_external_id, commission.offer_id) == (
        OrderSource.ERLI, "380094464", "260926x10469", "345921069"
    )
    assert commission.occurred_at == datetime(2026, 9, 26, 0, 27, 5, 385000, tzinfo=UTC)
    # a rebate used on the commission gives some back
    assert by_type["CRUC"].amount == Decimal("0.38") and not by_type["CRUC"].is_settlement


def test_the_billing_read_asks_from_the_given_time_newest_first():
    seen = []
    ErliAdapter(client=_client(seen=seen)).fetch_billing_entries(SINCE)

    (body,) = [b for path, b in seen if path.endswith("/billing/company/entries")]
    assert body["pagination"] == {"sortField": "id", "order": "DESC", "limit": BILLING_PAGE_SIZE}
    assert body["simpleFilter"] == {"fromOccurredAt": "2026-09-01T00:00:00.000Z"}


def test_the_billing_read_pages_below_the_last_id():
    first = [_entry(10_000 - i, "COMM", -100) for i in range(BILLING_PAGE_SIZE)]

    def pages(body):
        return first if "after" not in body["pagination"] else [_entry(1, "COMM", -100)]

    seen = []
    entries = ErliAdapter(client=_client(entries=pages, seen=seen)).fetch_billing_entries(SINCE)

    assert len(entries) == BILLING_PAGE_SIZE + 1
    afters = [b["pagination"].get("after") for path, b in seen if path.endswith("/billing/company/entries")]
    assert afters == [None, 10_000 - BILLING_PAGE_SIZE + 1]


def test_a_kind_erli_does_not_name_is_left_out():
    entries = ErliAdapter(client=_client(entries=[_entry(5, "ZZZZ", -100)])).fetch_billing_entries(SINCE)
    assert entries == []


def test_a_failed_page_fails_the_read():
    def broken(request):
        if request.url.path.endswith("/dictionaries/billingEntryTypes"):
            return httpx2.Response(200, json=TYPES)
        return httpx2.Response(500)

    client = ErliClient(api_key="k", api_url=API_URL, http_client=httpx2.Client(transport=httpx2.MockTransport(broken)))
    with pytest.raises(IntegrationUnavailable):
        ErliAdapter(client=client).fetch_billing_entries(SINCE)


def test_payouts_are_read_in_zloty_since_the_given_time():
    seen = []
    payouts = ErliAdapter(client=_client(seen=seen)).fetch_payouts(SINCE)

    assert [(p.external_id, p.amount, p.operator) for p in payouts] == [
        ("1940609", Decimal("43.59"), "PAYU"),
        ("1984422", Decimal("22.37"), "PAYU"),
    ]
    assert payouts[0].paid_at == datetime(2026, 9, 1, 3, 46, 28, 744000, tzinfo=UTC)
    (body,) = [b for path, b in seen if path.endswith("/payouts/_search")]
    assert body["filter"] == {"field": "createdAt", "operator": ">=", "value": "2026-09-01T00:00:00.000Z"}
    assert body["pagination"] == {"sortField": "id", "order": "ASC", "limit": PAYOUT_PAGE_SIZE}


def test_an_import_stores_the_fees_and_payouts_once(session):
    service = build_erli_import_service(session, client=_client())
    service.sync_orders()
    service.sync_orders()

    stored = session.query(BillingEntry).filter(BillingEntry.source == OrderSource.ERLI).all()
    assert sorted(e.type_id for e in stored) == ["COMM", "CRUC", "PAYM", "SHIP"]
    assert [e.is_settlement for e in stored if e.type_id == "PAYM"] == [True]
    assert session.query(Payout).count() == 2
