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


def test_re_import_keeps_a_status_the_operator_set_while_the_marketplace_has_not_moved(session):
    """Only a *move* on the marketplace is applied. Seeing the same order again
    with the same marketplace status must not revert what the operator did."""
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
            "status": OrderStatus.READY_FOR_SHIPMENT,
            "marketplace_status_label": "READY_FOR_SHIPMENT",
        }
    )

    _service(session, [moved_on]).import_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.READY_FOR_SHIPMENT
    assert stored.marketplace_status is OrderStatus.READY_FOR_SHIPMENT
    assert stored.marketplace_status_label == "READY_FOR_SHIPMENT"


def test_a_status_followed_from_the_marketplace_is_recorded_in_the_history(session):
    _service(session, [_order("ALG-1")]).import_orders()
    shipped = _order("ALG-1").model_copy(update={"status": OrderStatus.SHIPPED})

    _service(session, [shipped]).import_orders()

    (entry,) = OrderRepository(session).list_status_history(session.query(Order).one().id)
    assert (entry.from_status, entry.to_status) == (OrderStatus.NEW, OrderStatus.SHIPPED)
    # no one made this change, so no one is named
    assert entry.changed_by_user_id is None


def test_when_the_marketplace_moves_it_wins_over_the_operators_status(session):
    """The owner's rule: what changes on Allegro changes here, even over a
    status set by hand - Anvero does not write back, so Allegro is the truth."""
    _service(session, [_order("ALG-1")]).import_orders()
    OrderRepository(session).update_status(session.query(Order).one(), OrderStatus.SHIPPED)
    confirmed = _order("ALG-1").model_copy(update={"status": OrderStatus.CONFIRMED})

    _service(session, [confirmed]).import_orders()

    assert session.query(Order).one().status is OrderStatus.CONFIRMED


def test_no_history_entry_when_the_status_already_matches(session):
    _service(session, [_order("ALG-1")]).import_orders()
    OrderRepository(session).update_status(session.query(Order).one(), OrderStatus.SHIPPED)
    shipped = _order("ALG-1").model_copy(update={"status": OrderStatus.SHIPPED})

    _service(session, [shipped]).import_orders()

    history = OrderRepository(session).list_status_history(session.query(Order).one().id)
    # only the operator's own change; the import had nothing to add
    assert len(history) == 1


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


def test_a_marketplace_cancellation_cancels_the_order_and_warns(session):
    """Regression: a cancellation on Allegro used to vanish without trace, so
    an operator could ship an order the buyer had cancelled."""
    _service(session, [_order("ALG-1")]).import_orders()

    result = _service(session, [_cancelled(_order("ALG-1"))]).import_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.CANCELLED
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

    # SQLite hands the column back without a zone, PostgreSQL with one
    recorded = _as_utc(credentials.last_synced_at("ALLEGRO"))
    assert before - SYNC_OVERLAP <= recorded <= datetime.now(UTC) - SYNC_OVERLAP


def test_a_sync_that_fails_while_fetching_stores_nothing_and_keeps_the_point(session):
    credentials = _credentials(session)
    adapter = PagedFakeAdapter([[_order("ALG-1")], [_order("ALG-2")]], fail_on_page=1)

    try:
        _sync_service(session, adapter, credentials).sync_orders()
    except RuntimeError:
        pass

    assert credentials.last_synced_at("ALLEGRO") is None
    assert session.query(Order).count() == 0


def test_a_first_import_numbers_orders_by_purchase_date_not_page_order(session):
    """Allegro serves the newest orders first; the numbers must still read in
    the order the orders were placed."""
    day = lambda d: datetime(2026, 9, d, tzinfo=UTC)
    newest_page = [_placed(_order("NEW-9"), day(9)), _placed(_order("MID-5"), day(5))]
    oldest_page = [_placed(_order("OLD-1"), day(1))]

    _sync_service(
        session, PagedFakeAdapter([newest_page, oldest_page]), _credentials(session)
    ).sync_orders()

    numbered = {o.external_id: o.order_number for o in session.query(Order).all()}
    assert numbered == {"OLD-1": 1, "MID-5": 2, "NEW-9": 3}


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


# --- Anvero's own order numbers -------------------------------------------


def test_every_new_order_gets_the_next_number(session):
    _service(session, [_order("A"), _order("B"), _order("C")]).import_orders()

    numbers = sorted(o.order_number for o in session.query(Order).all())
    assert numbers == [numbers[0], numbers[0] + 1, numbers[0] + 2]


