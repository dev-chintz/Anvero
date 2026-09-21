"""Settings' Allegro section: the application's credentials, and connecting a
seller by the device flow, against a fake Allegro (no network)."""

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.endpoints.integrations as integrations_endpoint
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.allegro import authorization as authorization_module
from app.integrations.allegro import client as client_module
from app.main import app
from app.models.integration import IntegrationCredential, IntegrationSettings
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services import allegro_settings
from app.services.user_service import UserService

client = TestClient(app)
anonymous = TestClient(app)

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
            UserCreate(email="connection-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    """Every test starts unconfigured, with no environment credentials and no
    sign-in in progress, and never reaches the network."""
    db = TestingSessionLocal()
    db.query(IntegrationSettings).delete()
    db.query(IntegrationCredential).delete()
    db.commit()
    db.close()
    allegro_settings.flows.cancel()
    for name in ("allegro_client_id", "allegro_client_secret", "allegro_user_agent", "allegro_refresh_token"):
        monkeypatch.setattr(settings, name, "")
    monkeypatch.setattr(settings, "allegro_api_url", "https://api.allegro.pl")
    yield
    allegro_settings.flows.cancel()


class FakeAllegro:
    """Answers the device flow and /me; records what it was asked."""

    def __init__(self):
        self.token_answers = []  # popped per token poll: dict json, status
        self.requests = []
        self.login = "sandbox_seller"

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append((request.method, request.url.host, request.url.path))
        if request.url.path.endswith("/device"):
            return httpx2.Response(
                200,
                json={
                    "device_code": "dev-code",
                    "user_code": "ABCD-1234",
                    "verification_uri_complete": "https://allegro.pl.allegrosandbox.pl/auth/oauth/device?user_code=ABCD-1234",
                    "interval": 5,
                    "expires_in": 600,
                },
            )
        if request.url.path.endswith("/token"):
            body = request.content.decode()
            if "grant_type=refresh_token" in body:
                return httpx2.Response(200, json={"access_token": "acc", "expires_in": 3600, "refresh_token": "rotated-token"})
            json, code = self.token_answers.pop(0)
            return httpx2.Response(code, json=json)
        if request.url.path == "/me":
            if self.login is None:
                return httpx2.Response(403, json={})
            return httpx2.Response(200, json={"login": self.login})
        raise AssertionError(f"unexpected request {request.url}")


@pytest.fixture
def allegro(monkeypatch):
    fake = FakeAllegro()
    transport = httpx2.MockTransport(fake.handler)

    def http():
        return httpx2.Client(transport=transport)

    real_authorizer = authorization_module.AllegroDeviceAuthorizer.__init__
    real_client = client_module.AllegroClient.__init__

    def authorizer_init(self, *a, **kw):
        kw.setdefault("http_client", http())
        real_authorizer(self, *a, **kw)

    def client_init(self, *a, **kw):
        kw.setdefault("http_client", http())
        real_client(self, *a, **kw)

    monkeypatch.setattr(authorization_module.AllegroDeviceAuthorizer, "__init__", authorizer_init)
    monkeypatch.setattr(client_module.AllegroClient, "__init__", client_init)
    return fake


def _save(**overrides):
    body = {
        "client_id": "the-app",
        "client_secret": "the-secret",
        "user_agent": "anvero/1.0 (+https://example.com)",
        "environment": "sandbox",
    }
    body.update(overrides)
    return client.put("/api/v1/integrations/allegro/settings", json=body)


def _expire_poll_delay():
    flow = allegro_settings.flows._flow
    allegro_settings.flows._flow = type(flow)(
        flow_id=flow.flow_id,
        authorization=flow.authorization,
        authorizer=flow.authorizer,
        interval=flow.interval,
        next_poll_at=0.0,
        expires_at=flow.expires_at,
    )


def test_every_endpoint_refuses_an_anonymous_request():
    assert anonymous.put("/api/v1/integrations/allegro/settings", json={}).status_code == 401
    assert anonymous.post("/api/v1/integrations/allegro/connect").status_code == 401
    assert anonymous.get("/api/v1/integrations/allegro/connect/x").status_code == 401
    assert anonymous.delete("/api/v1/integrations/allegro/connection").status_code == 401


def test_nothing_is_configured_to_begin_with():
    status = client.get("/api/v1/integrations/allegro").json()

    assert status["configured"] is False
    assert status["connected"] is False
    assert status["application_complete"] is False
    assert status["source"] == "environment"


def test_saving_the_application_reports_it_without_the_secret():
    response = _save()

    assert response.status_code == 200
    body = response.json()
    assert body["client_id"] == "the-app"
    assert body["environment"] == "sandbox"
    assert body["source"] == "settings"
    assert body["application_complete"] is True
    assert "the-secret" not in response.text
    assert "client_secret" not in body


def test_the_secret_is_required_the_first_time_and_kept_when_left_blank():
    assert _save(client_secret=None).status_code == 422

    assert _save().status_code == 200
    assert _save(client_secret="", user_agent="anvero/2.0 (+https://example.com)").status_code == 200

    db = TestingSessionLocal()
    stored = db.get(IntegrationSettings, "ALLEGRO")
    assert (stored.client_secret, stored.user_agent) == ("the-secret", "anvero/2.0 (+https://example.com)")
    db.close()


def test_settings_in_the_database_win_over_the_environment(monkeypatch):
    monkeypatch.setattr(settings, "allegro_client_id", "env-app")
    _save(environment="production")

    db = TestingSessionLocal()
    application = allegro_settings.resolve_application(db)
    db.close()

    assert application.client_id == "the-app"
    assert application.api_url == "https://api.allegro.pl"
    assert application.source == "settings"


def test_connecting_without_credentials_is_refused():
    response = client.post("/api/v1/integrations/allegro/connect")

    assert response.status_code == 409


def test_connecting_stores_the_token_and_names_the_account(allegro):
    _save()

    started = client.post("/api/v1/integrations/allegro/connect").json()
    assert started["user_code"] == "ABCD-1234"
    assert started["verification_uri"].startswith("https://allegro.pl.allegrosandbox.pl/")
    assert started["flow_id"]

    allegro.token_answers.append(({"refresh_token": "granted-token", "access_token": "a"}, 200))
    _expire_poll_delay()
    polled = client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}").json()

    assert polled == {"status": "connected", "account_login": "sandbox_seller"}
    status = client.get("/api/v1/integrations/allegro").json()
    assert status["connected"] is True
    assert status["account_login"] == "sandbox_seller"
    db = TestingSessionLocal()
    # the token was spent reading /me, so what is stored is its replacement
    assert db.get(IntegrationCredential, "ALLEGRO").refresh_token == "rotated-token"
    db.close()


def test_a_connected_account_is_labelled_even_when_its_login_cannot_be_read(allegro):
    _save()
    allegro.login = None
    started = client.post("/api/v1/integrations/allegro/connect").json()
    allegro.token_answers.append(({"refresh_token": "granted-token"}, 200))
    _expire_poll_delay()

    polled = client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}").json()

    assert polled == {"status": "connected", "account_login": None}
    assert client.get("/api/v1/integrations/allegro").json()["connected"] is True


def test_polling_before_the_seller_confirms_stays_pending(allegro):
    _save()
    started = client.post("/api/v1/integrations/allegro/connect").json()
    allegro.token_answers.append(({"error": "authorization_pending"}, 400))
    _expire_poll_delay()

    polled = client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}").json()

    assert polled["status"] == "pending"
    assert client.get("/api/v1/integrations/allegro").json()["connected"] is False


def test_polling_faster_than_allegros_interval_does_not_reach_allegro(allegro):
    _save()
    started = client.post("/api/v1/integrations/allegro/connect").json()
    before = len(allegro.requests)

    for _ in range(3):
        polled = client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}").json()
        assert polled["status"] == "pending"

    assert len(allegro.requests) == before


def test_a_declined_sign_in_is_reported_and_ends_the_flow(allegro):
    _save()
    started = client.post("/api/v1/integrations/allegro/connect").json()
    allegro.token_answers.append(({"error": "access_denied"}, 400))
    _expire_poll_delay()

    response = client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}")

    assert response.status_code == 403
    assert client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}").status_code == 404


def test_an_unknown_flow_is_a_404():
    assert client.get("/api/v1/integrations/allegro/connect/nope").status_code == 404


def test_starting_again_replaces_the_flow_in_progress(allegro):
    _save()
    first = client.post("/api/v1/integrations/allegro/connect").json()
    second = client.post("/api/v1/integrations/allegro/connect").json()

    assert first["flow_id"] != second["flow_id"]
    assert client.get(f"/api/v1/integrations/allegro/connect/{first['flow_id']}").status_code == 404


def test_polling_while_an_import_runs_waits_instead_of_racing_it(allegro):
    _save()
    started = client.post("/api/v1/integrations/allegro/connect").json()
    assert integrations_endpoint._import_lock.acquire(blocking=False)
    try:
        polled = client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}")
    finally:
        integrations_endpoint._import_lock.release()

    assert polled.json()["status"] == "pending"


def test_disconnecting_forgets_the_account_but_keeps_the_application(allegro):
    _save()
    started = client.post("/api/v1/integrations/allegro/connect").json()
    allegro.token_answers.append(({"refresh_token": "granted-token"}, 200))
    _expire_poll_delay()
    client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}")

    status = client.delete("/api/v1/integrations/allegro/connection").json()

    assert status["connected"] is False
    assert status["account_login"] is None
    assert status["application_complete"] is True


def test_changing_the_client_id_or_environment_disconnects_the_account(allegro):
    _save()
    started = client.post("/api/v1/integrations/allegro/connect").json()
    allegro.token_answers.append(({"refresh_token": "granted-token"}, 200))
    _expire_poll_delay()
    client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}")
    assert client.get("/api/v1/integrations/allegro").json()["connected"] is True

    # the same application again keeps it
    _save(user_agent="anvero/1.1 (+https://example.com)")
    assert client.get("/api/v1/integrations/allegro").json()["connected"] is True

    # a token granted to another application, or in another environment, is
    # worthless to this one
    assert _save(environment="production").json()["connected"] is False


def test_connecting_forgets_where_the_last_sync_got_to(allegro):
    """A newly connected account may be another seller's."""
    from datetime import UTC, datetime

    _save()
    db = TestingSessionLocal()
    db.add(
        IntegrationCredential(
            provider="ALLEGRO",
            refresh_token="old",
            seed_fingerprint="x",
            last_synced_at=datetime.now(UTC),
        )
    )
    db.commit()
    db.close()

    started = client.post("/api/v1/integrations/allegro/connect").json()
    allegro.token_answers.append(({"refresh_token": "granted-token"}, 200))
    _expire_poll_delay()
    client.get(f"/api/v1/integrations/allegro/connect/{started['flow_id']}")

    db = TestingSessionLocal()
    assert db.get(IntegrationCredential, "ALLEGRO").last_synced_at is None
    db.close()
