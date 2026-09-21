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
    assert response.json() == {"configured": True}


def test_status_reports_configured_false(monkeypatch):
    _patch_client(monkeypatch, configured=False)

    response = client.get("/api/v1/integrations/allegro")

    assert response.status_code == 200
    assert response.json() == {"configured": False}


def test_status_never_leaks_anything_beyond_the_configured_flag(monkeypatch):
    """However AllegroClient is configured, the response must carry nothing
    that could be a credential, token or secret."""
    _patch_client(monkeypatch, configured=True)

    response = client.get("/api/v1/integrations/allegro")

    assert set(response.json().keys()) == {"configured"}


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
    assert response.json() == {"configured": False}