def test_a_re_import_does_not_renumber_or_use_up_numbers(session):
    _service(session, [_order("A")]).import_orders()
    first = session.query(Order).one().order_number

    _service(session, [_order("A")]).import_orders()
    _service(session, [_order("B")]).import_orders()

    numbers = {o.external_id: o.order_number for o in session.query(Order).all()}
    assert numbers["A"] == first
    assert numbers["B"] == first + 1


def test_an_order_deleted_in_anvero_is_not_brought_back_by_an_import(session):
    _service(session, [_order("ALG-DEL", amount="100.00")]).import_orders()
    order = session.query(Order).one()
    OrderRepository(session).mark_deleted(order, None)

    # the marketplace still has it, and now says something else about it
    result = _service(session, [_order("ALG-DEL", amount="250.00")]).import_orders()

    assert (result.created, result.updated) == (0, 0)
    assert session.query(Order).count() == 1
    kept = session.query(Order).one()
    assert kept.deleted_at is not None
    assert kept.total_amount == Decimal("100.00")


def test_a_restored_order_is_updated_by_the_next_import_again(session):
    _service(session, [_order("ALG-BACK", amount="100.00")]).import_orders()
    repository = OrderRepository(session)
    order = session.query(Order).one()
    repository.mark_deleted(order, None)
    repository.restore(order)

    result = _service(session, [_order("ALG-BACK", amount="250.00")]).import_orders()

    assert (result.created, result.updated) == (0, 1)
    assert session.query(Order).one().total_amount == Decimal("250.00")


# --- orders that are still open are read again ----------------------------------------


class OpenAwareAdapter(PagedFakeAdapter):
    """Serves what changed in the window, and separately the orders still open."""

    def __init__(self, window, open_orders=None, open_error=None):
        super().__init__([window])
        self.open_orders = open_orders or []
        self.open_error = open_error
        self.open_reads = 0

    def iter_open_order_pages(self):
        self.open_reads += 1
        if self.open_error:
            raise self.open_error
        yield self.open_orders


def _moved(order, to=OrderStatus.SHIPPED):
    return order.model_copy(update={"status": to})


def test_an_open_order_the_window_missed_still_follows_the_marketplace(session):
    """The marketplace does not count everything that happens to an order (a
    shipment created, it being sent) as a change since the last import."""
    _service(session, [_order("ALG-1")]).import_orders()
    adapter = OpenAwareAdapter(window=[], open_orders=[_moved(_order("ALG-1"))])

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert session.query(Order).one().status is OrderStatus.SHIPPED
    assert (result.created, result.updated) == (0, 1)


def test_an_open_order_that_did_not_move_is_not_reported_as_updated(session):
    _service(session, [_order("ALG-1")]).import_orders()
    adapter = OpenAwareAdapter(window=[], open_orders=[_order("ALG-1")])

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert (result.created, result.updated) == (0, 0)
    assert session.query(Order).count() == 1


def test_an_order_in_both_the_window_and_the_open_list_is_stored_once(session):
    _service(session, [_order("ALG-1")]).import_orders()
    changed = _moved(_order("ALG-1"), OrderStatus.CONFIRMED)
    adapter = OpenAwareAdapter(window=[changed], open_orders=[changed])

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert (result.created, result.updated) == (0, 1)
    assert session.query(Order).count() == 1


def test_a_failure_reading_the_open_orders_does_not_fail_the_import(session):
    from app.integrations.base import IntegrationUnavailable

    adapter = OpenAwareAdapter(
        window=[_order("ALG-NEW")], open_error=IntegrationUnavailable("Allegro is slow")
    )
    credentials = _credentials(session)

    result = _sync_service(session, adapter, credentials).sync_orders()

    assert (result.created, result.updated) == (1, 0)
    # and the sync point moved, since the window itself was read
    assert credentials.last_synced_at("ALLEGRO") is not None


def test_an_adapter_without_the_open_call_is_unaffected(session):
    adapter = PagedFakeAdapter([[_order("ALG-1")]])

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert (result.created, result.updated) == (1, 0)


