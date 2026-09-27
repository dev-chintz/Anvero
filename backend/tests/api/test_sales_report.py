"""The non-invoiced sales report endpoints: reading Anvero's own orders, overriding one, exporting."""

import csv
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.order import AddressType, Order, OrderAddress, OrderSource, OrderStatus
from app.models.sales_report import SalesReportOverride
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

client = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

JUNE = {"date_from": "2026-06-01", "date_to": "2026-06-30"}


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
            UserCreate(email="sales-report-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def setup_function():
    db = TestingSessionLocal()
    try:
        db.query(SalesReportOverride).delete()
        db.query(OrderAddress).delete()
        db.query(Order).delete()
        db.commit()
    finally:
        db.close()


def _order(
    total: str,
    paid: str | None,
    status_label: str,
    invoice: dict | None = None,
    status: OrderStatus = OrderStatus.CONFIRMED,
    currency: str = "PLN",
) -> str:
    db = TestingSessionLocal()
    try:
        external_id = f"form-{uuid.uuid4()}"
        order = Order(
            external_id=external_id,
            source=OrderSource.ALLEGRO,
            status=status,
            customer_email="buyer@example.com",
            customer_login="buyer1",
            total_amount=Decimal(total),
            paid_amount=Decimal(paid) if paid is not None else None,
            currency=currency,
            ordered_at=datetime(2026, 6, 15, tzinfo=UTC),
            marketplace_status_label=status_label,
        )
        if invoice:
            order.addresses.append(OrderAddress(type=AddressType.INVOICE, **invoice))
        db.add(order)
        db.commit()
        return external_id
    finally:
        db.close()


def test_orders_classifies_a_complete_company_invoice_as_excluded():
    _order(
        "100.00",
        "100.00",
        "SENT",
        invoice={
            "company_name": "Firma sp. z o.o.",
            "street": "Kwiatowa 1",
            "postal_code": "00-001",
            "city": "Warszawa",
            "country_code": "PL",
            "tax_id": "1234567890",
        },
    )
    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {"total": 1, "retail": 0, "company": 1, "out_of_scope": 0, "manual_review": 0}
    assert body["items"][0]["category"] == "COMPANY"
    assert body["items"][0]["included"] is False
    # only the buyer's login travels with the row, never their name or address (ROADMAP.md GDPR)
    assert body["items"][0]["buyer_login"] == "buyer1"


def test_orders_classifies_cancelled_unpaid_as_out_of_scope():
    _order("50.00", "0.00", "CANCELLED")
    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    assert response.json()["items"][0]["category"] == "OUT_OF_SCOPE"


def test_orders_without_an_approved_rule_are_manual_review():
    _order("50.00", "50.00", "SENT")
    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    body = response.json()
    assert body["items"][0]["category"] == "MANUAL_REVIEW"
    assert body["items"][0]["included"] is False


def test_orders_qualifies_a_paid_shipped_uninvoiced_order_as_retail():
    _order("50.00", "50.00", "SENT", status=OrderStatus.SHIPPED)
    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    body = response.json()
    assert body["summary"] == {"total": 1, "retail": 1, "company": 0, "out_of_scope": 0, "manual_review": 0}
    row = body["items"][0]
    assert row["category"] == "RETAIL"
    assert row["included"] is True
    assert row["rule_id"] == "PAY-001"


def test_orders_does_not_qualify_as_retail_before_shipping():
    _order("50.00", "50.00", "SENT", status=OrderStatus.CONFIRMED)
    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    assert response.json()["items"][0]["category"] == "MANUAL_REVIEW"


def test_override_flips_inclusion_and_is_returned_on_the_next_read():
    external_id = _order("50.00", "50.00", "SENT")
    put = client.put(
        f"/api/v1/sales-report/orders/ALLEGRO/{external_id}/override",
        json={"included": True, "note": "Sprawdzone ręcznie z księgową"},
    )
    assert put.status_code == 200

    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    row = response.json()["items"][0]
    assert row["included"] is True
    assert row["overridden"] is True
    assert row["override_note"] == "Sprawdzone ręcznie z księgową"
    # the automatic category stays visible; the override only flips inclusion
    assert row["category"] == "MANUAL_REVIEW"


def test_override_cannot_reach_a_complete_company_invoice():
    external_id = _order(
        "100.00",
        "100.00",
        "SENT",
        invoice={
            "company_name": "Firma sp. z o.o.",
            "street": "Kwiatowa 1",
            "postal_code": "00-001",
            "city": "Warszawa",
            "country_code": "PL",
            "tax_id": "1234567890",
        },
    )
    client.put(f"/api/v1/sales-report/orders/ALLEGRO/{external_id}/override", json={"included": True})
    response = client.get("/api/v1/sales-report/orders", params=JUNE)
    row = response.json()["items"][0]
    assert row["category"] == "COMPANY"
    assert row["included"] is False
    assert row["overridden"] is False


def test_clearing_an_override_returns_to_the_automatic_decision():
    external_id = _order("50.00", "50.00", "SENT")
    client.put(f"/api/v1/sales-report/orders/ALLEGRO/{external_id}/override", json={"included": True})
    client.delete(f"/api/v1/sales-report/orders/ALLEGRO/{external_id}/override")
    row = client.get("/api/v1/sales-report/orders", params=JUNE).json()["items"][0]
    assert row["overridden"] is False
    assert row["included"] is False


def _order_with_person(first_name: str, last_name: str, paid: str = "50.00", total: str = "50.00") -> str:
    db = TestingSessionLocal()
    try:
        external_id = f"form-{uuid.uuid4()}"
        db.add(
            Order(
                external_id=external_id,
                source=OrderSource.ALLEGRO,
                status=OrderStatus.CONFIRMED,
                customer_email="buyer@example.com",
                customer_login="buyer1",
                customer_first_name=first_name,
                customer_last_name=last_name,
                total_amount=Decimal(total),
                paid_amount=Decimal(paid),
                currency="PLN",
                ordered_at=datetime(2026, 6, 15, tzinfo=UTC),
                marketplace_status_label="SENT",
            )
        )
        db.commit()
        return external_id
    finally:
        db.close()


def test_export_default_columns_are_lp_date_name_amount_paid():
    _order_with_person("Jan", "Kowalski", paid="45.50", total="50.00")
    response = client.get("/api/v1/sales-report/orders/export", params={**JUNE, "format": "csv"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(response.content.decode("utf-8-sig").splitlines()))
    assert rows[0] == ["Lp.", "Data zamówienia", "Imię i nazwisko", "Kwota zapłacona"]
    # the amount actually paid, comma decimal separator, not the amount due
    assert rows[1] == ["1", "15.06.2026", "Jan Kowalski", "45,50"]


def test_export_a_name_starting_with_a_formula_character_is_guarded():
    _order_with_person("=cmd|'/c calc'!A1", "Kowalski")
    response = client.get("/api/v1/sales-report/orders/export", params={**JUNE, "format": "csv"})
    text = response.content.decode("utf-8-sig")
    assert "'=cmd" in text


def test_export_accepts_a_chosen_column_set_and_order():
    external_id = _order_with_person("Jan", "Kowalski")
    response = client.get(
        "/api/v1/sales-report/orders/export",
        params={**JUNE, "format": "csv", "columns": "order_external_id,customer_login,amount_total,currency"},
    )
    rows = list(csv.reader(response.content.decode("utf-8-sig").splitlines()))
    assert rows[0] == ["Numer u marketplace'u", "Login", "Kwota zamówienia (razem)", "Waluta"]
    assert rows[1] == [external_id, "buyer1", "50,00", "PLN"]


def test_export_refuses_an_unknown_column():
    response = client.get("/api/v1/sales-report/orders/export", params={**JUNE, "format": "csv", "columns": "made_up"})
    assert response.status_code == 422


def test_export_refuses_a_format_not_built_yet():
    response = client.get("/api/v1/sales-report/orders/export", params={**JUNE, "format": "xlsx"})
    assert response.status_code == 422


def test_columns_catalog_lists_every_column_and_the_default_set():
    response = client.get("/api/v1/sales-report/columns")
    assert response.status_code == 200
    body = response.json()
    keys = [item["key"] for item in body["items"]]
    assert "customer_name" in keys
    assert "amount_paid" in keys
    assert body["default"] == ["lp", "ordered_at", "customer_name", "amount_paid"]
