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
