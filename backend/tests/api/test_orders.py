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


# --- Anvero's own order number ---------------------------------------------


def test_an_order_carries_its_number_and_the_label_it_is_shown_with():
    created = client.post("/api/v1/orders", json=_order_payload(external_id="NUM-1")).json()

    detail = client.get(f"/api/v1/orders/{created['id']}").json()

    assert isinstance(created["order_number"], int)
    assert detail["order_number"] == created["order_number"]
    assert detail["order_label"] == f"AN-{created['order_number']:06d}"


def test_orders_are_numbered_in_the_order_they_are_created():
    first = client.post("/api/v1/orders", json=_order_payload(external_id="NUM-A")).json()
    second = client.post("/api/v1/orders", json=_order_payload(external_id="NUM-B")).json()

    assert second["order_number"] == first["order_number"] + 1


def test_a_client_cannot_choose_the_number():
    created = client.post(
        "/api/v1/orders", json=_order_payload(external_id="NUM-C", order_number=1)
    ).json()

    assert created["order_number"] != 1


def test_the_number_is_searchable_in_every_form_a_person_types_it():
    created = client.post("/api/v1/orders", json=_order_payload(external_id="NUM-D")).json()
    number = created["order_number"]

    for term in (f"AN-{number:06d}", f"an-{number}", f"{number:06d}", str(number)):
        found = client.get("/api/v1/orders", params={"search": term}).json()["items"]
        assert created["id"] in [order["id"] for order in found], term


# --- work queues -----------------------------------------------------------


def _queued(external_id, status, payment=None, **overrides):
    """Create an order for the queue tests; every one's id starts QUEUE-."""
    payload = _order_payload(external_id=f"QUEUE-{external_id}", status=status, **overrides)
    if payment is not None:
        payload["payment"] = payment
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _queue(name, **params):
    listed = client.get(
        "/api/v1/orders", params={"queue": name, "search": "QUEUE-", **params}
    ).json()
    return [order["external_id"].removeprefix("QUEUE-") for order in listed["items"]]


def test_each_waiting_order_is_in_the_one_queue_that_needs_it():
    paid = {"type": "ONLINE", "paid_amount": "129.99"}
    _queued("new-paid", "NEW", paid)
    _queued("in-progress-cod", "CONFIRMED", {"type": "CASH_ON_DELIVERY"})
    _queued("by-hand", "NEW")
    _queued("ready", "READY_FOR_SHIPMENT", paid)
    _queued("online-unpaid", "NEW", {"type": "ONLINE"})
    _queued("transfer-short", "CONFIRMED", {"type": "BANK_TRANSFER", "paid_amount": "10.00"})
    _queued("shipped", "SHIPPED", paid)
    cancelled = _queued("cancelled-on-allegro", "NEW", paid)
    _flag_cancelled_on_marketplace(cancelled["id"])

    assert sorted(_queue("to_make")) == ["by-hand", "in-progress-cod", "new-paid"]
    assert _queue("to_ship") == ["ready"]
    assert sorted(_queue("unpaid")) == ["online-unpaid", "transfer-short"]


def test_an_unknown_queue_is_rejected():
    assert client.get("/api/v1/orders", params={"queue": "someday"}).status_code == 422


def test_at_risk_puts_the_closest_dispatch_deadline_first_and_none_last():
    paid = {"type": "ONLINE", "paid_amount": "129.99"}
    now = datetime.now(UTC)
    _queued("risk-later", "NEW", paid, dispatch_by=(now + timedelta(days=2)).isoformat())
    _queued("risk-none", "NEW", paid, ordered_at=(now - timedelta(days=9)).isoformat())
    _queued("risk-soon", "NEW", paid, dispatch_by=(now + timedelta(hours=3)).isoformat())
    _queued("risk-late", "NEW", paid, dispatch_by=(now - timedelta(hours=1)).isoformat())

    ordered = [x for x in _queue("to_make", sort="at_risk") if x.startswith("risk-")]

    assert ordered == ["risk-late", "risk-soon", "risk-later", "risk-none"]


def test_oldest_first_reverses_the_default_order():
    now = datetime.now(UTC)
    for days in (3, 1, 2):
        _queued(f"age-{days}", "NEW", ordered_at=(now - timedelta(days=days)).isoformat())

    newest = [x for x in _queue("to_make") if x.startswith("age-")]
    oldest = [x for x in _queue("to_make", sort="oldest") if x.startswith("age-")]

    assert newest == ["age-1", "age-2", "age-3"]
    assert oldest == ["age-3", "age-2", "age-1"]


def test_the_list_carries_the_dispatch_deadline():
    created = _queued("deadline", "NEW", dispatch_by="2026-09-25T12:00:00Z")

    (listed,) = client.get("/api/v1/orders", params={"search": "QUEUE-deadline"}).json()["items"]

    assert created["dispatch_by"] == listed["dispatch_by"] == "2026-09-25T12:00:00Z"


