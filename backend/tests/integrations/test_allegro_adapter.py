import logging

from app.integrations.allegro.adapter import AllegroAdapter
from app.models.order import OrderSource


class FakeClient:
    is_configured = True

    def __init__(self, checkout_forms):
        self.checkout_forms = checkout_forms
        self.calls = []

    def fetch_checkout_forms(self, limit=100, offset=0):
        self.calls.append((limit, offset))
        return self.checkout_forms


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
