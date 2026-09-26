"""Allegro's payouts to the seller's bank, read from its payment operations.

Shaped by Allegro's published OpenAPI specification (`PaymentOperations`,
`PayoutOperation`, `PayoutOperationCancel`); no real response has been seen yet.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.integrations.allegro.adapter import AllegroAdapter
from app.integrations.allegro.client import PAYMENT_OPERATIONS_PAGE_SIZE, AllegroClient
from app.integrations.allegro.mapper import map_payout_operation
from app.integrations.base import IntegrationAuthError
from app.models.integration import IntegrationCredential
from app.models.order import BillingEntry, OrderSource, Payout
from app.repositories.integration_credential_repository import IntegrationCredentialRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.order import BillingEntryCreate
from app.services.order_import_service import PAYOUT_OVERLAP, OrderImportService

SINCE = datetime(2026, 9, 1, tzinfo=UTC)


def _operation(type_="PAYOUT", payout_id="efe29ef4-c279-444d-a1d4-6243eb4bc029", amount="-820.00", **overrides):
    operation = {
        "type": type_,
        "group": "OUTCOME",
        "wallet": {"paymentOperator": "AF", "type": "AVAILABLE", "balance": {"amount": "0.00", "currency": "PLN"}},
        "value": {"amount": amount, "currency": "PLN"},
        "occurredAt": "2026-09-25T06:12:00.000Z",
        "marketplaceId": "allegro-pl",
    }
    if payout_id:
        operation["payout"] = {"id": payout_id}
    operation.update(overrides)
    return operation


# --- the client -------------------------------------------------------------


def test_asks_for_the_operations_going_out_since_a_time():
    seen = []

    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(200, json={"paymentOperations": [_operation()], "count": 1, "totalCount": 1})

    client = AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url="https://api.test",
        auth_url="https://auth.test",
        user_agent="anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )

    operations = client.fetch_payment_operations(datetime(2026, 9, 14, 8, 0, tzinfo=UTC), "OUTCOME", 50, 100)

    assert operations == [_operation()]
    params = seen[0].url.params
    assert seen[0].url.path == "/payments/payment-operations"
    assert (params["group"], params["occurredAt.gte"], params["limit"], params["offset"]) == (
        "OUTCOME", "2026-09-14T08:00:00.000Z", "50", "100"
    )


def test_a_page_larger_than_allegro_allows_is_refused_before_asking():
    client = AllegroClient(client_id="id", client_secret="s", refresh_token="r", api_url="https://api.test")
    with pytest.raises(ValueError):
        client.fetch_payment_operations(SINCE, limit=PAYMENT_OPERATIONS_PAGE_SIZE + 1)


# --- the mapping ------------------------------------------------------------


def test_a_payout_is_positive_and_kept_by_its_id():
    payout = map_payout_operation(_operation())

    assert payout is not None
    assert (payout.source, payout.external_id, payout.amount, payout.currency, payout.operator) == (
        OrderSource.ALLEGRO, "efe29ef4-c279-444d-a1d4-6243eb4bc029", Decimal("820.00"), "PLN", "AF"
    )
    assert payout.paid_at == datetime(2026, 9, 25, 6, 12, tzinfo=UTC)


def test_a_cancelled_payout_gives_the_money_back_under_an_id_of_its_own():
    cancel = map_payout_operation(_operation("PAYOUT_CANCEL", amount="820.00"))

    assert cancel is not None
    assert (cancel.external_id, cancel.amount) == ("efe29ef4-c279-444d-a1d4-6243eb4bc029:cancel", Decimal("-820.00"))


@pytest.mark.parametrize(
    "raw",
    [
        _operation("DEDUCTION_CHARGE"),
        _operation(payout_id=None),
        _operation(amount="lots"),
        _operation(occurredAt=None),
    ],
)
def test_anything_else_is_not_a_payout(raw):
    assert map_payout_operation(raw) is None


# --- the adapter ------------------------------------------------------------


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_payment_operations(self, since, group, limit, offset):
        self.calls.append((since, group, limit, offset))
        index = offset // limit
        return self.pages[index] if index < len(self.pages) else []


def test_reads_every_page_and_keeps_only_the_payouts():
    full = [_operation("DEDUCTION_CHARGE", payout_id=None)] * (PAYMENT_OPERATIONS_PAGE_SIZE - 1) + [_operation(payout_id="P1")]
    client = FakeClient([full, [_operation(payout_id="P2")]])

    payouts = AllegroAdapter(client=client).fetch_payouts(SINCE)

    assert [p.external_id for p in payouts] == ["P1", "P2"]
    assert [c[3] for c in client.calls] == [0, PAYMENT_OPERATIONS_PAGE_SIZE]
    assert {c[1] for c in client.calls} == {"OUTCOME"}


# --- the import -------------------------------------------------------------


class PayoutAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, payouts=None, error=None):
        self.payouts = payouts or []
        self.error = error
        self.since = []

    def fetch_orders(self, limit=100, offset=0):
        return []

    def fetch_billing_entries(self, since):
        return [
            BillingEntryCreate(
                source=OrderSource.ALLEGRO,
                external_id="E1",
                occurred_at=datetime(2026, 9, 20, tzinfo=UTC),
                type_id="SUC",
                amount=Decimal("-1.00"),
                currency="PLN",
            )
        ]

    def fetch_payouts(self, since):
        self.since.append(since)
        if self.error:
            raise self.error
        return self.payouts


def _service(session, adapter):
    session.add(IntegrationCredential(provider="ALLEGRO", refresh_token="t", seed_fingerprint="f"))
    session.commit()
    return OrderImportService(
        OrderRepository(session),
        adapter,
        credentials=IntegrationCredentialRepository(session),
        initial_days=7,
    )


def test_payouts_are_stored_once_and_read_again_from_a_week_before_the_latest(session):
    payout = map_payout_operation(_operation())
    adapter = PayoutAdapter([payout])
    service = _service(session, adapter)
    started = datetime.now(UTC)

    service._sync_payouts(started)
    service._sync_payouts(started)

    assert session.query(Payout).count() == 1
    assert adapter.since[0] == started - timedelta(days=7)
    assert adapter.since[1] == payout.paid_at - PAYOUT_OVERLAP


def test_a_refused_payout_read_holds_back_neither_the_fees_nor_the_import(session):
    adapter = PayoutAdapter(error=IntegrationAuthError("missing allegro:api:payments:read"))
    service = _service(session, adapter)
    service.adapter.iter_order_pages = lambda **_: iter([[]])

    service.sync_orders()

    assert session.query(BillingEntry).count() == 1
    session.expire_all()
    assert session.get(IntegrationCredential, "ALLEGRO").last_billing_synced_at is not None
    assert session.query(Payout).count() == 0
