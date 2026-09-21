from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.order import (
    AddressType,
    Order,
    OrderAddress,
    OrderItem,
    OrderSource,
    OrderStatus,
    PaymentType,
)
from app.repositories.order_repository import OrderRepository
from app.schemas.order import (
    Address,
    Customer,
    Delivery,
    Invoice,
    OrderCreate,
    OrderDetails,
    OrderItemCreate,
    Payment,
    PickupPoint,
)
from app.schemas.types import _as_utc
from app.services.order_import_service import SYNC_OVERLAP, OrderImportService


class FakeAdapter:
    """Stands in for AllegroAdapter: the import service only needs the port."""

    source = OrderSource.ALLEGRO

    def __init__(self, orders):
        self.orders = orders

    def fetch_orders(self, limit: int = 100, offset: int = 0):
        return self.orders


def _order(external_id="ALG-1", email="buyer@example.com", amount="100.00"):
    return OrderCreate(
        external_id=external_id,
        source=OrderSource.ALLEGRO,
        status=OrderStatus.NEW,
        customer_email=email,
        total_amount=Decimal(amount),
        currency="PLN",
    )


# `session` comes from tests/conftest.py


def _service(session, orders):
    return OrderImportService(OrderRepository(session), FakeAdapter(orders))


def test_imports_new_orders(session):
    result = _service(session, [_order("ALG-1"), _order("ALG-2")]).import_orders()

    assert (result.created, result.updated, result.total) == (2, 0, 2)
    assert session.query(Order).count() == 2


def test_re_import_does_not_duplicate(session):
    orders = [_order("ALG-1")]
    _service(session, orders).import_orders()

    result = _service(session, orders).import_orders()

    assert (result.created, result.updated) == (0, 1)
    assert session.query(Order).count() == 1


def test_re_import_keeps_the_status_the_operator_set(session):
    """The Anvero status is the operator's, recorded in the status history.

    A sync overwriting it would silently undo their work, so an order already
    present keeps its status even though the marketplace still reports NEW.
    """
    orders = [_order("ALG-1")]
    _service(session, orders).import_orders()

    stored = session.query(Order).one()
    OrderRepository(session).update_status(stored, OrderStatus.SHIPPED)

    _service(session, orders).import_orders()

    assert session.query(Order).one().status is OrderStatus.SHIPPED


def test_a_new_order_records_the_marketplace_status_beside_its_own(session):
    _service(session, [_order("ALG-1")]).import_orders()

    stored = session.query(Order).one()
    assert (stored.status, stored.marketplace_status) == (
        OrderStatus.NEW,
        OrderStatus.NEW,
    )


def test_re_import_records_where_the_marketplace_has_moved_to(session):
    """The operator's status stands, but they must be able to see the gap.

    Here Anvero says SHIPPED and the marketplace still says NEW; without
    marketplace_status the divergence left no trace at all.
    """
    _service(session, [_order("ALG-1")]).import_orders()
    stored = session.query(Order).one()
    OrderRepository(session).update_status(stored, OrderStatus.SHIPPED)

    _service(session, [_order("ALG-1")]).import_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.SHIPPED
    assert stored.marketplace_status is OrderStatus.NEW


def test_re_import_follows_the_marketplace_status_as_it_changes(session):
    _service(session, [_order("ALG-1")]).import_orders()
    moved_on = _order("ALG-1").model_copy(
        update={
            "status": OrderStatus.CONFIRMED,
            "marketplace_status_label": "READY_FOR_SHIPMENT",
        }
    )

    _service(session, [moved_on]).import_orders()

    stored = session.query(Order).one()
    # the order the sandbox showed: Allegro in PROCESSING, Anvero untouched
    assert stored.status is OrderStatus.NEW
    assert stored.marketplace_status is OrderStatus.CONFIRMED
    # Anvero has one status for both PROCESSING and READY_FOR_SHIPMENT, so
    # only the label says which one Allegro means
    assert stored.marketplace_status_label == "READY_FOR_SHIPMENT"


