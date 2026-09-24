"""InPost over HTTP: the connection in Settings, and shipments made and printed.
InPost itself is a fake, so nothing here reaches the network."""

import itertools
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.main import app
from app.models.order import (
    AddressType,
    Order,
    OrderAddress,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.repositories.order_repository import OrderRepository
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services import inpost_settings, inpost_shipments
from app.services.marketplace_writes import set_safe_mode
from app.services.user_service import UserService

client = TestClient(app)
anonymous = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TOKEN = "sandbox-token-1234567890"


# InPost's ids are never reused, and the database outlives one test
_INPOST_IDS = itertools.count(9001)


class FakeInpost:
    def __init__(self):
        self.created = []
        self.cancelled = []
        self.labels = []

    def create_shipment(self, payload):
        self.created.append(payload)
        return {"id": next(_INPOST_IDS), "status": "created", "tracking_number": None}

    def get_shipment(self, shipment_id):
        return {"id": shipment_id, "status": "confirmed", "tracking_number": f"620000000000000{shipment_id:>09}"}

    def cancel_shipment(self, shipment_id):
        self.cancelled.append(shipment_id)

    def fetch_labels(self, ids, label_type="A6"):
        self.labels.append((list(ids), label_type))
        return b"%PDF-1.4 fake"


class StubOrderWrites:
    def __init__(self, db):
        self.db = db

    def add_shipment(self, order, carrier_id, carrier_name, waybill, user_id):
        return OrderRepository(self.db).add_shipment(order, carrier_id, carrier_name, waybill), None


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
            UserCreate(email="inpost-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def inpost(monkeypatch):
    """A fake InPost in place of the real one, settings saved, and safe mode off."""
    fake = FakeInpost()
    monkeypatch.setattr(inpost_shipments, "build_inpost_client", lambda db: fake)
    monkeypatch.setattr(inpost_shipments, "OrderWrites", StubOrderWrites)
    monkeypatch.setattr(inpost_shipments, "SETTLE_INTERVAL_SECONDS", 0)
    db = TestingSessionLocal()
    try:
        inpost_settings.save_settings(db, TOKEN, "777", "sandbox", "small", None)
        set_safe_mode(db, False, None)
        yield fake
    finally:
        set_safe_mode(db, True, None)
        inpost_settings.clear_settings(db)
        db.close()


def _order(**overrides) -> str:
    db = TestingSessionLocal()
    try:
        fields = {
            "external_id": f"inpost-{uuid.uuid4()}",
            "source": OrderSource.ALLEGRO,
            "status": OrderStatus.CONFIRMED,
            "customer_email": "buyer@user.allegromail.pl",
            "customer_first_name": "Anna",
            "customer_last_name": "Nowak",
            "total_amount": Decimal("45.00"),
            "currency": "PLN",
            "delivery_method": "Allegro Paczkomaty InPost",
            "pickup_point_id": "KRA010",
            "pickup_point_name": "Paczkomat KRA010",
            "payment_type": PaymentType.ONLINE,
            "paid_amount": Decimal("45.00"),
        }
        fields.update(overrides)
        order = Order(**fields)
        order.addresses.append(
            OrderAddress(type=AddressType.DELIVERY, first_name="Anna", last_name="Nowak", phone="600100200")
        )
        db.add(order)
        db.commit()
        return str(order.id)
    finally:
        db.close()


# --- the connection ------------------------------------------------------------------------


def test_everything_here_needs_a_login():
    some_id = "00000000-0000-0000-0000-000000000000"
    requests = [
        ("get", "/api/v1/integrations/inpost", None),
        ("put", "/api/v1/integrations/inpost/settings", {"organization_id": "1", "token": TOKEN}),
        ("delete", "/api/v1/integrations/inpost/settings", None),
        ("get", f"/api/v1/orders/{some_id}/inpost-shipments", None),
        ("post", f"/api/v1/orders/{some_id}/inpost-shipments", {}),
        ("get", "/api/v1/inpost/orders", None),
        ("post", "/api/v1/inpost/shipments", {"order_ids": [some_id]}),
        ("get", "/api/v1/inpost/labels", None),
        ("post", "/api/v1/inpost/labels/pdf", {"shipment_ids": [some_id]}),
    ]
    for method, path, body in requests:
        response = getattr(anonymous, method)(path, **({"json": body} if body is not None else {}))
        assert response.status_code == 401, f"{method.upper()} {path}"


def test_a_fresh_install_is_not_configured_and_uses_the_sandbox():
    body = client.get("/api/v1/integrations/inpost").json()

    assert body == {
        "configured": False,
        "environment": "sandbox",
        "organization_id": None,
        "token_hint": None,
        "default_template": "small",
    }


def test_settings_are_saved_once_inpost_accepts_them_and_the_token_is_never_sent_back(monkeypatch):
    asked = []
    monkeypatch.setattr(inpost_settings, "check", lambda *args: asked.append(args) or {"id": 777})
    try:
        response = client.put(
            "/api/v1/integrations/inpost/settings",
            json={"token": TOKEN, "organization_id": "777", "environment": "production", "default_template": "medium"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert (body["environment"], body["organization_id"], body["default_template"]) == ("production", "777", "medium")
        assert body["token_hint"] == "…7890"
        assert TOKEN not in response.text
        assert asked == [(TOKEN, "777", "production")]
        assert TOKEN not in client.get("/api/v1/integrations/inpost").text
    finally:
        client.delete("/api/v1/integrations/inpost/settings")


def test_a_token_inpost_refuses_is_not_saved(monkeypatch):
    def refuse(*args):
        raise IntegrationAuthError("InPost refused the token")

    monkeypatch.setattr(inpost_settings, "check", refuse)

    response = client.put("/api/v1/integrations/inpost/settings", json={"token": TOKEN, "organization_id": "777"})

    assert response.status_code == 422
    assert "did not accept" in response.json()["detail"]
    assert client.get("/api/v1/integrations/inpost").json()["configured"] is False


def test_an_unreachable_inpost_is_a_bad_gateway_and_nothing_is_saved(monkeypatch):
    def down(*args):
        raise IntegrationUnavailable("InPost is unreachable")

    monkeypatch.setattr(inpost_settings, "check", down)

    response = client.put("/api/v1/integrations/inpost/settings", json={"token": TOKEN, "organization_id": "777"})

    assert response.status_code == 502
    assert client.get("/api/v1/integrations/inpost").json()["configured"] is False


def test_the_token_can_be_left_out_to_keep_the_saved_one(monkeypatch):
    asked = []
    monkeypatch.setattr(inpost_settings, "check", lambda *args: asked.append(args) or {})
    client.put("/api/v1/integrations/inpost/settings", json={"token": TOKEN, "organization_id": "777"})
    try:
        response = client.put(
            "/api/v1/integrations/inpost/settings",
            json={"organization_id": "888", "environment": "production"},
        )

        assert response.status_code == 200
        assert response.json()["organization_id"] == "888"
        # the saved token is what InPost was asked about
        assert asked[-1] == (TOKEN, "888", "production")
    finally:
        client.delete("/api/v1/integrations/inpost/settings")


def test_without_a_saved_token_one_must_be_given(monkeypatch):
    monkeypatch.setattr(inpost_settings, "check", lambda *args: {})

    response = client.put("/api/v1/integrations/inpost/settings", json={"organization_id": "777"})

    assert response.status_code == 422


def test_a_bad_organization_id_is_refused():
    response = client.put("/api/v1/integrations/inpost/settings", json={"token": TOKEN, "organization_id": "abc"})

    assert response.status_code == 422


def test_the_default_size_can_be_changed_alone(inpost):
    response = client.put("/api/v1/integrations/inpost/template", json={"default_template": "large"})

    assert response.status_code == 200
    assert response.json()["default_template"] == "large"
    assert client.put("/api/v1/integrations/inpost/template", json={"default_template": "huge"}).status_code == 422


def test_forgetting_the_settings_removes_the_token(inpost):
    response = client.delete("/api/v1/integrations/inpost/settings")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["token_hint"] is None


# --- one order ---------------------------------------------------------------------------------


def test_a_parcel_is_made_for_an_order_and_its_number_comes_back(inpost):
    order_id = _order()

    response = client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["shipment"]["status"] == "confirmed"
    assert body["shipment"]["tracking_number"].startswith("620000000000000")
    assert body["shipment"]["target_point"] == "KRA010"
    assert body["marketplace_write"]["outcome"] == "SENT"
    assert inpost.created[0]["custom_attributes"] == {"target_point": "KRA010"}
    # the number is on the order, as an InPost parcel
    shipments = client.get(f"/api/v1/orders/{order_id}").json()["shipments"]
    assert [s["carrier_id"] for s in shipments] == ["INPOST"]
    assert client.get(f"/api/v1/orders/{order_id}/inpost-shipments").json()[0]["id"] == body["shipment"]["id"]


def test_the_size_can_be_chosen_when_the_parcel_is_made(inpost):
    order_id = _order()

    client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={"template": "large"})

    assert inpost.created[0]["parcels"] == {"template": "large"}


def test_with_safe_mode_on_nothing_is_sent_and_the_answer_says_so(inpost):
    db = TestingSessionLocal()
    set_safe_mode(db, True, None)
    db.close()
    order_id = _order()

    response = client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["shipment"] is None
    assert body["marketplace_write"]["outcome"] == "DRY_RUN"
    assert inpost.created == []


def test_an_order_that_cannot_get_a_parcel_is_a_conflict_with_the_reason(inpost):
    order_id = _order(delivery_method="Allegro Automat ORLEN Paczka")

    response = client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={})

    assert response.status_code == 409
    assert "not a delivery to an InPost parcel locker" in response.json()["detail"]
    assert inpost.created == []


def test_without_settings_the_answer_says_to_enter_them():
    order_id = _order()

    response = client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={})

    assert response.status_code == 409
    assert "Settings" in response.json()["detail"]


def test_a_deleted_order_gets_no_parcel(inpost):
    order_id = _order()
    client.delete(f"/api/v1/orders/{order_id}")

    response = client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={})

    assert response.status_code == 409
    assert inpost.created == []