def test_the_dashboard_counts_each_queue_and_the_late_ones():
    before = client.get("/api/v1/orders/stats").json()["queues"]
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    paid = {"type": "ONLINE", "paid_amount": "129.99"}
    _queued("count-make-late", "NEW", paid, dispatch_by=past)
    _queued("count-ship", "READY_FOR_SHIPMENT", paid)
    # late, but not paid, so nobody should be working on it yet
    _queued("count-unpaid-late", "NEW", {"type": "ONLINE"}, dispatch_by=past)

    after = client.get("/api/v1/orders/stats").json()["queues"]

    assert {k: after[k] - before[k] for k in after} == {
        "to_make": 1,
        "to_ship": 1,
        "unpaid": 1,
        "late": 1,
    }
    for name in after:
        total = client.get("/api/v1/orders", params={"queue": name, "limit": 1}).json()["total"]
        assert after[name] == total, name


# --- the "to make today" list ------------------------------------------------


def _production_lines(prefix):
    body = client.get("/api/v1/orders/production").json()
    return [line for line in body["lines"] if line["name"].startswith(prefix)]


def _to_make(external_id, items, status="NEW", payment=None, **overrides):
    payment = payment or {"type": "ONLINE", "paid_amount": "129.99"}
    return _queued(external_id, status, payment, items=items, **overrides)


def test_the_production_list_adds_up_each_product_across_orders():
    now = datetime.now(UTC)
    later = _to_make(
        "prod-later",
        [{"name": "PROD Mug", "sku": "PROD-MUG", "quantity": 2, "unit_price": "10.00"}],
        dispatch_by=(now + timedelta(days=2)).isoformat(),
    )
    sooner = _to_make(
        "prod-sooner",
        [
            {"name": "PROD Mug (red)", "sku": "PROD-MUG", "quantity": 1, "unit_price": "10.00"},
            {"name": "PROD Plate", "sku": "PROD-PLATE", "quantity": 3, "unit_price": "5.00"},
        ],
        status="CONFIRMED",
        source="ERLI",
        dispatch_by=(now + timedelta(hours=5)).isoformat(),
    )

    lines = _production_lines("PROD ")

    # the product first needed soonest leads; both come from the sooner order
    assert [line["key"] for line in lines] == ["sku:PROD-MUG", "sku:PROD-PLATE"]
    mug = lines[0]
    assert mug["quantity"] == 3
    assert [o["order_label"] for o in mug["orders"]] == [
        sooner["order_label"],
        later["order_label"],
    ]
    assert [o["quantity"] for o in mug["orders"]] == [1, 2]
    assert mug["dispatch_by"] == mug["orders"][0]["dispatch_by"]
    assert mug["orders"][0]["source"] == "ERLI"
    assert mug["orders"][0]["status"] == "CONFIRMED"


def test_without_a_code_items_group_by_listing_then_by_name():
    _to_make(
        "prod-nocode-1",
        [
            {"name": "NOCODE Bowl", "offer_id": "offer-77", "quantity": 1, "unit_price": "1.00"},
            {"name": "NOCODE Spoon", "quantity": 2, "unit_price": "1.00"},
        ],
    )
    _to_make(
        "prod-nocode-2",
        [
            {"name": "NOCODE Bowl, renamed", "offer_id": "offer-77", "quantity": 1, "unit_price": "1.00"},
            {"name": "NOCODE Spoon", "quantity": 1, "unit_price": "1.00"},
        ],
    )

    by_key = {line["key"]: line["quantity"] for line in _production_lines("NOCODE ")}

    assert by_key == {"offer:offer-77": 2, "name:NOCODE Spoon": 3}


def test_one_order_with_the_same_product_twice_is_listed_once():
    _to_make(
        "prod-twice",
        [
            {"name": "TWICE Cup", "sku": "TWICE-CUP", "quantity": 1, "unit_price": "1.00"},
            {"name": "TWICE Cup", "sku": "TWICE-CUP", "quantity": 2, "unit_price": "1.00"},
        ],
    )

    (line,) = _production_lines("TWICE ")

    assert line["quantity"] == 3
    assert [o["quantity"] for o in line["orders"]] == [3]


def test_only_orders_still_to_make_count():
    item = [{"name": "ONLY Vase", "sku": "ONLY-VASE", "quantity": 1, "unit_price": "1.00"}]
    _to_make("only-new", item)
    _to_make("only-unpaid", item, payment={"type": "ONLINE"})
    _to_make("only-ready", item, status="READY_FOR_SHIPMENT")
    _to_make("only-shipped", item, status="SHIPPED")

    (line,) = _production_lines("ONLY ")

    assert line["quantity"] == 1
    assert [o["order_label"] for o in line["orders"]] == [
        client.get("/api/v1/orders", params={"search": "QUEUE-only-new"}).json()["items"][0][
            "order_label"
        ]
    ]


# --- search beyond the order's own ids -----------------------------------------


def _find(term):
    listed = client.get("/api/v1/orders", params={"search": term}).json()
    return listed["total"], [o["external_id"] for o in listed["items"]]