def test_re_import_replaces_a_stale_marketplace_label(session):
    """A label left behind would describe a status the order has left."""
    first = _order("ALG-1").model_copy(
        update={"marketplace_status_label": "READY_FOR_SHIPMENT"}
    )
    _service(session, [first]).import_orders()

    moved_on = _order("ALG-1").model_copy(
        update={"status": OrderStatus.SHIPPED, "marketplace_status_label": "SENT"}
    )
    _service(session, [moved_on]).import_orders()

    assert session.query(Order).one().marketplace_status_label == "SENT"


def test_an_order_never_imported_has_no_marketplace_status(session):
    """A hand-made order has no marketplace to disagree with."""
    order = OrderRepository(session).create(
        Order(
            external_id="MANUAL-1",
            source=OrderSource.ALLEGRO,
            status=OrderStatus.NEW,
            customer_email="buyer@example.com",
            total_amount=Decimal("10.00"),
            currency="PLN",
        )
    )

    assert order.marketplace_status is None


def test_re_import_refreshes_the_fields_the_marketplace_owns(session):
    _service(session, [_order("ALG-1", email="old@example.com", amount="100.00")]).import_orders()

    _service(
        session, [_order("ALG-1", email="new@example.com", amount="250.00")]
    ).import_orders()

    stored = session.query(Order).one()
    assert stored.customer_email == "new@example.com"
    assert stored.total_amount == Decimal("250.00")


def _cancelled(order):
    return order.model_copy(update={"status": OrderStatus.CANCELLED})


def test_a_marketplace_cancellation_warns_instead_of_changing_status(session):
    """Regression: a cancellation on Allegro used to vanish without trace, so
    an operator could ship an order the buyer had cancelled."""
    _service(session, [_order("ALG-1")]).import_orders()

    result = _service(session, [_cancelled(_order("ALG-1"))]).import_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.NEW
    assert stored.marketplace_cancelled_at is not None
    assert result.cancellation_warnings == 1


def test_a_cancellation_is_only_reported_once(session):
    _service(session, [_order("ALG-1")]).import_orders()
    _service(session, [_cancelled(_order("ALG-1"))]).import_orders()
    first_seen = session.query(Order).one().marketplace_cancelled_at

    result = _service(session, [_cancelled(_order("ALG-1"))]).import_orders()

    assert result.cancellation_warnings == 0
    # the timestamp records when the cancellation was first noticed
    assert session.query(Order).one().marketplace_cancelled_at == first_seen


def test_no_warning_when_the_operator_already_cancelled(session):
    _service(session, [_order("ALG-1")]).import_orders()
    OrderRepository(session).update_status(
        session.query(Order).one(), OrderStatus.CANCELLED
    )

    result = _service(session, [_cancelled(_order("ALG-1"))]).import_orders()

    assert result.cancellation_warnings == 0
    assert session.query(Order).one().marketplace_cancelled_at is not None


def test_an_order_first_seen_cancelled_needs_no_warning(session):
    result = _service(session, [_cancelled(_order("ALG-1"))]).import_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.CANCELLED
    assert stored.marketplace_cancelled_at is not None
    assert result.cancellation_warnings == 0


def _placed(order, when):
    return order.model_copy(update={"ordered_at": when})


def test_an_imported_order_keeps_its_marketplace_purchase_time(session):
    """Regression: imported orders were dated at import, so a backfill made
    every order look placed today."""
    placed = datetime(2025, 12, 24, 18, 30, tzinfo=UTC)

    _service(session, [_placed(_order("ALG-1"), placed)]).import_orders()

    stored = session.query(Order).one()
    # SQLite hands timestamps back without a zone and PostgreSQL in the
    # connection's zone; normalised the way the API does before comparing
    assert _as_utc(stored.ordered_at) == placed


def test_re_import_refreshes_the_purchase_time(session):
    """The marketplace owns this field, like the email and the amount."""
    _service(session, [_order("ALG-1")]).import_orders()
    placed = datetime(2025, 12, 24, 18, 30, tzinfo=UTC)

    _service(session, [_placed(_order("ALG-1"), placed)]).import_orders()

    assert _as_utc(session.query(Order).one().ordered_at) == placed


