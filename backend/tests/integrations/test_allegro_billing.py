"""Billing entries (Allegro's fees): the client's call, the mapping, reading
every page, storing each entry once, and the per-order total the API shows."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.allegro.adapter import AllegroAdapter
from app.integrations.allegro.client import AllegroClient
from app.integrations.allegro.mapper import map_billing_entry
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.main import app
from app.models.integration import IntegrationCredential
from app.models.order import BillingEntry, Order, OrderSource, OrderStatus
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository
from app.schemas.order import BillingEntryCreate
from app.schemas.types import _as_utc
from app.schemas.user import UserCreate
from app.services.order_import_service import (
    BILLING_OVERLAP,
    SYNC_OVERLAP,
    OrderImportService,
)
from app.services.user_service import UserService


def _raw(entry_id="E1", amount="-8.50", order_id="ORDER-1", type_id="SUC", **overrides):
    entry = {
        "id": entry_id,
        "occurredAt": "2026-09-20T10:27:17.412Z",
        "type": {"id": type_id, "name": "Prowizja od sprzedaży"},
        "value": {"amount": amount, "currency": "PLN"},
        "offer": {"id": "6206586563", "name": "oferta testowa"},
    }
    if order_id:
        entry["order"] = {"id": order_id}
    entry.update(overrides)
    return entry


# --- the client -------------------------------------------------------------


def test_asks_for_entries_since_a_time_a_page_at_a_time():
    seen = []

    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(200, json={"billingEntries": [_raw()]})

    client = AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url="https://api.test",
        auth_url="https://auth.test",
        user_agent="anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )

    entries = client.fetch_billing_entries(datetime(2026, 9, 14, 8, 0, tzinfo=UTC), 100, 200)

    assert entries == [_raw()]
    assert seen[0].url.path == "/billing/billing-entries"
    assert seen[0].url.params["occurredAt.gte"] == "2026-09-14T08:00:00.000Z"
    assert (seen[0].url.params["limit"], seen[0].url.params["offset"]) == ("100", "200")


# --- the mapping ------------------------------------------------------------


def test_maps_a_charge_with_its_order():
    entry = map_billing_entry(_raw())

    assert entry is not None
    assert entry.source is OrderSource.ALLEGRO
    assert (entry.external_id, entry.type_id, entry.order_external_id) == ("E1", "SUC", "ORDER-1")
    assert entry.amount == Decimal("-8.50")
    assert entry.occurred_at == datetime(2026, 9, 20, 10, 27, 17, 412000, tzinfo=UTC)


def test_an_entry_that_names_no_order_is_still_kept():
    entry = map_billing_entry(_raw(order_id=None, type_id="CXR"))

    assert entry is not None
    assert entry.order_external_id is None


@pytest.mark.parametrize(
    "broken",
    [
        {"id": "E1"},
        _raw(entry_id=None),
        _raw(occurredAt="not a date"),
        _raw(value={"currency": "PLN"}),
        _raw(type={}),
    ],
)
def test_an_entry_missing_something_essential_is_dropped(broken):
    assert map_billing_entry(broken) is None


# --- the adapter ------------------------------------------------------------


class FakeClient:
    is_configured = True

    def __init__(self, pages=None, error=None):
        self.pages = pages or []
        self.error = error
        self.calls = []

    def fetch_billing_entries(self, occurred_since, limit=100, offset=0):
        self.calls.append((occurred_since, limit, offset))
        if self.error:
            raise self.error
        index = offset // limit
        return self.pages[index] if index < len(self.pages) else []


SINCE = datetime(2026, 9, 14, tzinfo=UTC)


def test_reads_every_page_until_a_short_one():
    full = [_raw(f"E{i}") for i in range(100)]
    client = FakeClient([full, [_raw("LAST")]])

    entries = AllegroAdapter(client=client).fetch_billing_entries(SINCE)

    assert len(entries) == 101
    assert [c[2] for c in client.calls] == [0, 100]


def test_an_unusable_entry_costs_only_itself(caplog):
    client = FakeClient([[_raw("E1"), {"id": "BAD"}, _raw("E2")]])

    entries = AllegroAdapter(client=client).fetch_billing_entries(SINCE)

    assert [e.external_id for e in entries] == ["E1", "E2"]


def test_a_failing_page_raises_instead_of_returning_a_partial_read():
    client = FakeClient(error=IntegrationUnavailable("boom"))

    with pytest.raises(IntegrationUnavailable):
        AllegroAdapter(client=client).fetch_billing_entries(SINCE)


# --- storing, and the sync point --------------------------------------------


def _entry(external_id="E1", amount="-8.50", order="ORDER-1", **overrides):
    data = {
        "source": OrderSource.ALLEGRO,
        "external_id": external_id,
        "occurred_at": datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        "type_id": "SUC",
        "type_name": "Prowizja",
        "amount": Decimal(amount),
        "currency": "PLN",
        "order_external_id": order,
    }
    data.update(overrides)
    return BillingEntryCreate(**data)


def test_an_entry_is_stored_once_however_often_it_is_read(session):
    repository = OrderRepository(session)

    first = repository.add_billing_entries([_entry("E1"), _entry("E2")])
    second = repository.add_billing_entries([_entry("E1"), _entry("E3")])

    assert (first, second) == (2, 1)
    assert session.query(BillingEntry).count() == 3


def test_a_duplicate_inside_one_read_is_stored_once(session):
    added = OrderRepository(session).add_billing_entries([_entry("E1"), _entry("E1")])

    assert added == 1


class BillingAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, entries=None, error=None):
        self.entries = entries or []
        self.error = error
        self.since = []

    def fetch_orders(self, limit=100, offset=0):
        return []

    def fetch_billing_entries(self, since):
        self.since.append(since)
        if self.error:
            raise self.error
        return self.entries


def _service(session, adapter):
    session.add(
        IntegrationCredential(provider="ALLEGRO", refresh_token="t", seed_fingerprint="f")
    )
    session.commit()
    return OrderImportService(
        OrderRepository(session),
        adapter,
        credentials=IntegrationCredentialRepository(session),
        initial_days=7,
    )


def _point(session):
    session.expire_all()
    point = session.get(IntegrationCredential, "ALLEGRO").last_billing_synced_at
    return None if point is None else _as_utc(point)


def test_the_first_read_reaches_back_the_initial_window_and_records_where_it_got_to(session):
    adapter = BillingAdapter([_entry("E1")])
    service = _service(session, adapter)
    started = datetime.now(UTC)

    service._sync_billing(started)

    assert adapter.since == [started - timedelta(days=7)]
    assert session.query(BillingEntry).count() == 1
    assert _point(session) == started - SYNC_OVERLAP


def test_a_later_read_resumes_from_the_point_less_an_overlap(session):
    adapter = BillingAdapter()
    service = _service(session, adapter)
    started = datetime.now(UTC)
    service._sync_billing(started)
    later = started + timedelta(hours=1)

    service._sync_billing(later)

    assert adapter.since[1] == started - SYNC_OVERLAP - BILLING_OVERLAP


def test_a_refused_read_keeps_the_point_and_never_fails_the_import(session):
    adapter = BillingAdapter(error=IntegrationAuthError("Allegro denied access"))
    service = _service(session, adapter)

    service._sync_billing(datetime.now(UTC))

    assert _point(session) is None
    assert session.query(BillingEntry).count() == 0


def test_an_import_reads_billing_after_its_orders(session):
    adapter = BillingAdapter([_entry("E1")])
    service = _service(session, adapter)
    service.adapter.iter_order_pages = lambda **_: iter([[]])

    service.sync_orders()

    assert session.query(BillingEntry).count() == 1


# --- the API ----------------------------------------------------------------

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def api():
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        operator = UserService(UserRepository(db)).create_user(
            UserCreate(email="billing-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)


def _new_order(db, external_id="ORDER-1"):
    order = OrderRepository(db).create(
        Order(
            external_id=external_id,
            source=OrderSource.ALLEGRO,
            status=OrderStatus.NEW,
            customer_email="buyer@example.com",
            total_amount=Decimal("100.00"),
            currency="PLN",
        )
    )
    return order


def test_the_order_shows_its_own_entries_and_their_sum(api):
    order = _new_order(api)
    _new_order(api, "ORDER-2")
    OrderRepository(api).add_billing_entries(
        [
            _entry("E1", "-8.50"),
            _entry("E2", "-2.00", type_id="HB4"),
            _entry("E3", "1.00", type_id="REF"),
            _entry("OTHER", "-99.00", order="ORDER-2"),
            _entry("NONE", "-5.00", order=None),
        ]
    )

    response = client.get(f"/api/v1/orders/{order.id}/billing")

    assert response.status_code == 200
    body = response.json()
    assert sorted(e["type_id"] for e in body["entries"]) == ["HB4", "REF", "SUC"]
    assert body["total"] == "-9.50"
    assert body["currency"] == "PLN"


def test_an_order_without_entries_has_a_zero_total(api):
    order = _new_order(api)

    body = client.get(f"/api/v1/orders/{order.id}/billing").json()

    assert body == {"entries": [], "total": "0.00", "currency": "PLN"}


def test_billing_needs_a_login_and_a_real_order(api):
    order = _new_order(api)

    assert TestClient(app).get(f"/api/v1/orders/{order.id}/billing").status_code == 401
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/orders/{missing}/billing").status_code == 404
