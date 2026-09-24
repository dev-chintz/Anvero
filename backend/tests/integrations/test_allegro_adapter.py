import logging
from datetime import UTC, datetime

from app.integrations.allegro.adapter import AllegroAdapter
from app.integrations.base import IntegrationUnavailable
from app.models.order import OrderSource


class FakeClient:
    is_configured = True

    def __init__(self, checkout_forms, images=None):
        self.checkout_forms = checkout_forms
        self.calls = []
        self.image_calls = []
        self._images = images or {}

    def fetch_checkout_forms(
        self, limit=100, offset=0, bought_since=None, updated_since=None
    ):
        self.calls.append((limit, offset))
        self.filters = (bought_since, updated_since)
        if callable(self.checkout_forms):
            return self.checkout_forms(offset)
        return self.checkout_forms

    def fetch_offer_image(self, offer_id):
        self.image_calls.append(offer_id)
        return self._images.get(offer_id)


def _form(external_id, **overrides):
    form = {
        "id": external_id,
        "status": "READY_FOR_PROCESSING",
        "fulfillment": {"status": "NEW"},
        "buyer": {"email": f"{external_id}@example.com"},
        "summary": {"totalToPay": {"amount": "99.00", "currency": "PLN"}},
    }
    form.update(overrides)
    return form


def test_returns_domain_orders_not_raw_payloads():
    adapter = AllegroAdapter(client=FakeClient([_form("ALG-1")]))

    orders = adapter.fetch_orders()

    assert len(orders) == 1
    assert orders[0].source is OrderSource.ALLEGRO
    assert orders[0].external_id == "ALG-1"


def test_one_unmappable_order_does_not_cost_the_rest_of_the_page(caplog):
    """A single malformed order must not lose the whole batch, but the gap
    has to be visible in the log rather than silent."""
    broken = _form("ALG-BAD")
    broken.pop("summary")
    adapter = AllegroAdapter(client=FakeClient([_form("ALG-1"), broken, _form("ALG-2")]))

    with caplog.at_level(logging.WARNING):
        orders = adapter.fetch_orders()

    assert [order.external_id for order in orders] == ["ALG-1", "ALG-2"]
    assert "ALG-BAD" in caplog.text


def test_an_order_failing_domain_validation_is_skipped_not_fatal(caplog):
    """Regression: an email the domain model rejects used to abort the page."""
    bad_email = _form("ALG-BAD-EMAIL", buyer={"email": "not-an-email"})
    adapter = AllegroAdapter(
        client=FakeClient([_form("ALG-1"), bad_email, _form("ALG-2")])
    )

    with caplog.at_level(logging.WARNING):
        orders = adapter.fetch_orders()

    assert [order.external_id for order in orders] == ["ALG-1", "ALG-2"]
    assert "ALG-BAD-EMAIL" in caplog.text
    assert "not-an-email" not in caplog.text


def test_passes_pagination_through_to_the_client():
    client = FakeClient([])
    AllegroAdapter(client=client).fetch_orders(limit=25, offset=50)

    assert client.calls == [(25, 50)]


def _line_item(offer_id, **overrides):
    item = {
        "id": f"li-{offer_id}",
        "offer": {"id": offer_id, "name": "Widget"},
        "quantity": 1,
        "price": {"amount": "10.00", "currency": "PLN"},
    }
    item.update(overrides)
    return item


def test_attaches_each_items_image_from_the_client():
    form = _form("ALG-1", lineItems=[_line_item("offer-1")])
    client = FakeClient([form], images={"offer-1": "https://img.test/a.jpg"})

    orders = AllegroAdapter(client=client).fetch_orders()

    assert orders[0].items[0].image_url == "https://img.test/a.jpg"


def test_fetches_each_distinct_offer_only_once_per_page():
    """Two orders for the same offer must not double the image requests."""
    forms = [
        _form("ALG-1", lineItems=[_line_item("offer-1")]),
        _form("ALG-2", lineItems=[_line_item("offer-1")]),
    ]
    client = FakeClient(forms, images={"offer-1": "https://img.test/a.jpg"})

    orders = AllegroAdapter(client=client).fetch_orders()

    assert client.image_calls == ["offer-1"]
    assert all(order.items[0].image_url == "https://img.test/a.jpg" for order in orders)


