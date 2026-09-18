from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

# `client` acts as a logged-in operator (see setup_module); `anonymous` never
# sends a token, to prove the endpoints refuse it
client = TestClient(app)
anonymous = TestClient(app)

OPERATOR_EMAIL = "operator@example.com"

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
    """Create test database tables and log the test client in."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        operator = UserService(UserRepository(db)).create_user(
            UserCreate(email=OPERATOR_EMAIL, password="operator-password-123")
        )
        # minted directly rather than through /auth/login: login has its own
        # tests, and this module is about what a logged-in user can do
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


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


def test_every_order_endpoint_refuses_an_anonymous_request():
    """Regression: the orders API was open to anyone who could reach it."""
    some_id = "00000000-0000-0000-0000-000000000000"
    requests = [
        ("get", "/api/v1/orders", None),
        ("get", "/api/v1/orders/stats", None),
        ("get", f"/api/v1/orders/{some_id}", None),
        ("get", f"/api/v1/orders/{some_id}/history", None),
        ("patch", f"/api/v1/orders/{some_id}/status", {"status": "SHIPPED"}),
        ("post", "/api/v1/orders", _order_payload(external_id="ANON-1")),
    ]

    for method, path, body in requests:
        response = getattr(anonymous, method)(path, **({"json": body} if body else {}))
        assert response.status_code == 401, f"{method.upper()} {path}"


def test_health_stays_public():
    assert anonymous.get("/api/v1/health").status_code == 200


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


def test_duplicate_order_from_the_same_source_is_rejected():
    """A marketplace order number may only appear once per marketplace.

    Without this an import re-run would insert a second copy of every order.
    """
    payload = _order_payload(external_id="DUP-1")
    first = client.post("/api/v1/orders", json=payload)

    second = client.post("/api/v1/orders", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    listed = client.get("/api/v1/orders", params={"search": "DUP-1"}).json()
    assert listed["total"] == 1


def test_same_external_id_from_different_sources_is_allowed():
    """Order numbers collide across marketplaces; that is not a duplicate."""
    allegro = client.post(
        "/api/v1/orders", json=_order_payload(external_id="SHARED-1")
    )
    erli = client.post(
        "/api/v1/orders",
        json=_order_payload(external_id="SHARED-1", source="ERLI"),
    )

    assert allegro.status_code == 200
    assert erli.status_code == 200
    listed = client.get("/api/v1/orders", params={"search": "SHARED-1"}).json()
    assert listed["total"] == 2


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


def test_status_change_is_recorded_in_history():
    """Each transition appends a row naming both ends of the move."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="HIST-1")
    ).json()

    client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "CONFIRMED"}
    )
    client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "SHIPPED"}
    )

    response = client.get(f"/api/v1/orders/{created['id']}/history")

    assert response.status_code == 200
    history = response.json()
    assert len(history) == 2
    # most recent first
    assert history[0]["from_status"] == "CONFIRMED"
    assert history[0]["to_status"] == "SHIPPED"
    assert history[1]["from_status"] == "NEW"
    assert history[1]["to_status"] == "CONFIRMED"


def test_history_records_who_made_the_change():
    """Deferred until logins existed; see DECISIONS.md."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="HIST-AUTHOR")
    ).json()

    client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "CONFIRMED"}
    )
    history = client.get(f"/api/v1/orders/{created['id']}/history").json()

    assert history[0]["changed_by"] == OPERATOR_EMAIL


def test_history_is_empty_for_an_unchanged_order():
    """An order still in its original status has no transitions."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="HIST-2")
    ).json()

    response = client.get(f"/api/v1/orders/{created['id']}/history")

    assert response.status_code == 200
    assert response.json() == []


def test_setting_the_same_status_records_nothing():
    """Re-sending the current status is a no-op, not a logged transition."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="HIST-3")
    ).json()

    response = client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "NEW"}
    )

    assert response.status_code == 200
    assert client.get(f"/api/v1/orders/{created['id']}/history").json() == []


def test_history_for_unknown_order_is_404():
    """An unknown id is distinguishable from an order that never moved."""
    response = client.get(
        "/api/v1/orders/00000000-0000-0000-0000-000000000000/history"
    )

    assert response.status_code == 404


def test_rejected_status_change_records_nothing():
    """A status outside the enum leaves neither the order nor the log changed."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="HIST-4")
    ).json()

    client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "TELEPORTED"}
    )

    assert client.get(f"/api/v1/orders/{created['id']}").json()["status"] == "NEW"
    assert client.get(f"/api/v1/orders/{created['id']}/history").json() == []


