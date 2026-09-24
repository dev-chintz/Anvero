from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
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


def setup_module():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        operator = UserService(UserRepository(db)).create_user(
            UserCreate(email="status-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def test_the_status_page_needs_a_login():
    assert anonymous.get("/api/v1/status").status_code == 401


def test_the_status_reports_every_part_and_no_secret():
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    body = response.json()
    assert body["safe_mode"] is True
    assert body["checked_at"].endswith("Z")
    # the suite has no Allegro credentials and no Erli key
    assert body["allegro"]["state"] == "off"
    assert body["erli"]["state"] == "off"
    assert body["erli"]["schedule"] is None
    assert set(body["allegro"]["schedule"]) >= {"interval_minutes", "running", "next_run_at"}
    text = response.text.lower()
    assert "secret" not in text and "refresh_token" not in text
