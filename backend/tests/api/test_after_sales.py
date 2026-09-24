"""The after-sales queue, the summary behind its badges, an order's own cases,
and the button that reads them from Allegro."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.endpoints.integrations as integrations_endpoint
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.main import app
from app.models.after_sales import AfterSalesCase, CaseAction, CaseKind
from app.models.order import Order, OrderSource, OrderStatus
from app.repositories.user_repository import UserRepository
from app.schemas.after_sales import AfterSalesSyncResult
from app.schemas.user import UserCreate
from app.services.user_service import UserService

client = TestClient(app)
anonymous = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
            UserCreate(email="after-sales-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def setup_function():
    db = TestingSessionLocal()
    try:
        db.query(AfterSalesCase).delete()
        db.commit()
    finally:
        db.close()


def _order() -> tuple[str, str]:
    """An imported order: its Anvero id and the marketplace's."""
    db = TestingSessionLocal()
    try:
        external_id = f"form-{uuid.uuid4()}"
        order = Order(
            external_id=external_id,
            source=OrderSource.ALLEGRO,
            status=OrderStatus.CONFIRMED,
            customer_email="buyer@example.com",
            total_amount=Decimal("10.00"),
            currency="PLN",
        )
        db.add(order)
        db.commit()
        return str(order.id), external_id
    finally:
        db.close()


def _case(
    external_id="X1",
    kind=CaseKind.RETURN,
    action=CaseAction.NONE,
    due_in=None,
    is_open=True,
    order_external_id=None,
    opened_ago=timedelta(days=2),
    status="DELIVERED",
    **fields,
):
    now = datetime.now(UTC)
    db = TestingSessionLocal()
    try:
        db.add(
            AfterSalesCase(
                source=OrderSource.ALLEGRO,
                external_id=external_id,
                kind=kind,
                status=status,
                is_open=is_open,
                action=action,
                due_at=(now + due_in).replace(tzinfo=None) if due_in is not None else None,
                order_external_id=order_external_id,
                opened_at=(now - opened_ago).replace(tzinfo=None),
                **fields,
            )
        )
        db.commit()
    finally:
        db.close()


def test_every_after_sales_endpoint_refuses_an_anonymous_request():
    assert anonymous.get("/api/v1/after-sales").status_code == 401
    assert anonymous.get("/api/v1/after-sales/summary").status_code == 401
    assert anonymous.get(f"/api/v1/orders/{uuid.uuid4()}/after-sales").status_code == 401
    assert anonymous.post("/api/v1/integrations/allegro/after-sales/sync").status_code == 401


def test_the_queue_lists_what_waits_for_the_seller_closest_deadline_first():
    _case("late", action=CaseAction.DECIDE, due_in=timedelta(days=-1), summary="late")
    _case("soon", action=CaseAction.DECIDE, due_in=timedelta(days=2), summary="soon")
    _case("later", action=CaseAction.DECIDE, due_in=timedelta(days=9), summary="later")
    _case("no-deadline", action=CaseAction.REPLY, kind=CaseKind.DISPUTE, summary="none")
    _case("nothing", action=CaseAction.NONE, summary="nothing")

    body = client.get("/api/v1/after-sales").json()

    assert [i["summary"] for i in body["items"]] == ["late", "soon", "later", "none"]
    assert body["total"] == 4


def test_a_case_past_its_deadline_is_marked_overdue():
    _case("late", action=CaseAction.DECIDE, due_in=timedelta(days=-1), summary="late")
    _case("ok", action=CaseAction.DECIDE, due_in=timedelta(days=2), summary="ok")

    items = {i["summary"]: i for i in client.get("/api/v1/after-sales").json()["items"]}

    assert items["late"]["overdue"] is True
    assert items["ok"]["overdue"] is False


def test_a_refunded_return_still_waits_for_its_commission_though_it_is_over():
    _case(
        "refunded",
        action=CaseAction.RECOVER_COMMISSION,
        due_in=timedelta(days=30),
        is_open=False,
        status="FINISHED",
        summary="refunded",
    )

    items = client.get("/api/v1/after-sales").json()["items"]

    assert [i["summary"] for i in items] == ["refunded"]


def test_the_views_narrow_by_what_is_going_on():
    _case("act", action=CaseAction.DECIDE, due_in=timedelta(days=1), summary="act")
    _case("watch", action=CaseAction.NONE, status="IN_TRANSIT", summary="watch")
    _case("done", action=CaseAction.NONE, is_open=False, status="REJECTED", summary="done")

    def summaries(view):
        items = client.get("/api/v1/after-sales", params={"view": view}).json()["items"]
        return {i["summary"] for i in items}

    assert summaries("action") == {"act"}
    assert summaries("open") == {"act", "watch"}
    assert summaries("all") == {"act", "watch", "done"}