def test_an_unknown_order_is_not_found(inpost):
    assert client.post(f"/api/v1/orders/{uuid.uuid4()}/inpost-shipments", json={}).status_code == 404


def test_a_shipment_can_be_looked_at_again_and_cancelled(inpost):
    order_id = _order()
    shipment = client.post(f"/api/v1/orders/{order_id}/inpost-shipments", json={}).json()["shipment"]

    refreshed = client.post(f"/api/v1/orders/{order_id}/inpost-shipments/{shipment['id']}/refresh")
    cancelled = client.post(f"/api/v1/orders/{order_id}/inpost-shipments/{shipment['id']}/cancel")

    assert refreshed.status_code == 200
    assert refreshed.json()["shipment"]["status"] == "confirmed"
    assert cancelled.status_code == 200
    assert cancelled.json()["shipment"]["status"] == "cancelled"
    assert inpost.cancelled == [shipment["inpost_id"]]
    again = client.post(f"/api/v1/orders/{order_id}/inpost-shipments/{shipment['id']}/cancel")
    assert again.status_code == 409


def test_another_orders_shipment_is_not_found_under_this_one(inpost):
    first = _order()
    other = _order()
    shipment = client.post(f"/api/v1/orders/{first}/inpost-shipments", json={}).json()["shipment"]

    response = client.post(f"/api/v1/orders/{other}/inpost-shipments/{shipment['id']}/cancel")

    assert response.status_code == 404