def _with_details(order, item_names=("Widget",), street="Prosta 1", pickup=False):
    details = OrderDetails(
        customer=Customer(first_name="Jan", last_name="Kowalski"),
        items=[
            OrderItemCreate(name=name, quantity=1, unit_price=Decimal("10.00"))
            for name in item_names
        ],
        delivery=Delivery(
            method="Kurier",
            address=Address(street=street, city="Warszawa"),
            pickup_point=(
                PickupPoint(id="WAW01A", address=Address(street="Długa 5"))
                if pickup
                else None
            ),
        ),
        payment=Payment(type=PaymentType.ONLINE, paid_amount=Decimal("100.00")),
        invoice=Invoice(required=True, address=Address(tax_id="1234563218")),
    )
    return order.model_copy(update=dict(details))


def test_an_imported_order_keeps_its_details(session):
    _service(session, [_with_details(_order("ALG-1"), pickup=True)]).import_orders()

    stored = session.query(Order).one()
    assert (stored.customer_first_name, stored.customer_last_name) == ("Jan", "Kowalski")
    assert [item.name for item in stored.items] == ["Widget"]
    assert stored.delivery_method == "Kurier"
    assert stored.pickup_point_id == "WAW01A"
    assert stored.payment_type is PaymentType.ONLINE
    assert stored.paid_amount == Decimal("100.00")
    assert stored.invoice_required is True
    assert stored.address(AddressType.DELIVERY).street == "Prosta 1"
    assert stored.address(AddressType.PICKUP_POINT).street == "Długa 5"
    assert stored.address(AddressType.INVOICE).tax_id == "1234563218"


def test_re_import_replaces_items_and_addresses(session):
    """The marketplace owns the details, so what it no longer reports goes.

    Also a regression guard for the address swap: within one flush SQLAlchemy
    inserts before it deletes, which would briefly hold two delivery addresses
    and break the one-per-type constraint.
    """
    first = _with_details(_order("ALG-1"), item_names=("Widget", "Gadget"), pickup=True)
    _service(session, [first]).import_orders()

    second = _with_details(_order("ALG-1"), item_names=("Gizmo",), street="Krzywa 9")
    _service(session, [second]).import_orders()

    session.expire_all()
    stored = session.query(Order).one()
    assert [item.name for item in stored.items] == ["Gizmo"]
    assert stored.address(AddressType.DELIVERY).street == "Krzywa 9"
    assert stored.address(AddressType.PICKUP_POINT) is None
    assert stored.pickup_point_id is None
    assert session.query(OrderItem).count() == 1
    assert session.query(OrderAddress).count() == 2


def test_re_import_keeps_the_status_while_refreshing_details(session):
    _service(session, [_with_details(_order("ALG-1"))]).import_orders()
    OrderRepository(session).update_status(session.query(Order).one(), OrderStatus.SHIPPED)

    _service(session, [_with_details(_order("ALG-1"), item_names=("Gizmo",))]).import_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.SHIPPED
    assert [item.name for item in stored.items] == ["Gizmo"]


def test_an_order_from_another_marketplace_is_not_a_duplicate(session):
    """Order numbers collide across marketplaces."""
    _service(session, [_order("SHARED")]).import_orders()

    erli = _order("SHARED")
    erli = erli.model_copy(update={"source": OrderSource.ERLI})
    result = _service(session, [erli]).import_orders()

    assert result.created == 1
    assert session.query(Order).count() == 2


# --- sync_orders: first window, then only what changed --------------------


class PagedFakeAdapter:
    """Records the filters it is asked for and serves pages of orders."""

    source = OrderSource.ALLEGRO

    def __init__(self, pages, fail_on_page=None):
        self.pages = pages
        self.fail_on_page = fail_on_page
        self.requests = []

    def fetch_orders(self, limit: int = 100, offset: int = 0):
        return []

    def iter_order_pages(self, bought_since=None, updated_since=None):
        self.requests.append({"bought_since": bought_since, "updated_since": updated_since})
        for index, page in enumerate(self.pages):
            if index == self.fail_on_page:
                raise RuntimeError("Allegro went away")
            yield page


