"""The updates endpoints: an administrator's only, and honest about what they can do."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services import updates
from app.services.updates import UpdateError, UpdateState

client = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


PASSWORD = "correct-horse-battery"


def setup_module():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def _auth(role: str) -> dict[str, str]:
    from app.services.user_service import UserService

    email = f"u-{uuid.uuid4()}@example.com"
    db = TestingSessionLocal()
    try:
        UserService(UserRepository(db)).create_user(UserCreate(email=email, password=PASSWORD, role=role))
    finally:
        db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _state(monkeypatch, current="a" * 40, latest="b" * 40):
    state = UpdateState(current=current, latest=latest, behind=1)
    monkeypatch.setattr(updates, "current_state", lambda: state)
    monkeypatch.setattr(updates, "updater_status", lambda: None)
    return state


def test_only_an_administrator_sees_or_starts_updates(monkeypatch):
    _state(monkeypatch)
    headers = _auth("user")

    assert client.get("/api/v1/admin/updates", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/updates", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/updates").status_code == 401


def test_an_available_update_is_described(monkeypatch):
    _state(monkeypatch)
    monkeypatch.setattr(settings, "updater_token", "x" * 40)

    body = client.get("/api/v1/admin/updates", headers=_auth("admin")).json()

    assert body["current"] == "aaaaaaa"
    assert body["latest"] == "bbbbbbb"
    assert body["available"] is True
    assert body["can_update"] is True


def test_without_the_updater_the_button_cannot_work(monkeypatch):
    _state(monkeypatch)
    monkeypatch.setattr(settings, "updater_token", "")

    assert client.get("/api/v1/admin/updates", headers=_auth("admin")).json()["can_update"] is False


def test_starting_asks_the_updater(monkeypatch):
    _state(monkeypatch)
    asked = []
    monkeypatch.setattr(updates, "start_update", lambda: asked.append(True))

    response = client.post("/api/v1/admin/updates", headers=_auth("admin"))

    assert response.status_code == 202
    assert asked == [True]


def test_nothing_to_install_is_a_conflict(monkeypatch):
    _state(monkeypatch, latest="a" * 40)

    assert client.post("/api/v1/admin/updates", headers=_auth("admin")).status_code == 409


def test_an_updater_that_fails_is_a_bad_gateway_saying_why(monkeypatch):
    _state(monkeypatch)

    def fail():
        raise UpdateError("The updater could not be reached")

    monkeypatch.setattr(updates, "start_update", fail)

    response = client.post("/api/v1/admin/updates", headers=_auth("admin"))

    assert response.status_code == 502
    assert "could not be reached" in response.json()["detail"]


def test_health_names_the_running_commit(monkeypatch):
    monkeypatch.setattr(settings, "app_commit", "d" * 40)
    assert client.get("/api/v1/health").json()["commit"] == "ddddddd"
    monkeypatch.setattr(settings, "app_commit", "")
    assert client.get("/api/v1/health").json()["commit"] is None