def test_search_finds_an_order_by_what_the_operator_remembers_of_it():
    client.post(
        "/api/v1/orders",
        json=_details_payload(
            external_id="SEARCH-WIDE",
            customer={"login": "zosia_kupuje", "first_name": "Zofia", "last_name": "Wyszukiwalska"},
            items=[
                {"name": "Kubek emaliowany", "sku": "SRCH-KUB-9", "quantity": 1, "unit_price": "10.00"},
                {"name": "Kubek drugi", "sku": "SRCH-KUB-10", "quantity": 1, "unit_price": "10.00"},
            ],
            delivery={
                "address": {"city": "Szczebrzeszyn"},
                "pickup_point": {"id": "SZC01M", "name": "Paczkomat SZC01M"},
            },
            shipments=[{"carrier_id": "INPOST", "waybill": "620111222333444555666777"}],
        ),
    )

    for term in (
        "SRCH-KUB-9",  # the seller's product code
        "emaliowany",  # the product's name
        "szczebrzeszyn",  # the delivery city, in any case
        "SZC01M",  # the parcel locker
        "620111222333",  # part of the tracking number
        "zosia_kupuje",  # the marketplace login
        "Zofia Wyszukiwalska",  # the buyer's full name
    ):
        assert _find(term) == (1, ["SEARCH-WIDE"]), term


def test_an_order_matching_on_two_items_is_found_once():
    total, found = _find("SRCH-KUB")

    assert (total, found) == (1, ["SEARCH-WIDE"])


# --- the same buyer's other orders --------------------------------------------


def _buyer_order(external_id, **overrides):
    response = client.post(
        "/api/v1/orders",
        json=_details_payload(external_id=f"BUYER-{external_id}", **overrides),
    )
    return response.json()


def test_an_order_lists_the_same_buyers_other_orders():
    first = _buyer_order(
        "1", customer_email="stala@example.com", customer={"login": "stala_klientka"},
        ordered_at="2026-09-01T10:00:00Z",
    )
    # another email (a marketplace can mask it per order), same login
    second = _buyer_order(
        "2", customer_email="inny@example.com", customer={"login": "stala_klientka"},
        ordered_at="2026-09-10T10:00:00Z",
    )
    # the same email, no login
    third = _buyer_order("3", customer_email="stala@example.com", customer={})
    # the same login on another marketplace is someone else
    _buyer_order(
        "4", source="ERLI", customer_email="ktos@example.com", customer={"login": "stala_klientka"}
    )
    _buyer_order("5", customer_email="obcy@example.com", customer={"login": "ktos_inny"})

    others = client.get(f"/api/v1/orders/{first['id']}/buyer-orders")

    assert others.status_code == 200
    assert [o["external_id"] for o in others.json()] == [third["external_id"], second["external_id"]]


def test_buyer_orders_of_an_unknown_order_is_404():
    missing = "00000000-0000-0000-0000-000000000000"

    assert client.get(f"/api/v1/orders/{missing}/buyer-orders").status_code == 404


# --- safe mode ------------------------------------------------------------------


def test_safe_mode_starts_on_and_says_who_switched_it():
    first = client.get("/api/v1/settings/safe-mode").json()
    assert first == {"enabled": True, "changed_at": None, "changed_by": None}

    off = client.put("/api/v1/settings/safe-mode", json={"enabled": False})

    assert off.status_code == 200
    assert off.json()["enabled"] is False
    assert off.json()["changed_by"] == OPERATOR_EMAIL
    assert off.json()["changed_at"].endswith("Z")

    back_on = client.put("/api/v1/settings/safe-mode", json={"enabled": True}).json()
    assert back_on["enabled"] is True


def test_safe_mode_and_the_write_log_need_a_login():
    assert anonymous.get("/api/v1/settings/safe-mode").status_code == 401
    assert anonymous.put("/api/v1/settings/safe-mode", json={"enabled": False}).status_code == 401
    assert anonymous.get("/api/v1/marketplace-writes").status_code == 401


def test_the_write_log_lists_what_would_have_been_sent():
    import uuid

    from app.models.order import OrderSource
    from app.services.marketplace_writes import MarketplaceWriter

    created = client.post("/api/v1/orders", json=_order_payload(external_id="WRITE-LOG-1")).json()
    db = TestingSessionLocal()
    try:
        MarketplaceWriter(db).write(
            OrderSource.ALLEGRO,
            "fulfillment_status",
            {"status": "SENT"},
            lambda: None,
            order_id=uuid.UUID(created["id"]),
        )
    finally:
        db.close()

    (entry,) = client.get(
        "/api/v1/marketplace-writes", params={"order_id": created["id"]}
    ).json()

    assert entry["outcome"] == "DRY_RUN"
    assert entry["action"] == "fulfillment_status"
    assert entry["payload"] == '{"status": "SENT"}'
    assert entry["source"] == "ALLEGRO"
