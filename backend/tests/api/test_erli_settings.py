"""Erli in Settings: the key, its check against Erli, and the import button."""

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.endpoints.integrations as integrations_endpoint
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.base import IntegrationAuthError, IntegrationError, IntegrationUnavailable
from app.main import app
from app.models.marketplace_write import AppSetting
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services import erli_settings
from app.services.user_service import UserService

client = TestClient(app)
anonymous = TestClient(app)

OPERATOR_EMAIL = "erli-settings-operator@example.com"
URL = "/api/v1/integrations/erli"

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def setup_module():
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
    Base.metadata.drop_all(bind=engine)


def setup_function():
    """Each test starts with no key entered and none in the environment."""
    db = TestingSessionLocal()
    try:
        erli_settings.clear_key(db)
    finally:
        db.close()
    settings.erli_api_key = ""


def _accepts(monkeypatch):
    checked: list[str] = []
    monkeypatch.setattr(erli_settings, "check_key", checked.append)
    return checked


def _refuses(monkeypatch, error):
    def check(api_key):
        raise error

    monkeypatch.setattr(erli_settings, "check_key", check)


@dataclass
class _Result:
    created: int
    updated: int
    cancellation_warnings: int


class _FakeService:
    def __init__(self, result=None, error=None):
        self._result, self._error, self.calls = result, error, 0

    def sync_orders(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result


def _patch_service(monkeypatch, service):
    monkeypatch.setattr(integrations_endpoint, "build_erli_import_service", lambda db: service)


def test_every_erli_endpoint_refuses_an_anonymous_request():
    assert anonymous.get(URL).status_code == 401
    assert anonymous.put(f"{URL}/settings", json={"api_key": "k"}).status_code == 401
    assert anonymous.delete(f"{URL}/settings").status_code == 401
    assert anonymous.post(f"{URL}/import").status_code == 401


def test_with_no_key_erli_is_not_configured():
    body = client.get(URL).json()

    assert body["configured"] is False
    assert body["source"] == "none"
    assert body["key_hint"] is None


def test_a_key_erli_accepts_is_saved_and_only_its_end_is_shown(monkeypatch):
    checked = _accepts(monkeypatch)

    response = client.put(f"{URL}/settings", json={"api_key": "secret-key-abcd"})

    assert response.status_code == 200
    body = response.json()
    assert (body["configured"], body["source"], body["key_hint"]) == (True, "settings", "…abcd")
    assert "secret-key-abcd" not in response.text
    assert "secret-key-abcd" not in client.get(URL).text
    assert checked == ["secret-key-abcd"]


def test_a_pasted_key_is_trimmed_before_it_is_checked_and_saved(monkeypatch):
    checked = _accepts(monkeypatch)

    client.put(f"{URL}/settings", json={"api_key": "  key-1234\n"})

    assert checked == ["key-1234"]
    db = TestingSessionLocal()
    try:
        assert db.get(AppSetting, erli_settings.KEY).value == "key-1234"
    finally:
        db.close()


def test_a_blank_key_is_refused():
    assert client.put(f"{URL}/settings", json={"api_key": "   "}).status_code == 422
    assert client.put(f"{URL}/settings", json={}).status_code == 422


def test_a_key_erli_refuses_is_not_saved(monkeypatch):
    _refuses(monkeypatch, IntegrationAuthError("Erli refused the API key (401)"))

    response = client.put(f"{URL}/settings", json={"api_key": "wrong"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Erli did not accept this API key"
    assert client.get(URL).json()["configured"] is False


def test_a_key_that_cannot_be_tried_because_erli_does_not_answer_is_not_saved(monkeypatch):
    _refuses(monkeypatch, IntegrationUnavailable("Erli unreachable"))

    response = client.put(f"{URL}/settings", json={"api_key": "some-key"})

    assert response.status_code == 502
    assert client.get(URL).json()["configured"] is False


def test_the_environments_key_applies_until_one_is_entered(monkeypatch):
    settings.erli_api_key = "env-key-9999"
    _accepts(monkeypatch)

    before = client.get(URL).json()
    client.put(f"{URL}/settings", json={"api_key": "typed-key-1111"})
    after = client.get(URL).json()

    assert (before["source"], before["key_hint"]) == ("environment", "…9999")
    assert (after["source"], after["key_hint"]) == ("settings", "…1111")


def test_forgetting_the_key_falls_back_to_the_environment(monkeypatch):
    settings.erli_api_key = "env-key-9999"
    _accepts(monkeypatch)
    client.put(f"{URL}/settings", json={"api_key": "typed-key-1111"})

    response = client.delete(f"{URL}/settings")

    assert response.status_code == 200
    assert response.json()["source"] == "environment"


def test_forgetting_a_key_that_was_never_entered_is_harmless():
    response = client.delete(f"{URL}/settings")

    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_the_import_button_returns_the_counts(monkeypatch):
    fake = _FakeService(result=_Result(created=3, updated=1, cancellation_warnings=0))
    _patch_service(monkeypatch, fake)

    response = client.post(f"{URL}/import")

    assert response.status_code == 200
    assert response.json() == {"created": 3, "updated": 1, "cancellation_warnings": 0}
    assert fake.calls == 1


def test_an_import_with_no_key_is_reported_as_409():
    response = client.post(f"{URL}/import")

    assert response.status_code == 409
    assert response.json()["detail"] == "Erli is not configured"


def test_an_import_erli_fails_is_reported_as_502(monkeypatch):
    _patch_service(monkeypatch, _FakeService(error=IntegrationError("Erli returned 503")))

    response = client.post(f"{URL}/import")

    assert response.status_code == 502
    assert "503" in response.json()["detail"]


def test_an_erli_import_waits_for_a_running_allegro_one(monkeypatch):
    fake = _FakeService(result=_Result(created=1, updated=0, cancellation_warnings=0))
    _patch_service(monkeypatch, fake)

    assert integrations_endpoint._import_lock.acquire(blocking=False)
    try:
        response = client.post(f"{URL}/import")
    finally:
        integrations_endpoint._import_lock.release()

    assert response.status_code == 409
    assert fake.calls == 0
