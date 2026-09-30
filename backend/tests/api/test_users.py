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
from app.schemas.user import PermissionGrant, UserCreate
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


def _create_user(
    active: bool = True,
    role: str | None = None,
    permissions: list[PermissionGrant] | None = None,
) -> str:
    email = f"user-{uuid.uuid4()}@example.com"
    db = TestingSessionLocal()
    try:
        data = {"email": email, "password": PASSWORD}
        if role is not None:
            data["role"] = role
        if permissions is not None:
            data["permissions"] = permissions
        user = UserService(UserRepository(db)).create_user(UserCreate(**data))
        if not active:
            user.is_active = False
            db.commit()
    finally:
        db.close()
    return email


def _login(email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _token(email: str, password: str = PASSWORD) -> str:
    return _login(email, password).json()["access_token"]


def _auth(email: str, password: str = PASSWORD) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(email, password)}"}


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


def _user_id(email: str) -> int:
    db = TestingSessionLocal()
    try:
        return db.query(User).filter(User.email == email).one().id
    finally:
        db.close()


def test_a_new_password_logs_out_the_tokens_issued_before_it():
    """Without it a token taken with the old password lived out its eight hours."""
    admin_email = _create_user(role="admin")
    email = _create_user()
    old_token = _token(email)

    response = client.patch(
        f"/api/v1/users/{_user_id(email)}",
        headers=_auth(admin_email),
        json={"password": "a-brand-new-password"},
    )

    assert response.status_code == 200
    old = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old.status_code == 401
    assert client.get("/api/v1/users/me", headers=_auth(email, "a-brand-new-password")).status_code == 200


def test_an_admin_changing_a_role_does_not_log_the_user_out():
    admin_email = _create_user(role="admin")
    email = _create_user(role="user")
    token = _token(email)

    client.patch(f"/api/v1/users/{_user_id(email)}", headers=_auth(admin_email), json={"role": "admin"})

    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_the_reset_password_script_logs_out_the_old_sessions():
    email = _create_user()
    old_token = _token(email)

    result = _run_reset_password(email, "a-brand-new-password")

    assert result.returncode == 0, result.stderr
    old = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old.status_code == 401


