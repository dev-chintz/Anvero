import uuid
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
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services import shipping_labels
from app.services.user_service import UserService

client = TestClient(app)
anonymous = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SENDER = {
    "name": "Jan Kowalski",
    "company": None,
    "street": "Długa 1",
    "postal_code": "00-001",
    "city": "Warszawa",
    "country_code": "PL",
    "email": "sklep@example.com",
    "phone": "500600700",
}
PACKAGE = {"length_cm": "30", "width_cm": "20", "height_cm": "10", "weight_kg": "1.5"}


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
            UserCreate(email="shipping-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def _order() -> str:
    db = TestingSessionLocal()
    try:
        order = Order(
            external_id=f"form-{uuid.uuid4()}",
            source=OrderSource.ALLEGRO,
            status=OrderStatus.CONFIRMED,
            customer_email="buyer@example.com",
            total_amount=Decimal("10.00"),
            currency="PLN",
        )
        order.addresses = [
            OrderAddress(type=AddressType.DELIVERY, first_name="Anna", street="Krótka 2",
                         postal_code="30-001", city="Kraków", country_code="PL")
        ]
        db.add(order)
        db.commit()
        return str(order.id)
    finally:
        db.close()


class _Allegro:
    def fetch_checkout_form(self, checkout_form_id):
        return {"delivery": {"method": {"id": "method-1"}}}


def test_labels_and_their_settings_need_a_login():
    assert anonymous.get("/api/v1/settings/shipping").status_code == 401
    assert anonymous.get(f"/api/v1/orders/{uuid.uuid4()}/labels").status_code == 401


def test_the_shipping_settings_round_trip():
    assert client.get("/api/v1/settings/shipping").json() == {"sender": None, "default_package": None}

    response = client.put(
        "/api/v1/settings/shipping", json={"sender": SENDER, "default_package": PACKAGE}
    )

    assert response.status_code == 200
    assert response.json()["sender"]["city"] == "Warszawa"
    assert Decimal(response.json()["default_package"]["weight_kg"]) == Decimal("1.5")


def test_a_malformed_sender_is_refused():
    response = client.put(
        "/api/v1/settings/shipping", json={"sender": {**SENDER, "email": "not an email"}}
    )
    assert response.status_code == 422


def test_in_safe_mode_buying_only_records_what_would_be_sent(monkeypatch):
    client.put("/api/v1/settings/shipping", json={"sender": SENDER, "default_package": PACKAGE})
    monkeypatch.setattr(shipping_labels, "build_allegro_client", lambda db: _Allegro())
    order_id = _order()

    response = client.post(f"/api/v1/orders/{order_id}/labels", json=PACKAGE)

    assert response.status_code == 200
    body = response.json()
    assert body["label"] is None
    assert body["marketplace_write"]["outcome"] == "DRY_RUN"
    assert '"deliveryMethodId": "method-1"' in body["marketplace_write"]["payload"]
    assert client.get(f"/api/v1/orders/{order_id}/labels").json() == []


def test_without_a_sender_buying_is_a_conflict():
    client.put("/api/v1/settings/shipping", json={"sender": None, "default_package": None})

    response = client.post(f"/api/v1/orders/{_order()}/labels", json=PACKAGE)

    assert response.status_code == 409
    assert "sender" in response.json()["detail"]


def test_an_unknown_label_is_not_found():
    response = client.get(f"/api/v1/orders/{_order()}/labels/{uuid.uuid4()}/pdf")
    assert response.status_code == 404


def test_the_print_list_needs_a_login_and_starts_empty():
    assert anonymous.get("/api/v1/labels").status_code == 401
    assert client.get("/api/v1/labels").json() == []


def test_printing_an_unknown_label_is_not_found():
    response = client.post("/api/v1/labels/pdf", json={"label_ids": [str(uuid.uuid4())]})
    assert response.status_code == 404


def test_printing_nothing_is_refused():
    assert client.post("/api/v1/labels/pdf", json={"label_ids": []}).status_code == 422


def test_pickups_need_a_login():
    body = {"label_ids": [str(uuid.uuid4())], "ready_date": "2099-01-01"}
    assert anonymous.post("/api/v1/pickups/proposals", json=body).status_code == 401
    assert anonymous.post(f"/api/v1/pickups/{uuid.uuid4()}/refresh").status_code == 401


def test_proposals_for_an_unknown_parcel_are_not_found():
    body = {"label_ids": [str(uuid.uuid4())], "ready_date": "2099-01-01"}
    assert client.post("/api/v1/pickups/proposals", json=body).status_code == 404


def test_a_pickup_needs_a_day():
    body = {"label_ids": [str(uuid.uuid4())], "proposal_id": "p", "proposal_label": "p"}
    assert client.post("/api/v1/pickups", json=body).status_code == 422


def test_the_label_list_takes_known_views_only():
    assert client.get("/api/v1/labels?view=no_pickup").status_code == 200
    assert client.get("/api/v1/labels?view=all").status_code == 200
    assert client.get("/api/v1/labels?view=whatever").status_code == 422


def test_refreshing_an_unknown_pickup_is_not_found():
    assert client.post(f"/api/v1/pickups/{uuid.uuid4()}/refresh").status_code == 404


def test_the_test_label_needs_a_login():
    assert anonymous.get("/api/v1/labels/test-pdf").status_code == 401


def test_the_test_label_is_a_pdf_and_touches_no_marketplace(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the test label must not reach Allegro")

    monkeypatch.setattr(shipping_labels, "build_allegro_client", refuse)
    client.put("/api/v1/settings/shipping", json={"sender": SENDER, "default_package": PACKAGE})

    response = client.get("/api/v1/labels/test-pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="test-label.pdf"'
    assert response.content.startswith(b"%PDF-1.4")
    # the sender saved in Settings is on it, without its Polish letters
    assert b"(Dluga 1)" in response.content
    assert b"(Jan Kowalski)" in response.content


def test_an_order_with_a_bought_label_cannot_be_deleted():
    from datetime import UTC, datetime

    from app.models.shipping_label import LabelStatus, ShippingLabel

    order_id = _order()
    db = TestingSessionLocal()
    try:
        db.add(
            ShippingLabel(
                order_id=uuid.UUID(order_id),
                created_at=datetime.now(UTC),
                command_id=f"cmd-{uuid.uuid4()}",
                shipment_id="ship-1",
                status=LabelStatus.CREATED,
                delivery_method_id="method-1",
                length_cm=Decimal(30),
                width_cm=Decimal(20),
                height_cm=Decimal(10),
                weight_kg=Decimal("1.5"),
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == 409
    assert "label" in response.json()["detail"]
    assert client.get(f"/api/v1/orders/{order_id}").json()["deleted_at"] is None


def test_an_order_cannot_be_given_a_label_once_deleted():
    order_id = _order()
    assert client.delete(f"/api/v1/orders/{order_id}").status_code == 200

    response = client.post(f"/api/v1/orders/{order_id}/labels", json=PACKAGE)

    assert response.status_code == 409
    assert "restore" in response.json()["detail"]
