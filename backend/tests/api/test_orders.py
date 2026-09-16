from datetime import UTC, datetime, timedelta
from decimal import Decimal

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


def test_update_order_status():
    """PATCH /orders/{id}/status changes the status and the change persists."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="PATCH-1")
    ).json()
    assert created["status"] == "NEW"

    response = client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "SHIPPED"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "SHIPPED"
    # re-read, so this fails if the change was never committed
    assert client.get(f"/api/v1/orders/{created['id']}").json()["status"] == "SHIPPED"


def test_update_order_status_not_found():
    """PATCH /orders/{id}/status returns 404 for a non-existent id."""
    response = client.patch(
        "/api/v1/orders/00000000-0000-0000-0000-000000000000/status",
        json={"status": "SHIPPED"},
    )

    assert response.status_code == 404


def test_update_order_rejects_unknown_status():
    """PATCH /orders/{id}/status rejects a status outside the enum."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="PATCH-2")
    ).json()

    response = client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "TELEPORTED"}
    )

    assert response.status_code == 422
    assert client.get(f"/api/v1/orders/{created['id']}").json()["status"] == "NEW"


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


def test_source_and_status_filters_combine():
    """Both filters apply together, and total agrees with the returned page.

    Regression: the service used if/elif, so setting both applied only
    source to the page while counting the total with both.
    """
    client.post(
        "/api/v1/orders",
        json=_order_payload(
            external_id="COMBO-ERLI-CONFIRMED", source="ERLI", status="CONFIRMED"
        ),
    )
    client.post(
        "/api/v1/orders",
        json=_order_payload(external_id="COMBO-ERLI-NEW", source="ERLI"),
    )

    response = client.get(
        "/api/v1/orders", params={"source": "ERLI", "status": "CONFIRMED"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"], "expected at least one matching order"
    assert all(
        item["source"] == "ERLI" and item["status"] == "CONFIRMED"
        for item in data["items"]
    )
    assert data["total"] == len(data["items"])


def test_search_finds_order_outside_the_first_page():
    """search is applied by the database, not to an already-fetched page."""
    for i in range(4):
        client.post("/api/v1/orders", json=_order_payload(external_id=f"BULK-{i}"))
    client.post(
        "/api/v1/orders",
        json=_order_payload(
            external_id="NEEDLE-9999", customer_email="needle@example.com"
        ),
    )

    response = client.get("/api/v1/orders", params={"search": "NEEDLE-9999", "limit": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["external_id"] == "NEEDLE-9999"


def test_search_matches_customer_email():
    """search also matches the customer email, case-insensitively."""
    client.post(
        "/api/v1/orders",
        json=_order_payload(
            external_id="MAIL-1", customer_email="Findme@example.com"
        ),
    )

    response = client.get("/api/v1/orders", params={"search": "findme"})

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_search_escapes_like_wildcards():
    """A literal % typed into search must not match every row."""
    client.post("/api/v1/orders", json=_order_payload(external_id="NOPERCENT"))

    response = client.get("/api/v1/orders", params={"search": "%"})

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_filter_by_date_range():
    """date_from/date_to bound created_at, with date_to fully included.

    An order created today at midday must still match date_to=today, which
    a naive "created_at <= date_to" bound would cut off at midnight.
    """
    client.post("/api/v1/orders", json=_order_payload(external_id="DATE-1"))
    today = datetime.now(UTC).date()
    long_ago = (today - timedelta(days=30)).isoformat()

    inside = client.get(
        "/api/v1/orders",
        params={"date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    outside = client.get(
        "/api/v1/orders", params={"date_from": long_ago, "date_to": long_ago}
    )

    assert inside.status_code == 200
    assert inside.json()["total"] >= 1
    assert outside.status_code == 200
    assert outside.json()["total"] == 0


def test_stats_covers_all_orders_not_just_one_page():
    """GET /orders/stats aggregates the whole table.

    Regression: the dashboard derived totals from a single 100-row page.
    """
    for i in range(3):
        client.post("/api/v1/orders", json=_order_payload(external_id=f"STATS-{i}"))

    unfiltered_total = client.get("/api/v1/orders", params={"limit": 1}).json()["total"]
    response = client.get("/api/v1/orders/stats")

    assert response.status_code == 200
    stats = response.json()
    assert stats["total_orders"] == unfiltered_total
    assert stats["total_orders"] > 1
    assert sum(stats["by_status"].values()) == unfiltered_total
    assert sum(stats["by_source"].values()) == unfiltered_total
    assert Decimal(stats["total_revenue"]) > 0
