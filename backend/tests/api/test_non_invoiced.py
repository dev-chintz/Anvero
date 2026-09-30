"""The non-invoiced sales record's endpoints (docs/API.md, "Non-invoiced sales record"): a range's
report, the exports, handing over, overrides."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.non_invoiced import (
    HandedOverReport,
    HandedOverReportRow,
    LedgerEntry,
    LedgerKind,
)
from app.models.order import OrderSource
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

client = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SEPTEMBER = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


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
            UserCreate(email="record-keeper@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def setup_function():
    db = TestingSessionLocal()
    try:
        db.query(HandedOverReportRow).delete()
        db.query(HandedOverReport).delete()
        db.query(LedgerEntry).delete()
        db.commit()
    finally:
        db.close()


_numbers = iter(range(1, 1_000_000))


def _entry(category="EXEMPT_MAIL_ORDER", reason="E41", amount="120.00", day=14, **changes) -> uuid.UUID:
    db = TestingSessionLocal()
    try:
        number = next(_numbers)
        entry = LedgerEntry(
            kind=LedgerKind.SALE,
            event_key=f"ORDER:form-{number}",
            entry_at=datetime(2026, 9, day, 10, 0, tzinfo=UTC),
            entry_date=date(2026, 9, day),
            source=OrderSource.ALLEGRO,
            order_external_id=f"form-{number}",
            order_number=number,
            amount=Decimal(amount),
            currency="PLN",
            buyer_first_name="Jan",
            buyer_last_name="Kowalski",
            buyer_street="Lipowa 3",
            buyer_postal_code="80-001",
            buyer_city="Gdańsk",
            payment_operator="P24",
            operation_fingerprint=f"fp-{number}",
            category=category,
            reason=reason,
            ruleset="poz41-2024/2",
        )
        for key, value in changes.items():
            setattr(entry, key, value)
        db.add(entry)
        db.commit()
        return entry.id
    finally:
        db.close()


def test_a_range_says_what_it_lists_and_what_it_counts_apart():
    listed = _entry()
    _entry(category="BUSINESS", reason="COMPANY", amount="80.00", day=15)

    response = client.get("/api/v1/non-invoiced/report", params=SEPTEMBER)

    assert response.status_code == 200
    body = response.json()
    assert body["listed"] == [str(listed)]
    assert Decimal(body["total"]) == Decimal("120.00")
    row = next(r for r in body["rows"] if r["id"] == str(listed))
    assert (row["buyer_name"], row["buyer_address"], row["in_report"], row["order_label"]) == (
        "Jan Kowalski",
        "Lipowa 3, 80-001 Gdańsk",
        True,
        row["order_label"],
    )
    business = next(t for t in body["totals"] if t["category"] == "BUSINESS")
    assert (business["sales"], Decimal(business["sales_amount"])) == (1, Decimal("80.00"))
    assert (body["ended"], body["can_hand_over"]) == (True, True)


def test_a_range_ends_before_it_begins_is_refused():
    assert client.get("/api/v1/non-invoiced/report", params={"date_from": "2026-09-30", "date_to": "2026-09-01"}).status_code == 422


def test_the_exports_come_in_three_formats():
    _entry()
    expected = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
    }
    for fmt, media_type in expected.items():
        response = client.get("/api/v1/non-invoiced/export", params={**SEPTEMBER, "format": fmt})
        assert response.status_code == 200, fmt
        assert response.headers["content-type"].startswith(media_type)
        assert f"ewidencja-bezrachunkowa-2026-09-01-2026-09-30.{fmt}" in response.headers["content-disposition"]


def test_an_unknown_format_or_column_is_refused():
    assert client.get("/api/v1/non-invoiced/export", params={**SEPTEMBER, "format": "doc"}).status_code == 422
    assert client.get("/api/v1/non-invoiced/export", params={**SEPTEMBER, "columns": "lp,nope"}).status_code == 422


def test_the_columns_offered_start_with_the_accountants_default():
    body = client.get("/api/v1/non-invoiced/columns").json()

    assert body["default"] == ["lp", "entry_date", "buyer_name", "amount"]
    assert {c["key"]: c["personal"] for c in body["items"]}["buyer_address"] is True


def test_handing_over_once_and_only_once():
    _entry()

    first = client.post("/api/v1/non-invoiced/reports", json=SEPTEMBER)
    second = client.post("/api/v1/non-invoiced/reports", json=SEPTEMBER)

    assert first.status_code == 201
    assert (first.json()["row_count"], Decimal(first.json()["total"])) == (1, Decimal("120.00"))
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ALREADY_HANDED_OVER"
    (listed,) = client.get("/api/v1/non-invoiced/reports").json()
    assert listed["handed_over_by"] == "record-keeper@example.com"
    again = client.get(f"/api/v1/non-invoiced/reports/{listed['id']}/export", params={"format": "csv"})
    assert again.status_code == 200
    assert "120,00" in again.content.decode("utf-8-sig")


def test_a_sale_to_decide_stops_the_hand_over():
    _entry(category="TO_REVIEW", reason="CANCELLED_AFTER_PAYMENT")

    response = client.post("/api/v1/non-invoiced/reports", json=SEPTEMBER)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "TO_REVIEW"


def test_an_override_is_set_with_a_reason_and_taken_back():
    entry = _entry(category="TO_REVIEW", reason="CANCELLED_AFTER_PAYMENT")
    url = f"/api/v1/non-invoiced/entries/{entry}/override"

    assert client.put(url, json={"category": "TO_REVIEW", "note": "?"}).status_code == 422
    set_ = client.put(url, json={"category": "NOT_A_SALE", "note": "Zwrócone w całości"})
    assert set_.status_code == 200
    assert set_.json()["by"] == "record-keeper@example.com"
    row = next(r for r in client.get("/api/v1/non-invoiced/report", params=SEPTEMBER).json()["rows"] if r["id"] == str(entry))
    assert (row["category"], row["automatic_category"], row["override"]["note"]) == ("NOT_A_SALE", "TO_REVIEW", "Zwrócone w całości")

    assert client.delete(url).status_code == 200
    row = next(r for r in client.get("/api/v1/non-invoiced/report", params=SEPTEMBER).json()["rows"] if r["id"] == str(entry))
    assert (row["category"], row["override"]) == ("TO_REVIEW", None)


def test_a_company_sale_cannot_be_overridden():
    entry = _entry(category="BUSINESS", reason="COMPANY")

    response = client.put(f"/api/v1/non-invoiced/entries/{entry}/override", json={"category": "EXEMPT_MAIL_ORDER", "note": "?"})

    assert response.status_code == 422


def test_an_unknown_row_is_not_found():
    response = client.put(f"/api/v1/non-invoiced/entries/{uuid.uuid4()}/override", json={"category": "NOT_A_SALE", "note": "x"})

    assert response.status_code == 404
