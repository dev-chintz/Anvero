"""The GDPR page's API: who the data controller is, and the retention periods."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.marketplace_write import AppSetting
from app.repositories.user_repository import UserRepository
from app.schemas.user import PermissionGrant, UserCreate
from app.services import retention
from app.services.user_service import UserService

admin = TestClient(app)
member = TestClient(app)
anonymous = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

FULL = {
    "name": "Anvero Test sp. z o.o.",
    "tax_id": "1234567890",
    "address": "ul. Prosta 1, 00-001 Warszawa",
    "email": "rodo@example.com",
    "phone": "+48 123 456 789",
    "dpo_contact": "iod@example.com",
}


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
        service = UserService(UserRepository(db))
        boss = service.create_user(UserCreate(email="gdpr-admin@example.com", password="operator-password-123"))
        admin.headers["Authorization"] = f"Bearer {create_access_token(boss.id)}"
        other = service.create_user(
            UserCreate(
                email="gdpr-member@example.com",
                password="operator-password-123",
                role="user",
                permissions=[PermissionGrant(area="labels", level="view")],
            )
        )
        member.headers["Authorization"] = f"Bearer {create_access_token(other.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def setup_function():
    db = TestingSessionLocal()
    try:
        db.query(AppSetting).filter(AppSetting.key == "gdpr_controller").delete()
        db.commit()
    finally:
        db.close()


def test_the_page_needs_a_login():
    assert anonymous.get("/api/v1/gdpr/overview").status_code == 401
    assert anonymous.put("/api/v1/gdpr/controller", json=FULL).status_code == 401


def test_nothing_is_known_of_the_controller_until_it_is_entered():
    body = admin.get("/api/v1/gdpr/overview").json()

    assert body["controller"] == {
        "name": None,
        "tax_id": None,
        "address": None,
        "email": None,
        "phone": None,
        "dpo_contact": None,
        "updated_at": None,
    }


def test_the_retention_periods_are_the_ones_the_erasure_uses():
    body = admin.get("/api/v1/gdpr/overview").json()

    assert body["retention"] == {
        "orders_years": retention.ORDER_RETENTION_YEARS,
        "contacts_years": retention.CONTACT_RETENTION_YEARS,
    }


def test_an_administrator_saves_who_the_controller_is():
    response = admin.put("/api/v1/gdpr/controller", json=FULL)

    assert response.status_code == 200
    saved = response.json()
    assert {key: saved[key] for key in FULL} == FULL
    assert saved["updated_at"] is not None
    assert admin.get("/api/v1/gdpr/overview").json()["controller"]["name"] == "Anvero Test sp. z o.o."


def test_everyone_logged_in_can_read_it_but_only_an_administrator_can_change_it():
    admin.put("/api/v1/gdpr/controller", json=FULL)

    assert member.get("/api/v1/gdpr/overview").json()["controller"]["email"] == "rodo@example.com"
    assert member.put("/api/v1/gdpr/controller", json={"name": "Someone else"}).status_code == 403
    assert admin.get("/api/v1/gdpr/overview").json()["controller"]["name"] == "Anvero Test sp. z o.o."


def test_a_field_left_blank_is_cleared_and_spaces_are_tidied():
    admin.put("/api/v1/gdpr/controller", json=FULL)

    saved = admin.put(
        "/api/v1/gdpr/controller",
        json={"name": "  Anvero   Test  ", "tax_id": "   ", "address": "", "email": None},
    ).json()

    assert saved["name"] == "Anvero Test"
    assert (saved["tax_id"], saved["address"], saved["email"], saved["phone"], saved["dpo_contact"]) == (None,) * 5


def test_saving_again_replaces_what_was_saved_before():
    admin.put("/api/v1/gdpr/controller", json=FULL)
    admin.put("/api/v1/gdpr/controller", json={"name": "Second"})

    saved = admin.get("/api/v1/gdpr/overview").json()["controller"]

    assert saved["name"] == "Second" and saved["email"] is None


@pytest.mark.parametrize("email", ["no-at-sign", "a b@example.com", "@example.com", "name@"])
def test_an_e_mail_that_is_not_one_is_refused(email):
    assert admin.put("/api/v1/gdpr/controller", json={"email": email}).status_code == 422


@pytest.mark.parametrize("field, length", [("name", 201), ("tax_id", 33), ("address", 301), ("email", 201), ("phone", 41), ("dpo_contact", 201)])
def test_a_text_too_long_is_refused(field, length):
    value = "a@b.pl" + "x" * (length - 6) if field == "email" else "x" * length

    assert admin.put("/api/v1/gdpr/controller", json={field: value}).status_code == 422


def test_what_is_saved_but_unreadable_is_shown_as_nothing_rather_than_failing():
    db = TestingSessionLocal()
    db.add(AppSetting(key="gdpr_controller", value="not json at all"))
    db.commit()
    db.close()

    assert admin.get("/api/v1/gdpr/overview").json()["controller"]["name"] is None
    # and saving over it works
    assert admin.put("/api/v1/gdpr/controller", json=FULL).status_code == 200