def test_an_open_order_deleted_in_anvero_stays_deleted(session):
    _service(session, [_order("ALG-1")]).import_orders()
    OrderRepository(session).mark_deleted(session.query(Order).one(), None)
    adapter = OpenAwareAdapter(window=[], open_orders=[_moved(_order("ALG-1"))])

    _sync_service(session, adapter, _credentials(session)).sync_orders()

    kept = session.query(Order).one()
    assert kept.deleted_at is not None
    assert kept.status is OrderStatus.NEW


def test_an_open_order_that_was_never_imported_is_created(session):
    adapter = OpenAwareAdapter(window=[], open_orders=[_order("ALG-MISSED")])

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert (result.created, result.updated) == (1, 0)


# --- orders held as open that the marketplace has moved on from -----------------------


class HeldAwareAdapter(OpenAwareAdapter):
    """Also answers for orders by id, as the marketplace has them now."""

    def __init__(self, window, now=None, open_orders=None, error=None):
        super().__init__(window, open_orders=open_orders)
        self.now = now or {}
        self.error = error
        self.asked = []

    def fetch_orders_by_id(self, external_ids):
        self.asked.append(list(external_ids))
        if self.error:
            raise self.error
        return [self.now[i] for i in external_ids if i in self.now]


def test_an_open_order_the_marketplace_has_sent_is_asked_for_by_id(session):
    """Once an order is sent the list of open orders no longer names it, and the window
    does not either: only asking for it by its id brings the new status."""
    _service(session, [_order("ALG-1")]).import_orders()
    adapter = HeldAwareAdapter(window=[], now={"ALG-1": _moved(_order("ALG-1"))})

    result = _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert adapter.asked == [["ALG-1"]]
    assert session.query(Order).one().status is OrderStatus.SHIPPED
    assert (result.created, result.updated) == (0, 1)


def test_an_order_already_read_is_not_asked_for_again(session):
    _service(session, [_order("ALG-1"), _order("ALG-2"), _order("ALG-3")]).import_orders()
    adapter = HeldAwareAdapter(
        window=[_order("ALG-1")],
        open_orders=[_order("ALG-2")],
        now={"ALG-3": _moved(_order("ALG-3"))},
    )

    _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert adapter.asked == [["ALG-3"]]


def test_an_order_the_marketplace_called_finished_is_not_asked_for(session):
    _service(session, [_moved(_order("ALG-DONE"))]).import_orders()
    adapter = HeldAwareAdapter(window=[])

    _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert adapter.asked == []


def test_an_order_deleted_in_anvero_is_not_asked_for(session):
    _service(session, [_order("ALG-1")]).import_orders()
    OrderRepository(session).mark_deleted(session.query(Order).one(), None)
    adapter = HeldAwareAdapter(window=[], now={"ALG-1": _moved(_order("ALG-1"))})

    _sync_service(session, adapter, _credentials(session)).sync_orders()

    assert adapter.asked == []
    assert session.query(Order).one().status is OrderStatus.NEW


def test_a_failure_reading_held_orders_does_not_fail_the_import(session):
    from app.integrations.base import IntegrationUnavailable

    _service(session, [_order("ALG-1")]).import_orders()
    adapter = HeldAwareAdapter(
        window=[_order("ALG-NEW")], error=IntegrationUnavailable("Allegro is slow")
    )
    credentials = _credentials(session)

    result = _sync_service(session, adapter, credentials).sync_orders()

    assert (result.created, result.updated) == (1, 0)
    assert credentials.last_synced_at("ALLEGRO") is not None


# --- sent orders whose parcels the carrier has delivered ------------------------------


def _shipped_with(session, external_id, *tracking_statuses):
    """A stored order, already sent, with one parcel per given carrier status."""
    from app.models.order import OrderShipment

    _service(session, [_order(external_id)]).import_orders()
    order = session.query(Order).filter_by(external_id=external_id).one()
    OrderRepository(session).update_status(order, OrderStatus.SHIPPED)
    for position, status in enumerate(tracking_statuses):
        session.add(
            OrderShipment(
                order_id=order.id,
                position=position,
                waybill=f"{external_id}-{position}",
                carrier_id="INPOST",
                tracking_status=status,
            )
        )
    session.commit()
    return order


def _sync_nothing_new(session):
    _sync_service(session, PagedFakeAdapter([[]]), _credentials(session)).sync_orders()