def test_an_image_the_client_could_not_fetch_leaves_the_item_without_one():
    form = _form("ALG-1", lineItems=[_line_item("offer-missing")])
    client = FakeClient([form], images={})

    orders = AllegroAdapter(client=client).fetch_orders()

    assert orders[0].items[0].image_url is None


def test_pages_through_everything_and_stops_on_a_short_raw_page():
    full = [_form(f"ALG-{i}") for i in range(100)]
    client = FakeClient(lambda offset: {0: full, 100: full, 200: [_form("ALG-LAST")]}[offset])

    pages = list(AllegroAdapter(client=client).iter_order_pages())

    assert [len(page) for page in pages] == [100, 100, 1]
    assert [call[1] for call in client.calls] == [0, 100, 200]


def test_an_unmappable_order_does_not_end_the_paging_early():
    """A full raw page with one order dropped is still a full page: counting
    what is left would stop here and leave every later page unfetched."""
    broken = _form("ALG-BAD")
    broken.pop("summary")
    full = [broken] + [_form(f"ALG-{i}") for i in range(99)]
    client = FakeClient(lambda offset: {0: full, 100: [_form("ALG-LAST")]}[offset])

    pages = list(AllegroAdapter(client=client).iter_order_pages())

    assert [len(page) for page in pages] == [99, 1]


def test_passes_the_time_filters_to_every_page():
    since = datetime(2026, 9, 14, tzinfo=UTC)
    client = FakeClient([])

    list(AllegroAdapter(client=client).iter_order_pages(updated_since=since))

    assert client.filters == (None, since)


def test_running_out_of_pages_is_an_error_not_a_quiet_stop(monkeypatch):
    monkeypatch.setattr("app.integrations.allegro.adapter.MAX_PAGES", 2)
    full = [_form(f"ALG-{i}") for i in range(100)]
    client = FakeClient(full)

    try:
        list(AllegroAdapter(client=client).iter_order_pages())
    except IntegrationUnavailable as exc:
        assert "more than 200 orders" in str(exc)
    else:
        raise AssertionError("expected IntegrationUnavailable")


class StatusFakeClient(FakeClient):
    """Serves a different set of orders for each seller status asked for."""

    def __init__(self, by_status):
        super().__init__([])
        self.by_status = by_status
        self.statuses = []

    def fetch_checkout_forms(
        self, limit=100, offset=0, bought_since=None, updated_since=None, fulfillment_status=None
    ):
        self.statuses.append((fulfillment_status, offset))
        forms = self.by_status.get(fulfillment_status, [])
        return forms[offset : offset + limit]

    def fetch_shipments(self, order_id):
        return []


def test_open_orders_are_read_one_seller_status_at_a_time():
    from app.integrations.allegro.adapter import OPEN_FULFILLMENT_STATUSES

    client = StatusFakeClient(
        {
            "PROCESSING": [_form("ALG-1", fulfillment={"status": "PROCESSING"})],
            "READY_FOR_SHIPMENT": [_form("ALG-2", fulfillment={"status": "READY_FOR_SHIPMENT"})],
        }
    )

    pages = list(AllegroAdapter(client=client).iter_open_order_pages())

    assert [o.external_id for page in pages for o in page] == ["ALG-1", "ALG-2"]
    # every open status is asked for, and a finished one never is
    assert [status for status, _ in client.statuses] == list(OPEN_FULFILLMENT_STATUSES)
    assert "SENT" not in OPEN_FULFILLMENT_STATUSES
    assert "CANCELLED" not in OPEN_FULFILLMENT_STATUSES


def test_open_orders_are_paged_within_a_status():
    forms = [_form(f"ALG-{i}", fulfillment={"status": "PROCESSING"}) for i in range(101)]
    client = StatusFakeClient({"PROCESSING": forms})

    orders = [o for page in AllegroAdapter(client=client).iter_open_order_pages() for o in page]

    assert len(orders) == 101
    assert [offset for status, offset in client.statuses if status == "PROCESSING"] == [0, 100]