def _credentials(session):
    from app.models.integration import IntegrationCredential
    from app.repositories.integration_credential_repository import (
        IntegrationCredentialRepository,
    )

    session.add(
        IntegrationCredential(provider="ALLEGRO", refresh_token="t", seed_fingerprint="f")
    )
    session.commit()
    return IntegrationCredentialRepository(session)


def _sync_service(session, adapter, credentials, initial_days=7):
    return OrderImportService(
        OrderRepository(session), adapter, credentials=credentials, initial_days=initial_days
    )


def test_the_first_sync_reaches_back_the_initial_window_by_purchase_date(session):
    adapter = PagedFakeAdapter([[_order("ALG-1")]])
    credentials = _credentials(session)

    _sync_service(session, adapter, credentials, initial_days=7).sync_orders()
    after = datetime.now(UTC)

    (request,) = adapter.requests
    assert request["updated_since"] is None
    window = after - request["bought_since"]
    assert timedelta(days=7) <= window < timedelta(days=7, minutes=1)


def test_a_later_sync_asks_only_for_what_changed_since_the_recorded_point(session):
    credentials = _credentials(session)
    _sync_service(session, PagedFakeAdapter([[_order("ALG-1")]]), credentials).sync_orders()
    recorded = credentials.last_synced_at("ALLEGRO")

    adapter = PagedFakeAdapter([[_order("ALG-1")]])
    result = _sync_service(session, adapter, credentials).sync_orders()

    (request,) = adapter.requests
    assert request == {"bought_since": None, "updated_since": recorded}
    # the same order again is an update, not a second copy
    assert (result.created, result.updated) == (0, 1)


def test_every_page_is_stored(session):
    adapter = PagedFakeAdapter([[_order("ALG-1")], [_order("ALG-2")], [_order("ALG-3")]])

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert result.created == 3
    assert session.query(Order).count() == 3


def test_the_recorded_point_is_the_start_of_the_run_less_a_small_overlap(session):
    credentials = _credentials(session)
    before = datetime.now(UTC)

    _sync_service(session, PagedFakeAdapter([[_order("ALG-1")]]), credentials).sync_orders()

    recorded = credentials.last_synced_at("ALLEGRO")
    assert before - SYNC_OVERLAP <= recorded <= datetime.now(UTC) - SYNC_OVERLAP


def test_a_failed_sync_keeps_the_recorded_point_and_the_pages_already_stored(session):
    credentials = _credentials(session)
    adapter = PagedFakeAdapter([[_order("ALG-1")], [_order("ALG-2")]], fail_on_page=1)

    try:
        _sync_service(session, adapter, credentials).sync_orders()
    except RuntimeError:
        pass

    assert credentials.last_synced_at("ALLEGRO") is None
    assert session.query(Order).count() == 1


def test_days_forces_a_purchase_window_even_when_a_point_is_recorded(session):
    credentials = _credentials(session)
    _sync_service(session, PagedFakeAdapter([[]]), credentials).sync_orders()

    adapter = PagedFakeAdapter([[]])
    _sync_service(session, adapter, credentials).sync_orders(days=30)

    (request,) = adapter.requests
    assert request["updated_since"] is None
    assert request["bought_since"] is not None


def test_reauthorizing_forgets_the_recorded_point(session):
    """A different seller account has a different order history, so what was
    fetched for the old one says nothing about the new one."""
    credentials = _credentials(session)
    _sync_service(session, PagedFakeAdapter([[]]), credentials).sync_orders()
    assert credentials.last_synced_at("ALLEGRO") is not None

    credentials.save("ALLEGRO", "new-token", "another-seed")

    assert credentials.last_synced_at("ALLEGRO") is None