def test_a_sent_order_whose_parcel_was_delivered_becomes_delivered(session):
    _shipped_with(session, "ALG-1", "DELIVERED")

    _sync_nothing_new(session)

    order = session.query(Order).one()
    assert order.status is OrderStatus.DELIVERED
    # the marketplace still calls it sent, which is what the next import compares with
    assert order.marketplace_status is OrderStatus.NEW


def test_the_move_is_in_the_history_with_no_author(session):
    _shipped_with(session, "ALG-1", "DELIVERED")

    _sync_nothing_new(session)

    last = OrderRepository(session).list_status_history(session.query(Order).one().id)[0]
    assert (last.from_status, last.to_status, last.changed_by_user_id) == (
        OrderStatus.SHIPPED,
        OrderStatus.DELIVERED,
        None,
    )


def test_a_parcel_still_on_its_way_keeps_the_order_sent(session):
    _shipped_with(session, "ALG-1", "IN_TRANSIT")
    _shipped_with(session, "ALG-2", None)
    _shipped_with(session, "ALG-3", "AVAILABLE_FOR_PICKUP")

    _sync_nothing_new(session)

    assert {o.status for o in session.query(Order).all()} == {OrderStatus.SHIPPED}


def test_one_parcel_not_yet_delivered_keeps_the_order_sent(session):
    _shipped_with(session, "ALG-1", "DELIVERED", "IN_TRANSIT")

    _sync_nothing_new(session)

    assert session.query(Order).one().status is OrderStatus.SHIPPED


def test_every_parcel_delivered_makes_a_multi_parcel_order_delivered(session):
    _shipped_with(session, "ALG-1", "DELIVERED", "DELIVERED")

    _sync_nothing_new(session)

    assert session.query(Order).one().status is OrderStatus.DELIVERED


def test_a_returned_parcel_is_not_a_delivery(session):
    _shipped_with(session, "ALG-1", "RETURNED")

    _sync_nothing_new(session)

    assert session.query(Order).one().status is OrderStatus.SHIPPED


def test_a_sent_order_without_a_parcel_stays_sent(session):
    _shipped_with(session, "ALG-1")

    _sync_nothing_new(session)

    assert session.query(Order).one().status is OrderStatus.SHIPPED


def test_an_order_deleted_in_anvero_is_not_settled(session):
    order = _shipped_with(session, "ALG-1", "DELIVERED")
    OrderRepository(session).mark_deleted(order, None)

    _sync_nothing_new(session)

    assert session.query(Order).one().status is OrderStatus.SHIPPED


def test_only_the_importing_marketplaces_orders_are_settled(session):
    order = _shipped_with(session, "ERL-1", "DELIVERED")
    order.source = OrderSource.ERLI
    session.commit()

    _sync_nothing_new(session)

    assert session.query(Order).one().status is OrderStatus.SHIPPED


# --- the pictures Anvero already holds ------------------------------------------------


def _with_item(external_id, offer_id, image_url, source=OrderSource.ALLEGRO):
    order = _order(external_id).model_copy(update={"source": source})
    order.items = [
        OrderItemCreate(
            name="Kubek", quantity=1, unit_price=Decimal("10.00"), offer_id=offer_id, image_url=image_url
        )
    ]
    return order


def test_a_stored_picture_is_found_by_offer(session):
    _service(session, [_with_item("ALG-1", "offer-1", "https://img/a.jpg")]).import_orders()

    found = OrderRepository(session).images_by_offer(OrderSource.ALLEGRO, ["offer-1", "offer-2"])

    assert found == {"offer-1": "https://img/a.jpg"}


def test_an_item_without_a_picture_is_not_a_held_picture(session):
    _service(session, [_with_item("ALG-1", "offer-1", None)]).import_orders()

    assert OrderRepository(session).images_by_offer(OrderSource.ALLEGRO, ["offer-1"]) == {}


def test_a_picture_is_held_per_marketplace(session):
    _service(session, [_with_item("ALG-1", "same-id", "https://img/a.jpg")]).import_orders()

    assert OrderRepository(session).images_by_offer(OrderSource.ERLI, ["same-id"]) == {}


def test_the_newest_picture_of_an_offer_wins(session):
    _service(session, [_with_item("ALG-1", "offer-1", "https://img/old.jpg")]).import_orders()
    _service(session, [_with_item("ALG-2", "offer-1", "https://img/new.jpg")]).import_orders()

    found = OrderRepository(session).images_by_offer(OrderSource.ALLEGRO, ["offer-1"])

    assert found == {"offer-1": "https://img/new.jpg"}
