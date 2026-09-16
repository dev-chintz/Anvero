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


def _order_payload(**overrides):
    payload = {
        "external_id": "ALG-1001",
        "source": "ALLEGRO",
        "customer_email": "buyer@example.com",
        "total_amount": "129.99",
        "currency": "PLN",
    }
    payload.update(overrides)
    return payload


def test_list_orders_empty():
    """GET /orders returns 200 with an empty list when no orders exist."""
    response = client.get("/api/v1/orders")

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_order():
    """POST /orders creates an order and returns it."""
    payload = _order_payload()

    response = client.post("/api/v1/orders", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["external_id"] == payload["external_id"]
    assert data["source"] == "ALLEGRO"
    assert data["status"] == "NEW"
    assert data["customer_email"] == payload["customer_email"]
    assert data["currency"] == "PLN"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_get_order_by_id():
    """GET /orders/{id} returns the previously created order."""
    payload = _order_payload(external_id="ALG-1002")
    create_response = client.post("/api/v1/orders", json=payload)
    order_id = create_response.json()["id"]

    response = client.get(f"/api/v1/orders/{order_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == order_id
    assert data["external_id"] == "ALG-1002"


def test_get_order_not_found():
    """GET /orders/{id} returns 404 for a non-existent id."""
    response = client.get("/api/v1/orders/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_filter_orders_by_source():
    """GET /orders?source=ALLEGRO returns only orders from that source."""
    client.post("/api/v1/orders", json=_order_payload(external_id="ERLI-1"))
    client.post(
        "/api/v1/orders",
        json=_order_payload(external_id="ERLI-2", source="ERLI"),
    )

    response = client.get("/api/v1/orders", params={"source": "ERLI"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert all(item["source"] == "ERLI" for item in data["items"])


def test_filter_orders_by_status():
    """GET /orders?status=NEW returns only orders with that status."""
    client.post("/api/v1/orders", json=_order_payload(external_id="STATUS-1"))

    response = client.get("/api/v1/orders", params={"status": "NEW"})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert all(item["status"] == "NEW" for item in data["items"])


def test_pagination():
    """skip/limit params correctly page through the order list."""
    for i in range(5):
        client.post(
            "/api/v1/orders",
            json=_order_payload(external_id=f"PAGE-{i}"),
        )

    page_one = client.get("/api/v1/orders", params={"skip": 0, "limit": 2})
    page_two = client.get("/api/v1/orders", params={"skip": 2, "limit": 2})

    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert len(page_one.json()["items"]) == 2
    assert len(page_two.json()["items"]) == 2

    page_one_ids = {item["id"] for item in page_one.json()["items"]}
    page_two_ids = {item["id"] for item in page_two.json()["items"]}
    assert page_one_ids.isdisjoint(page_two_ids)