def _flag_cancelled_on_marketplace(order_id):
    """Stand in for an import: no endpoint sets this, only the importer."""
    import uuid as _uuid

    from app.models.order import Order

    db = TestingSessionLocal()
    try:
        order = db.get(Order, _uuid.UUID(order_id))
        order.marketplace_cancelled_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def test_cancellation_warnings_are_filterable_counted_and_resolvable():
    """The filter, the dashboard count and the detail field agree, and the
    warning clears once the operator cancels the order in Anvero."""
    flagged = client.post(
        "/api/v1/orders", json=_order_payload(external_id="WARN-1")
    ).json()
    client.post("/api/v1/orders", json=_order_payload(external_id="WARN-QUIET"))
    _flag_cancelled_on_marketplace(flagged["id"])

    listed = client.get(
        "/api/v1/orders", params={"cancellation_warning": "true"}
    ).json()
    stats = client.get("/api/v1/orders/stats").json()
    detail = client.get(f"/api/v1/orders/{flagged['id']}").json()

    assert [item["external_id"] for item in listed["items"]] == ["WARN-1"]
    assert listed["total"] == 1
    assert stats["cancellation_warnings"] == 1
    assert detail["marketplace_cancelled_at"] is not None
    assert detail["status"] == "NEW"

    client.patch(
        f"/api/v1/orders/{flagged['id']}/status", json={"status": "CANCELLED"}
    )

    assert (
        client.get("/api/v1/orders", params={"cancellation_warning": "true"}).json()[
            "total"
        ]
        == 0
    )
    assert client.get("/api/v1/orders/stats").json()["cancellation_warnings"] == 0


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
    """date_from/date_to bound ordered_at, with date_to fully included.

    An order placed today at midday must still match date_to=today, which
    a naive "ordered_at <= date_to" bound would cut off at midnight.
    """
    client.post("/api/v1/orders", json=_order_payload(external_id="DATE-1"))
    # "today" in the business timezone, as the filter reads it; UTC's today
    # is a different date for two hours every night and would make this flaky
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
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


def test_timestamps_leave_the_api_marked_as_utc():
    """Regression: SQLite returns naive timestamps, which went out without a
    zone and were read by browsers as local time, two hours off in Poland."""
    order = client.post(
        "/api/v1/orders", json=_order_payload(external_id="TZ-1")
    ).json()
    client.patch(f"/api/v1/orders/{order['id']}/status", json={"status": "SHIPPED"})

    fetched = client.get(f"/api/v1/orders/{order['id']}").json()
    history = client.get(f"/api/v1/orders/{order['id']}/history").json()

    for field in ("ordered_at", "created_at", "updated_at"):
        assert fetched[field].endswith("Z"), f"{field}: {fetched[field]}"
    assert history[0]["changed_at"].endswith("Z")


def test_date_filter_uses_calendar_days_in_the_business_timezone():
    """23:30 UTC on 10 March is 00:30 on 11 March in Warsaw, so it belongs to
    the 11th. A UTC day boundary put it on the 10th."""
    client.post(
        "/api/v1/orders",
        json=_order_payload(
            external_id="TZ-MIDNIGHT", ordered_at="2026-03-10T23:30:00Z"
        ),
    )

    on_11th = client.get(
        "/api/v1/orders", params={"date_from": "2026-03-11", "date_to": "2026-03-11"}
    ).json()
    on_10th = client.get(
        "/api/v1/orders", params={"date_from": "2026-03-10", "date_to": "2026-03-10"}
    ).json()

    assert [o["external_id"] for o in on_11th["items"]] == ["TZ-MIDNIGHT"]
    assert on_10th["total"] == 0


def test_orders_are_listed_by_order_date_not_creation_time():
    """An order imported today but placed years ago belongs at the bottom."""
    client.post("/api/v1/orders", json=_order_payload(external_id="SORT-RECENT"))
    client.post(
        "/api/v1/orders",
        json=_order_payload(
            external_id="SORT-OLD", ordered_at="2020-01-01T12:00:00Z"
        ),
    )

    listed = client.get("/api/v1/orders", params={"search": "SORT-"}).json()

    assert [o["external_id"] for o in listed["items"]] == ["SORT-RECENT", "SORT-OLD"]


def test_this_week_counts_orders_placed_this_week_not_created_this_week():
    """Regression: a backfill of old orders made every one of them count as
    'this week', because the figure used the import time."""
    before = client.get("/api/v1/orders/stats").json()
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    client.post(
        "/api/v1/orders",
        json=_order_payload(external_id="OLD-BACKFILL", ordered_at=thirty_days_ago),
    )
    after = client.get("/api/v1/orders/stats").json()

    assert after["total_orders"] == before["total_orders"] + 1
    assert after["this_week"] == before["this_week"]


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


# --- order details ---------------------------------------------------------