# --- many at once ---------------------------------------------------------------------------------


def test_the_orders_waiting_for_a_parcel_are_listed(inpost):
    wanted = _order(external_id=f"wait-{uuid.uuid4()}")
    _order(delivery_method="Allegro Automat ORLEN Paczka")

    listed = client.get("/api/v1/inpost/orders").json()

    ids = [o["id"] for o in listed]
    assert wanted in ids
    entry = next(o for o in listed if o["id"] == wanted)
    assert entry["target_point"] == "KRA010"
    assert entry["buyer"] == "Anna Nowak"
    assert entry["order_label"].startswith("AN-")
    assert entry["status"] == "CONFIRMED"


def test_a_batch_makes_a_parcel_for_each_order_and_says_what_became_of_each(inpost):
    good = _order()
    orlen = _order(delivery_method="Allegro Automat ORLEN Paczka")
    also_good = _order()

    response = client.post("/api/v1/inpost/shipments", json={"order_ids": [good, orlen, also_good, good]})

    assert response.status_code == 200
    items = response.json()["items"]
    # a repeated order is asked once
    assert [i["outcome"] for i in items] == ["created", "refused", "created"]
    assert items[1]["message"]
    assert items[0]["shipment"]["tracking_number"]
    assert len(inpost.created) == 2


def test_a_batch_needs_one_to_fifty_orders():
    assert client.post("/api/v1/inpost/shipments", json={"order_ids": []}).status_code == 422
    too_many = [str(uuid.uuid4()) for _ in range(51)]
    assert client.post("/api/v1/inpost/shipments", json={"order_ids": too_many}).status_code == 422


def test_a_batch_with_an_unknown_order_is_not_found(inpost):
    assert client.post("/api/v1/inpost/shipments", json={"order_ids": [str(uuid.uuid4())]}).status_code == 404


# --- printing ----------------------------------------------------------------------------------------


def test_labels_to_print_are_listed_and_printed_together_as_one_pdf(inpost):
    made = [
        client.post(f"/api/v1/orders/{_order()}/inpost-shipments", json={}).json()["shipment"] for _ in range(2)
    ]
    ids = [m["id"] for m in made]

    waiting = client.get("/api/v1/inpost/labels").json()
    assert set(ids) <= {w["id"] for w in waiting}
    assert all(w["order_label"].startswith("AN-") for w in waiting)

    response = client.post("/api/v1/inpost/labels/pdf", json={"shipment_ids": ids})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert inpost.labels[-1] == ([m["inpost_id"] for m in made], "A6")
    # printed now: no longer among those to print, but still among the printed
    after = {w["id"] for w in client.get("/api/v1/inpost/labels").json()}
    printed = {w["id"] for w in client.get("/api/v1/inpost/labels", params={"printed": "true"}).json()}
    assert not set(ids) & after
    assert set(ids) <= printed


def test_printing_an_unknown_label_is_not_found_and_nothing_chosen_is_refused(inpost):
    assert client.post("/api/v1/inpost/labels/pdf", json={"shipment_ids": [str(uuid.uuid4())]}).status_code == 404
    assert client.post("/api/v1/inpost/labels/pdf", json={"shipment_ids": []}).status_code == 422