def test_a_token_from_before_versions_existed_still_works():
    """Tokens issued before the upgrade carry no version; nobody is logged out by it."""
    email = _create_user()
    token = jwt.encode(
        {"sub": str(_user_id(email)), "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.secret_key,
        algorithm="HS256",
    )

    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_a_malformed_token_is_a_401_not_a_500():
    for claims in ({"sub": "not-a-number"}, {"sub": "1", "ver": "x"}):
        token = jwt.encode(
            {**claims, "exp": datetime.now(UTC) + timedelta(hours=1)},
            settings.secret_key,
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
        check=False,
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
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert _login(email, "powershell-piped-password").status_code == 200


def _run_reset_password(email: str, password: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/reset_password.py", email],
        input=password + "\n",
        capture_output=True,
        text=True,
        cwd=BACKEND_DIR,
        timeout=60,
        check=False,
    )


def test_reset_password_script_replaces_the_password():
    email = _create_user()

    result = _run_reset_password(email, "a-brand-new-password")

    assert result.returncode == 0, result.stderr
    assert _login(email, "a-brand-new-password").status_code == 200
    assert _login(email, PASSWORD).status_code == 401


def test_reset_password_script_rejects_an_unknown_email():
    result = _run_reset_password(f"nobody-{uuid.uuid4()}@example.com", "a-perfectly-good-password")

    assert result.returncode == 1
    assert "No user" in result.stderr


def test_reset_password_script_rejects_a_short_password_and_keeps_the_old_one():
    email = _create_user()

    result = _run_reset_password(email, "short-pw")

    assert result.returncode == 1
    assert "short-pw" not in result.stdout + result.stderr
    assert _login(email, PASSWORD).status_code == 200


def test_create_user_script_rejects_a_short_password_without_echoing_it():
    email = f"scripted-{uuid.uuid4()}@example.com"

    result = _run_create_user(email, "short-pw")

    assert result.returncode == 1
    assert "short-pw" not in result.stdout + result.stderr
    assert _login(email, "short-pw").status_code == 401


# ---- roles and permissions ------------------------------------------------


def test_a_user_with_no_grants_is_refused_a_gated_area():
    email = _create_user(role="user")

    response = client.get("/api/v1/orders", headers=_auth(email))

    assert response.status_code == 403


def test_a_view_grant_allows_reading_but_not_managing():
    email = _create_user(
        role="user",
        permissions=[PermissionGrant(area="orders", level="view")],
    )
    headers = _auth(email)

    assert client.get("/api/v1/orders", headers=headers).status_code == 200
    assert (
        client.put(
            "/api/v1/orders/production/checks",
            headers=headers,
            json={"key": "sku:X", "quantity": 1, "done": True},
        ).status_code
        == 403
    )


def test_asking_allegro_again_about_a_label_or_pickup_needs_manage():
    """Both write what Allegro answers, as the InPost refresh does, which needed manage already."""
    email = _create_user(role="user", permissions=[PermissionGrant(area="labels", level="view")])
    headers = _auth(email)

    label = client.post(f"/api/v1/orders/{uuid.uuid4()}/labels/{uuid.uuid4()}/refresh", headers=headers)
    pickup = client.post(f"/api/v1/pickups/{uuid.uuid4()}/refresh", headers=headers)

    assert label.status_code == 403
    assert pickup.status_code == 403


def test_a_manage_grant_satisfies_a_view_requirement_too():
    email = _create_user(
        role="user",
        permissions=[PermissionGrant(area="orders", level="manage")],
    )

    assert client.get("/api/v1/orders", headers=_auth(email)).status_code == 200


def test_a_grant_on_one_area_does_not_reach_another():
    email = _create_user(
        role="user",
        permissions=[PermissionGrant(area="orders", level="manage")],
    )

    assert client.get("/api/v1/messages/threads", headers=_auth(email)).status_code == 403


def test_an_admin_needs_no_grants():
    email = _create_user(role="admin")

    assert client.get("/api/v1/orders", headers=_auth(email)).status_code == 200


def test_only_an_admin_may_list_or_create_users():
    admin_email = _create_user(role="admin")
    plain_email = _create_user(role="user")

    assert client.get("/api/v1/users", headers=_auth(admin_email)).status_code == 200
    assert client.get("/api/v1/users", headers=_auth(plain_email)).status_code == 403

    new_email = f"created-{uuid.uuid4()}@example.com"
    response = client.post(
        "/api/v1/users",
        headers=_auth(admin_email),
        json={"email": new_email, "password": "a-perfectly-good-password", "role": "user"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"
    assert response.json()["permissions"] == []


def test_creating_a_user_with_an_existing_email_is_a_conflict():
    admin_email = _create_user(role="admin")
    existing_email = _create_user(role="user")

    response = client.post(
        "/api/v1/users",
        headers=_auth(admin_email),
        json={"email": existing_email, "password": "a-perfectly-good-password"},
    )

    assert response.status_code == 409


def test_an_admin_can_grant_and_later_revoke_a_permission():
    admin_email = _create_user(role="admin")
    plain_email = _create_user(role="user")
    db = TestingSessionLocal()
    try:
        user_id = db.query(User).filter(User.email == plain_email).one().id
    finally:
        db.close()

    granted = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_auth(admin_email),
        json={"permissions": [{"area": "orders", "level": "view"}]},
    )
    assert granted.status_code == 200
    assert client.get("/api/v1/orders", headers=_auth(plain_email)).status_code == 200

    revoked = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_auth(admin_email),
        json={"permissions": []},
    )
    assert revoked.status_code == 200
    assert client.get("/api/v1/orders", headers=_auth(plain_email)).status_code == 403


def _make_the_only_active_admin(email: str) -> int:
    """Every earlier test in this module may have left admin accounts behind
    (the module shares one database), so the last-admin guard is only
    meaningfully tested once every other admin is out of the count."""
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one()
        db.query(User).filter(User.role == "admin", User.id != user.id).update(
            {"is_active": False}
        )
        db.commit()
        return user.id
    finally:
        db.close()


def test_replacing_permissions_while_keeping_some_of_the_same_areas():
    """Regression: clearing and re-adding a kept area in the same request collided
    on (user_id, area) before the old row was gone."""
    admin_email = _create_user(role="admin")
    plain_email = _create_user(
        role="user",
        permissions=[
            PermissionGrant(area="orders", level="manage"),
            PermissionGrant(area="messages", level="view"),
        ],
    )
    db = TestingSessionLocal()
    try:
        user_id = db.query(User).filter(User.email == plain_email).one().id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_auth(admin_email),
        json={
            "permissions": [
                {"area": "orders", "level": "manage"},
                {"area": "messages", "level": "view"},
                {"area": "finance", "level": "view"},
            ]
        },
    )

    assert response.status_code == 200
    assert {(p["area"], p["level"]) for p in response.json()["permissions"]} == {
        ("orders", "manage"),
        ("messages", "view"),
        ("finance", "view"),
    }


def test_the_last_active_admin_cannot_be_demoted():
    email = _create_user(role="admin")
    user_id = _make_the_only_active_admin(email)

    response = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_auth(email),
        json={"role": "user"},
    )

    assert response.status_code == 409


def test_the_last_active_admin_cannot_be_deactivated():
    email = _create_user(role="admin")
    user_id = _make_the_only_active_admin(email)

    response = client.patch(
        f"/api/v1/users/{user_id}",
        headers=_auth(email),
        json={"is_active": False},
    )

    assert response.status_code == 409


def test_demoting_one_of_two_admins_is_allowed():
    first_admin = _create_user(role="admin")
    second_email = _create_user(role="admin")
    db = TestingSessionLocal()
    try:
        second_id = db.query(User).filter(User.email == second_email).one().id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/users/{second_id}",
        headers=_auth(first_admin),
        json={"role": "user"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "user"
