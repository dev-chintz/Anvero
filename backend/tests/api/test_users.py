from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

client = TestClient(app)

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
    """Create test database tables."""
    Base.metadata.create_all(bind=engine)


def teardown_module():
    """Drop test database tables."""
    Base.metadata.drop_all(bind=engine)


def test_register_user():
    """Test successful user registration."""
    payload = {
        "email": "test@example.com",
        "password": "TestPassword123!",
    }

    response = client.post("/api/v1/users/register", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data


def test_register_user_duplicate_email():
    """Test registration with duplicate email returns 409."""
    payload = {
        "email": "duplicate@example.com",
        "password": "TestPassword123!",
    }

    # First registration should succeed
    response = client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 200

    # Second registration with same email should fail with 409
    response = client.post("/api/v1/users/register", json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "User with this email already exists"
