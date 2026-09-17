import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

client = TestClient(app)

SQLALCHEMY_DATABASE_URL = settings.database_url
BACKEND_DIR = Path(__file__).resolve().parents[2]

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

PASSWORD = "correct-horse-battery"


def setup_module():
    """Create test database tables."""
    Base.metadata.create_all(bind=engine)


def teardown_module():
    """Drop test database tables."""
    Base.metadata.drop_all(bind=engine)


def _create_user(active: bool = True) -> str:
    email = f"user-{uuid.uuid4()}@example.com"
    db = TestingSessionLocal()
    try:
        user = UserService(UserRepository(db)).create_user(
            UserCreate(email=email, password=PASSWORD)
        )
        if not active:
            user.is_active = False
            db.commit()
    finally:
        db.close()
    return email


def _login(email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_registration_endpoint_does_not_exist():
    """Accounts are created by script; an open endpoint would let anyone who
    can reach the API give themselves a login."""
    response = client.post(
        "/api/v1/users/register",
        json={"email": "intruder@example.com", "password": "a-long-enough-password"},
    )

    assert response.status_code in (404, 405)


def test_login_returns_a_token_that_identifies_the_user():
    email = _create_user()

    token = _login(email).json()["access_token"]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["email"] == email


def test_wrong_password_is_rejected():
    email = _create_user()

    response = _login(email, "wrong-password-entirely")

    assert response.status_code == 401


def test_unknown_email_gets_the_same_answer_as_a_wrong_password():
    """A different answer would tell an attacker which emails have accounts."""
    email = _create_user()

    wrong_password = _login(email, "wrong-password-entirely")
    unknown_email = _login(f"nobody-{uuid.uuid4()}@example.com", "wrong-password-entirely")

    assert unknown_email.status_code == wrong_password.status_code == 401
    assert unknown_email.json() == wrong_password.json()


def test_inactive_user_cannot_log_in():
    """Regression: a deactivated account received a token at login."""
    email = _create_user(active=False)

    response = _login(email)

    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_users_me_requires_a_token():
    assert client.get("/api/v1/users/me").status_code == 401


def test_token_lasts_the_configured_working_day():
    email = _create_user()
    token = _login(email).json()["access_token"]

    claims = jwt.decode(token, options={"verify_signature": False})

    assert claims["exp"] - claims["iat"] == settings.access_token_expire_minutes * 60
    assert settings.access_token_expire_minutes == 480


def test_expired_token_is_rejected():
    email = _create_user()
    db = TestingSessionLocal()
    try:
        user_id = db.query(User).filter(User.email == email).one().id
    finally:
        db.close()
    past = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(user_id), "iat": past - timedelta(hours=8), "exp": past},
        settings.secret_key,
        algorithm="HS256",
    )

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_signed_with_another_key_is_rejected():
    """What a forged token looks like when the real key is not guessable."""
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "CHANGE_ME",
        algorithm="HS256",
    )

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def _run_create_user(email: str, password: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/create_user.py", email],
        input=password + "\n",
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        timeout=60,
    )


def test_create_user_script_makes_an_account_that_can_log_in():
    email = f"scripted-{uuid.uuid4()}@example.com"

    result = _run_create_user(email, "a-perfectly-good-password")

    assert result.returncode == 0, result.stderr
    assert _login(email, "a-perfectly-good-password").status_code == 200


def test_create_user_script_ignores_the_bom_powershell_adds_to_piped_input():
    """Regression: `"password" | python create_user.py` in Windows PowerShell
    sends a UTF-8 byte-order mark first. It was stored as part of the password,
    so the account could never be logged into."""
    email = f"piped-{uuid.uuid4()}@example.com"

    result = subprocess.run(
        [sys.executable, "scripts/create_user.py", email],
        input=b"\xef\xbb\xbfpowershell-piped-password\r\n",
        capture_output=True,
        cwd=BACKEND_DIR,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert _login(email, "powershell-piped-password").status_code == 200


def test_create_user_script_rejects_a_short_password_without_echoing_it():
    email = f"scripted-{uuid.uuid4()}@example.com"

    result = _run_create_user(email, "short-pw")

    assert result.returncode == 1
    assert "short-pw" not in result.stdout + result.stderr
    assert _login(email, "short-pw").status_code == 401