def test_the_queue_can_be_narrowed_to_one_kind():
    _case("r", kind=CaseKind.RETURN, action=CaseAction.DECIDE, due_in=timedelta(days=1), summary="r")
    _case("c", kind=CaseKind.CLAIM, action=CaseAction.DECIDE, due_in=timedelta(days=1), summary="c")

    items = client.get("/api/v1/after-sales", params={"kind": "CLAIM"}).json()["items"]

    assert [i["summary"] for i in items] == ["c"]


def test_a_case_names_the_anvero_order_it_belongs_to():
    order_id, external_id = _order()
    _case("mine", action=CaseAction.DECIDE, order_external_id=external_id, summary="mine")
    _case("unknown", action=CaseAction.DECIDE, order_external_id="not-imported", summary="unknown")

    items = {i["summary"]: i for i in client.get("/api/v1/after-sales").json()["items"]}

    assert items["mine"]["order_id"] == order_id
    assert items["mine"]["order_label"].startswith("AN-")
    assert items["unknown"]["order_id"] is None
    assert items["unknown"]["order_label"] is None
    assert items["unknown"]["order_external_id"] == "not-imported"


def test_the_summary_counts_what_waits_what_is_late_and_what_is_close():
    _case("late", action=CaseAction.DECIDE, due_in=timedelta(days=-1))
    _case("soon", action=CaseAction.DECIDE, due_in=timedelta(days=2))
    _case("far", action=CaseAction.DECIDE, due_in=timedelta(days=20))
    _case("reply", action=CaseAction.REPLY, kind=CaseKind.DISPUTE)
    _case("nothing", action=CaseAction.NONE)

    body = client.get("/api/v1/after-sales/summary").json()

    assert body == {"needs_action": 4, "overdue": 1, "due_soon": 1}


def test_an_empty_queue_says_so():
    assert client.get("/api/v1/after-sales/summary").json() == {
        "needs_action": 0,
        "overdue": 0,
        "due_soon": 0,
    }
    assert client.get("/api/v1/after-sales").json() == {"items": [], "total": 0}


def test_an_order_lists_its_own_cases_open_or_not_newest_first():
    order_id, external_id = _order()
    _case("old", order_external_id=external_id, is_open=False, opened_ago=timedelta(days=30), summary="old")
    _case("new", order_external_id=external_id, action=CaseAction.DECIDE, summary="new")
    _case("other", order_external_id="somebody-elses", summary="other")

    response = client.get(f"/api/v1/orders/{order_id}/after-sales")

    assert response.status_code == 200
    assert [i["summary"] for i in response.json()] == ["new", "old"]


def test_an_unknown_order_is_a_404():
    assert client.get(f"/api/v1/orders/{uuid.uuid4()}/after-sales").status_code == 404


def test_paging_narrows_the_list_and_keeps_the_total():
    for n in range(3):
        _case(f"c{n}", action=CaseAction.DECIDE, due_in=timedelta(days=n + 1), summary=f"c{n}")

    body = client.get("/api/v1/after-sales", params={"limit": 2, "offset": 1}).json()

    assert [i["summary"] for i in body["items"]] == ["c1", "c2"]
    assert body["total"] == 3


# --- the sync button --------------------------------------------------------


def _patch_sync(monkeypatch, result=None, error=None):
    def run(db):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(integrations_endpoint, "run_after_sales_sync", run)


URL = "/api/v1/integrations/allegro/after-sales/sync"


def test_the_sync_button_returns_what_was_read(monkeypatch):
    _patch_sync(monkeypatch, AfterSalesSyncResult(returns=2, claims=1, disputes=3))

    response = client.post(URL)

    assert response.status_code == 200
    assert response.json() == {"returns": 2, "claims": 1, "disputes": 3}


def test_the_sync_button_says_when_allegro_is_not_configured(monkeypatch):
    _patch_sync(monkeypatch, error=IntegrationNotConfigured("no"))

    response = client.post(URL)

    assert response.status_code == 409
    assert response.json()["detail"] == "Allegro is not configured"


def test_the_sync_button_reports_a_failure_from_allegro_as_502(monkeypatch):
    _patch_sync(monkeypatch, error=IntegrationError("Allegro API returned 503 for customer returns"))

    response = client.post(URL)

    assert response.status_code == 502
    assert "503" in response.json()["detail"]


def test_the_sync_button_waits_for_a_running_import(monkeypatch):
    def run(db):
        raise integrations_endpoint.ImportAlreadyRunning

    monkeypatch.setattr(integrations_endpoint, "run_after_sales_sync", run)

    assert client.post(URL).status_code == 409


@pytest.fixture(autouse=True)
def _clean_limiter_state():
    # the sync endpoint is rate limited per client; tests here call it often
    app.state.limiter.reset()
    yield
