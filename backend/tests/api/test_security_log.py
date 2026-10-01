"""The security log: logins, refusals, the rate limit, and changes to accounts (docs/GDPR.md).

What it must do is as much about what it leaves out as what it says: no e-mail, no password, and
nothing a stranger types can start a line of its own.
"""

import logging
import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import security_log
from app.core.config import settings
from app.core.rate_limit import route_template
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

client = TestClient(app)
admin = TestClient(app)

PASSWORD = "operator-password-123"

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

boss_id: int


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_module():
    global boss_id
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        boss = UserService(UserRepository(db)).create_user(UserCreate(email="log-admin@example.com", password=PASSWORD))
        boss_id = boss.id
        admin.headers["Authorization"] = f"Bearer {create_access_token(boss.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def log(caplog):
    caplog.set_level(logging.INFO, logger="security")
    return caplog


def lines(log) -> list[str]:
    return [record.getMessage() for record in log.records if record.name == "security"]


def levels(log) -> list[int]:
    return [record.levelno for record in log.records if record.name == "security"]


def make_user(active: bool = True) -> tuple[int, str]:
    email = f"log-{uuid.uuid4()}@example.com"
    db = TestingSessionLocal()
    try:
        user = UserService(UserRepository(db)).create_user(UserCreate(email=email, password=PASSWORD, role="user"))
        if not active:
            user.is_active = False
            db.commit()
        return user.id, email
    finally:
        db.close()


def login(email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# --- logging in ---------------------------------------------------------------------------------


def test_a_login_is_logged_with_the_account_and_where_it_came_from(log):
    user_id, email = make_user()
    log.clear()

    assert login(email).status_code == 200

    assert lines(log) == [f"login_succeeded user={user_id} ip=testclient"]
    assert levels(log) == [logging.INFO]


def test_a_wrong_password_is_logged_as_a_warning_naming_the_account(log):
    user_id, email = make_user()
    log.clear()

    assert login(email, "not-the-password-at-all").status_code == 401

    assert lines(log) == [f"login_failed reason=wrong_password user={user_id} ip=testclient"]
    assert levels(log) == [logging.WARNING]


def test_a_switched_off_account_is_told_from_a_wrong_password_in_the_log_only(log):
    user_id, email = make_user(active=False)
    log.clear()

    response = login(email)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert lines(log) == [f"login_failed reason=account_inactive user={user_id} ip=testclient"]


def test_an_unknown_account_is_logged_without_anything_that_was_typed(log):
    typed_email = f"nobody-{uuid.uuid4()}@example.com"
    typed_password = "a-password-typed-into-the-wrong-field"

    response = login(typed_email, typed_password)

    assert response.status_code == 401
    assert lines(log) == ["login_failed reason=unknown_account ip=testclient"]
    assert typed_email not in log.text and typed_password not in log.text


def test_no_e_mail_and_no_password_reaches_the_log_whatever_the_outcome(log):
    user_id, email = make_user()
    login(email)
    login(email, "wrong-password-123")

    assert email not in log.text
    assert PASSWORD not in log.text and "wrong-password-123" not in log.text


def test_the_refused_logins_are_answered_alike(log):
    _, email = make_user()
    _, off = make_user(active=False)

    answers = {
        (r.status_code, r.text)
        for r in (login(email, "wrong-password-123"), login(off), login(f"nobody-{uuid.uuid4()}@example.com"))
    }

    assert len(answers) == 1


def test_a_burst_of_logins_is_logged_when_the_rate_limit_stops_it(log):
    _, email = make_user()
    log.clear()

    statuses = [login(email, "wrong-password-123").status_code for _ in range(8)]

    assert 429 in statuses
    limited = [line for line in lines(log) if line.startswith("rate_limited")]
    assert len(limited) == statuses.count(429)
    assert limited[0] == "rate_limited ip=testclient method=POST route=/api/v1/auth/login limit=5_per_1_minute"
    assert logging.WARNING in levels(log)


def _request(path: str, path_params: dict) -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "path_params": path_params, "headers": []})


def test_the_route_is_logged_with_a_path_parameter_named_not_copied():
    assert route_template(_request("/api/v1/auth/login", {})) == "/api/v1/auth/login"
    assert (
        route_template(_request("/api/v1/integrations/allegro/connect/9f8e7d", {"flow_id": "9f8e7d"}))
        == "/api/v1/integrations/allegro/connect/{flow_id}"
    )