def _details_payload(**overrides):
    details = {
        "customer": {"first_name": "Jan", "last_name": "Kowalski", "phone": "+48 600 100 200"},
        "items": [
            {
                "name": "Widget",
                "sku": "SKU-W1",
                "quantity": 2,
                "unit_price": "76.00",
                "image_url": "https://a.allegroimg.com/original/widget.jpg",
            },
            {"name": "Gadget", "quantity": 1, "unit_price": "15.99"},
        ],
        "delivery": {
            "method": "InPost Paczkomat",
            "cost": "12.99",
            "address": {"first_name": "Anna", "street": "Prosta 1", "city": "Warszawa"},
            "pickup_point": {
                "id": "WAW01A",
                "name": "Paczkomat WAW01A",
                "address": {"street": "Długa 5", "postal_code": "00-002"},
            },
        },
        "payment": {
            "type": "ONLINE",
            "provider": "P24",
            "paid_amount": "180.98",
            "paid_at": "2026-09-14T10:01:00Z",
        },
        "invoice": {"required": True, "address": {"company_name": "Firma", "tax_id": "1234563218"}},
        "buyer_message": "Please pack it well",
        "seller_note": "Regular customer, ship first",
    }
    details.update(overrides)
    return _order_payload(**details)


def test_an_order_returns_its_details():
    created = client.post(
        "/api/v1/orders", json=_details_payload(external_id="DETAILS-1")
    ).json()

    response = client.get(f"/api/v1/orders/{created['id']}")

    assert response.status_code == 200
    order = response.json()
    assert order["customer"]["last_name"] == "Kowalski"
    assert order["customer"]["login"] is None
    assert order["items"][0]["image_url"] == "https://a.allegroimg.com/original/widget.jpg"
    assert order["items"][1]["image_url"] is None
    assert [(i["name"], i["quantity"], i["unit_price"]) for i in order["items"]] == [
        ("Widget", 2, "76.00"),
        ("Gadget", 1, "15.99"),
    ]
    assert all(item["id"] for item in order["items"])
    assert order["delivery"]["method"] == "InPost Paczkomat"
    assert order["delivery"]["cost"] == "12.99"
    assert order["delivery"]["address"]["street"] == "Prosta 1"
    assert order["delivery"]["pickup_point"]["id"] == "WAW01A"
    assert order["delivery"]["pickup_point"]["address"]["street"] == "Długa 5"
    assert order["payment"] == {
        "type": "ONLINE",
        "provider": "P24",
        "paid_amount": "180.98",
        "paid_at": "2026-09-14T10:01:00Z",
    }
    assert order["invoice"]["required"] is True
    assert order["invoice"]["address"]["tax_id"] == "1234563218"
    assert order["buyer_message"] == "Please pack it well"
    assert order["seller_note"] == "Regular customer, ship first"


def test_the_list_already_carries_the_buyer_name_and_payment_method():
    """No join needed for these: they are flat columns on `orders` already,
    unlike items, so the list can show them without extra query cost."""
    client.post("/api/v1/orders", json=_details_payload(external_id="LIST-DETAILS-1"))

    response = client.get("/api/v1/orders?search=LIST-DETAILS-1")

    order = response.json()["items"][0]
    assert order["customer_first_name"] == "Jan"
    assert order["customer_last_name"] == "Kowalski"
    assert order["payment_type"] == "ONLINE"
    assert order["payment_provider"] == "P24"


def test_an_order_without_details_has_the_same_shape_with_nulls():
    """Orders entered before details existed, or by hand, have none."""
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="NO-DETAILS")
    ).json()

    order = client.get(f"/api/v1/orders/{created['id']}").json()

    assert order["items"] == []
    assert set(order["customer"].values()) == {None}
    assert order["delivery"] == {
        "method": None,
        "cost": None,
        "address": None,
        "pickup_point": None,
    }
    assert set(order["payment"].values()) == {None}
    assert order["invoice"] == {"required": False, "address": None}
    assert order["buyer_message"] is None
    assert order["seller_note"] is None


def test_a_status_change_response_keeps_the_details():
    """The order page replaces its copy of the order with this response."""
    created = client.post(
        "/api/v1/orders", json=_details_payload(external_id="DETAILS-PATCH")
    ).json()

    response = client.patch(
        f"/api/v1/orders/{created['id']}/status", json={"status": "CONFIRMED"}
    )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Widget", "Gadget"]


def test_the_order_list_stays_lean():
    """Details are for one order at a time; a page of 500 does not carry them."""
    client.post("/api/v1/orders", json=_details_payload(external_id="DETAILS-LIST"))

    listed = client.get("/api/v1/orders", params={"search": "DETAILS-LIST"}).json()

    assert listed["total"] == 1
    assert "items" not in listed["items"][0]
    assert "customer" not in listed["items"][0]


def test_invalid_details_are_rejected():
    bad_payloads = [
        _details_payload(external_id="BAD-1", items=[{"name": "X", "quantity": 0, "unit_price": "1.00"}]),
        _details_payload(external_id="BAD-2", items=[{"quantity": 1, "unit_price": "1.00"}]),
        _details_payload(external_id="BAD-3", payment={"type": "BITCOIN"}),
        _details_payload(external_id="BAD-4", delivery={"cost": "-1.00"}),
        _details_payload(external_id="BAD-5", customer={"first_name": ""}),
    ]

    for payload in bad_payloads:
        response = client.post("/api/v1/orders", json=payload)
        assert response.status_code == 422, payload["external_id"]
