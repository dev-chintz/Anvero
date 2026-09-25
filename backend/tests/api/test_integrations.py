from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.endpoints.integrations as integrations_endpoint
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.main import app
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

# `client` acts as a logged-in operator (see setup_module); `anonymous` never
# sends a token, to prove the endpoints refuse it -- same pattern as
# tests/api/test_orders.py
client = TestClient(app)
anonymous = TestClient(app)

OPERATOR_EMAIL = "integrations-operator@example.com"

SQLALCHEMY_DATABASE_URL = settings.database_url

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=(
        {"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}
    ),
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def setup_module():
    """Create test database tables and log the test client in."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        operator = UserService(UserRepository(db)).create_user(
            UserCreate(email=OPERATOR_EMAIL, password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    """Drop test database tables."""
    Base.metadata.drop_all(bind=engine)


@dataclass
class _FakeClient:
    is_configured: bool


@dataclass
class _FakeResult:
    created: int
    updated: int
    cancellation_warnings: int


class _FakeService:
    """Stands in for OrderImportService: no network, no real adapter.

    Either returns a fixed result or raises whatever exception the test
    hands it, so the endpoint's error mapping can be exercised without ever
    calling Allegro.
    """

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = 0

    def sync_orders(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def _patch_client(monkeypatch, configured: bool) -> None:
    monkeypatch.setattr(
        integrations_endpoint,
        "build_allegro_client",
        lambda db: _FakeClient(is_configured=configured),
    )


def _patch_service(monkeypatch, service: _FakeService) -> None:
    monkeypatch.setattr(
        integrations_endpoint, "build_allegro_import_service", lambda db: service
    )


def test_status_and_import_refuse_an_anonymous_request():
    """Regression: the orders API was open to anyone who could reach it --
    the same must hold for the integrations router."""
    assert anonymous.get("/api/v1/integrations/allegro").status_code == 401
    assert (
        anonymous.post("/api/v1/integrations/allegro/import", json={}).status_code
        == 401
    )


def test_status_reports_configured_true(monkeypatch):
    _patch_client(monkeypatch, configured=True)

    response = client.get("/api/v1/integrations/allegro")

    assert response.status_code == 200
    assert response.json()["configured"] is True


def test_status_reports_configured_false(monkeypatch):
    _patch_client(monkeypatch, configured=False)

    response = client.get("/api/v1/integrations/allegro")

    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_status_never_leaks_a_credential_or_token(monkeypatch):
    """However the application is configured, the response must carry nothing
    that could be a secret or a token - the client id is not one, the secret
    and the refresh token are."""
    _patch_client(monkeypatch, configured=True)
    monkeypatch.setattr(settings, "allegro_client_secret", "SECRET-VALUE")
    monkeypatch.setattr(settings, "allegro_refresh_token", "TOKEN-VALUE")

    response = client.get("/api/v1/integrations/allegro")

    assert "SECRET-VALUE" not in response.text
    assert "TOKEN-VALUE" not in response.text
    assert set(response.json()) == {
        "configured",
        "connected",
        "application_complete",
        "client_id",
        "user_agent",
        "environment",
        "source",
        "account_login",
        "last_import_at",
        "last_import_created",
        "last_import_updated",
        "last_import_error",
        "auto_import_interval_minutes",
    }


def test_successful_import_returns_the_fake_services_counts(monkeypatch):
    fake = _FakeService(result=_FakeResult(created=3, updated=2, cancellation_warnings=1))
    _patch_service(monkeypatch, fake)

    response = client.post("/api/v1/integrations/allegro/import", json={})

    assert response.status_code == 200
    assert response.json() == {
        "created": 3,
        "updated": 2,
        "cancellation_warnings": 1,
    }
    assert fake.calls == 1


def test_not_configured_is_reported_as_409(monkeypatch):
    fake = _FakeService(error=IntegrationNotConfigured("Allegro credentials are missing"))
    _patch_service(monkeypatch, fake)

    response = client.post("/api/v1/integrations/allegro/import", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "Allegro is not configured"


def test_auth_error_is_reported_as_502_with_the_exceptions_message(monkeypatch):
    fake = _FakeService(
        error=IntegrationAuthError(
            "Allegro rejected the refresh token; the application needs "
            "authorizing again"
        )
    )
    _patch_service(monkeypatch, fake)

    response = client.post("/api/v1/integrations/allegro/import", json={})

    assert response.status_code == 502
    assert "needs authorizing again" in response.json()["detail"]


def test_generic_integration_error_is_reported_as_502(monkeypatch):
    fake = _FakeService(error=IntegrationError("Allegro API returned 503"))
    _patch_service(monkeypatch, fake)

    response = client.post("/api/v1/integrations/allegro/import", json={})

    assert response.status_code == 502
    assert response.json()["detail"] == "Allegro API returned 503"


def test_a_second_import_while_the_first_holds_the_lock_is_refused(monkeypatch):
    """Allegro rotates the refresh token on every use, so two imports
    running at once would race to refresh it. The lock is acquired
    directly here to simulate an import already in progress."""
    fake = _FakeService(result=_FakeResult(created=1, updated=0, cancellation_warnings=0))
    _patch_service(monkeypatch, fake)

    assert integrations_endpoint._import_lock.acquire(blocking=False)
    try:
        response = client.post("/api/v1/integrations/allegro/import", json={})
    finally:
        integrations_endpoint._import_lock.release()

    assert response.status_code == 409
    assert response.json()["detail"] == "An Allegro import is already running"
    assert fake.calls == 0


def test_the_lock_is_released_after_a_failed_import_so_the_next_one_can_run(
    monkeypatch,
):
    failing = _FakeService(error=IntegrationError("Allegro API returned 503"))
    _patch_service(monkeypatch, failing)
    failed = client.post("/api/v1/integrations/allegro/import", json={})
    assert failed.status_code == 502

    succeeding = _FakeService(
        result=_FakeResult(created=1, updated=0, cancellation_warnings=0)
    )
    _patch_service(monkeypatch, succeeding)
    followup = client.post("/api/v1/integrations/allegro/import", json={})

    assert followup.status_code == 200
    assert followup.json()["created"] == 1


def test_the_suite_never_sees_a_developers_real_allegro_credentials():
    # unpatched on purpose: conftest.py blanks ALLEGRO_* so a test that forgets
    # to patch the builders cannot refresh (and so rotate) a real token
    response = client.get("/api/v1/integrations/allegro")

    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_the_import_interval_is_15_minutes_until_one_is_saved():
    response = client.get("/api/v1/integrations/schedule")

    assert response.status_code == 200
    assert response.json() == {"interval_minutes": 15}


def test_an_interval_can_be_saved_and_is_reported_by_every_channels_status():
    saved = client.put("/api/v1/integrations/schedule", json={"interval_minutes": 30})

    assert saved.status_code == 200
    assert saved.json() == {"interval_minutes": 30}
    assert client.get("/api/v1/integrations/schedule").json() == {"interval_minutes": 30}
    assert client.get("/api/v1/integrations/allegro").json()["auto_import_interval_minutes"] == 30
    assert client.get("/api/v1/integrations/erli").json()["auto_import_interval_minutes"] == 30
    # put it back for the tests after this one
    client.put("/api/v1/integrations/schedule", json={"interval_minutes": 15})


def test_zero_switches_the_schedule_off():
    client.put("/api/v1/integrations/schedule", json={"interval_minutes": 0})

    assert client.get("/api/v1/integrations/schedule").json() == {"interval_minutes": 0}
    client.put("/api/v1/integrations/schedule", json={"interval_minutes": 15})


def test_an_interval_under_five_minutes_or_beyond_a_day_is_refused():
    for minutes in (1, 4, 1441, -1):
        response = client.put("/api/v1/integrations/schedule", json={"interval_minutes": minutes})
        assert response.status_code == 422, minutes


def test_the_schedule_refuses_an_anonymous_request():
    assert anonymous.get("/api/v1/integrations/schedule").status_code == 401
    put = anonymous.put("/api/v1/integrations/schedule", json={"interval_minutes": 15})
    assert put.status_code == 401