def test_an_order_numbered_one_does_not_turn_the_v1_of_the_prefix_into_a_parameter():
    assert route_template(_request("/api/v1/orders/1", {"order_id": 1})) == "/api/v1/orders/{order_id}"


# --- changes to accounts ------------------------------------------------------------------------


def test_an_administrator_making_an_account_is_logged_with_who_and_which(log):
    email = f"log-{uuid.uuid4()}@example.com"

    response = admin.post("/api/v1/users", json={"email": email, "password": PASSWORD, "role": "user"})

    assert response.status_code == 201
    assert lines(log) == [f"account_created actor={boss_id} user={response.json()['id']} role=user"]
    assert email not in log.text and PASSWORD not in log.text


def test_a_refused_account_is_not_logged_as_made(log):
    _, email = make_user()
    log.clear()

    response = admin.post("/api/v1/users", json={"email": email, "password": PASSWORD, "role": "user"})

    assert response.status_code == 409
    assert lines(log) == []


def test_a_change_of_role_and_state_is_logged_by_name_and_new_value(log):
    user_id, _ = make_user()
    log.clear()

    response = admin.patch(f"/api/v1/users/{user_id}", json={"role": "admin", "is_active": False})

    assert response.status_code == 200
    assert lines(log) == [f"account_changed actor={boss_id} user={user_id} changes=role,active role=admin active=false"]


def test_a_new_password_is_logged_as_a_change_and_never_as_a_value(log):
    user_id, _ = make_user()
    log.clear()

    response = admin.patch(f"/api/v1/users/{user_id}", json={"password": "a-brand-new-password-456"})

    assert response.status_code == 200
    assert lines(log) == [f"account_changed actor={boss_id} user={user_id} changes=password"]
    assert "a-brand-new-password-456" not in log.text


def test_permissions_are_logged_as_changed_without_listing_them(log):
    user_id, _ = make_user()
    log.clear()

    admin.patch(f"/api/v1/users/{user_id}", json={"permissions": [{"area": "orders", "level": "view"}]})

    assert lines(log) == [f"account_changed actor={boss_id} user={user_id} changes=permissions"]


def test_a_request_that_changes_nothing_is_not_logged(log):
    user_id, _ = make_user()
    log.clear()

    response = admin.patch(f"/api/v1/users/{user_id}", json={"role": "user", "is_active": True})

    assert response.status_code == 200
    assert lines(log) == []


def test_a_change_to_an_account_that_does_not_exist_is_not_logged(log):
    response = admin.patch("/api/v1/users/999999", json={"is_active": False})

    assert response.status_code == 404
    assert lines(log) == []


def test_what_a_script_does_on_the_server_is_logged_as_the_console(log):
    db = TestingSessionLocal()
    try:
        service = UserService(UserRepository(db))
        email = f"log-{uuid.uuid4()}@example.com"
        created = service.create_user(UserCreate(email=email, password=PASSWORD, role="user"))
        service.set_password(email, "a-reset-password-789")
    finally:
        db.close()

    assert lines(log) == [
        f"account_created actor=console user={created.id} role=user",
        f"account_changed actor=console user={created.id} changes=password",
    ]
    assert "a-reset-password-789" not in log.text


# --- the line itself ----------------------------------------------------------------------------


def test_nothing_a_value_holds_can_start_a_line_of_its_own(log):
    security_log.record("probe", reason="a\nlogin_succeeded user=1\r\nb", ip="10.0.0.1\x1b[31m x")

    [line] = lines(log)
    assert line == "probe reason=a_login_succeeded_user=1_b ip=10.0.0.1[31m_x"
    assert "\n" not in line and "\r" not in line and "\x1b" not in line and " " not in line


def test_a_field_that_is_none_is_left_out_and_an_empty_one_is_a_dash(log):
    security_log.record("probe", user=None, reason="")

    assert lines(log) == ["probe reason=-"]


def test_a_long_value_is_cut(log):
    security_log.record("probe", ip="1" * 500)

    assert lines(log) == ["probe ip=" + "1" * 64]
