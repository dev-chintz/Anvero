import logging

from app.integrations.allegro.adapter import AllegroAdapter
from app.models.order import OrderSource


class FakeClient:
    is_configured = True

    def __init__(self, checkout_forms, images=None):
        self.checkout_forms = checkout_forms
        self.calls = []
        self.image_calls = []
        self._images = images or {}

    def fetch_checkout_forms(self, limit=100, offset=0):
        self.calls.append((limit, offset))
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
