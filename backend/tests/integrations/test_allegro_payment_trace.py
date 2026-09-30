"""What traces an order's money, for the non-invoiced sales record (docs/NON_INVOICED_SALES.md):
the payment's id, surcharges and cash on delivery, whether the invoice names a company, the tax
an item's offer declares, and the payment operations that tie the money to the bank.

Shaped by Allegro's published OpenAPI specification (`CheckoutForm`, `PaymentOperations` and
its operation types); no real response has been seen with these fields yet.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.integrations.allegro.adapter import AllegroAdapter
from app.integrations.allegro.client import PAYMENT_OPERATIONS_PAGE_SIZE
from app.integrations.allegro.mapper import map_checkout_form, map_details, map_payment_operation
from app.integrations.base import IntegrationAuthError
from app.models.integration import IntegrationCredential
from app.models.order import Order, OrderPayment, OrderPaymentKind, OrderSource, PaymentOperation, PaymentType
from app.repositories.integration_credential_repository import IntegrationCredentialRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderDetailRead
from app.services.order_details import apply_details
from app.services.order_import_service import (
    PAYMENT_OPERATIONS_OVERLAP,
    UNTRACED_ORDERS_PER_RUN,
    OrderImportService,
    start_of_previous_month,
)
from tests.integrations.test_allegro_mapper import _checkout_form


# --- the order's own fields -------------------------------------------------


def test_keeps_the_payments_id_and_the_delivery_methods():
    details = map_details(_checkout_form())

    assert details.payment.id == "p-1"
    assert details.delivery.method_id == "m-1"


def test_an_invoice_with_a_company_is_a_company_purchase_with_its_vat_status():
    details = map_details(_checkout_form())

    assert details.invoice.is_company is True
    assert details.invoice.vat_payer_status == "ACTIVE"


def test_an_invoice_with_the_company_null_is_a_private_purchase():
    form = _checkout_form()
    form["invoice"]["address"]["company"] = None
    form["invoice"]["address"]["naturalPerson"] = {"firstName": "Jan", "lastName": "Kowalski"}

    details = map_details(form)

    assert details.invoice.is_company is False
    assert details.invoice.vat_payer_status is None


def test_an_order_without_invoice_data_says_neither():
    details = map_details(_checkout_form(invoice={"required": False, "address": None}))

    assert details.invoice.is_company is None


def test_keeps_the_tax_the_offer_declares_and_none_where_it_declares_none():
    form = _checkout_form()
    form["lineItems"].append(
        dict(form["lineItems"][0], id="li-2", tax={"rate": "23.00", "subject": "GOODS", "exemption": None})
    )

    items = map_details(form).items

    assert (items[0].tax_rate, items[0].tax_subject) == (None, None)
    assert (items[1].tax_rate, items[1].tax_subject, items[1].tax_exemption) == ("23.00", "GOODS", None)


def test_surcharges_and_cash_on_delivery_become_payments_of_their_own():
    form = _checkout_form(
        surcharges=[
            {
                "id": "s-1",
                "type": "ONLINE",
                "provider": "PAYU",
                "finishedAt": "2026-09-15T08:00:00.000Z",
                "paidAmount": {"amount": "10.00", "currency": "PLN"},
            }
        ],
        codBookedPayments=[
            {
                "paymentId": "cod-1",
                "shipmentId": "sh-1",
                "paidAmount": {"amount": "50.00", "currency": "PLN"},
                "paidAt": "2026-09-16T12:00:00.000Z",
            }
        ],
    )

    surcharge, cash = map_details(form).extra_payments

    assert (surcharge.kind, surcharge.external_id, surcharge.payment_type, surcharge.provider) == (
        OrderPaymentKind.SURCHARGE, "s-1", PaymentType.ONLINE, "PAYU"
    )
    assert (surcharge.paid_amount, surcharge.currency) == (Decimal("10.00"), "PLN")
    assert surcharge.paid_at == datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
    assert (cash.kind, cash.external_id, cash.payment_type, cash.paid_amount) == (
        OrderPaymentKind.CASH_ON_DELIVERY, "cod-1", PaymentType.CASH_ON_DELIVERY, Decimal("50.00")
    )


def test_an_order_without_either_has_no_extra_payments():
    assert map_details(_checkout_form()).extra_payments == []


def test_all_of_it_is_stored_on_the_order_and_replaced_by_a_reimport(session):
    form = _checkout_form(
        surcharges=[{"id": "s-1", "type": "ONLINE", "provider": "PAYU", "paidAmount": {"amount": "10.00", "currency": "PLN"}}]
    )
    form["lineItems"][0]["tax"] = {"rate": "23.00"}
    created = map_checkout_form(form)
    order = Order(
        source=OrderSource.ALLEGRO,
        external_id=created.external_id,
        status=created.status,
        customer_email=created.customer_email,
        total_amount=created.total_amount,
        currency=created.currency,
        ordered_at=created.ordered_at,
    )
    session.add(order)
    apply_details(order, map_details(form))
    session.commit()

    assert (order.payment_id, order.delivery_method_id, order.invoice_is_company, order.invoice_vat_payer_status) == (
        "p-1", "m-1", True, "ACTIVE"
    )
    assert order.items[0].tax_rate == "23.00"
    assert [(p.kind, p.external_id) for p in order.extra_payments] == [(OrderPaymentKind.SURCHARGE, "s-1")]

    apply_details(order, map_details(_checkout_form()))
    session.commit()

    assert order.extra_payments == []
    assert session.query(OrderPayment).count() == 0


# --- payment operations -----------------------------------------------------


def _operation(type_="CONTRIBUTION", group="INCOME", amount="167.00", balance="167.00", **extra):
    operation = {
        "type": type_,
        "group": group,
        "wallet": {"paymentOperator": "P24", "type": "WAITING", "balance": {"amount": balance, "currency": "PLN"}},
        "value": {"amount": amount, "currency": "PLN"},
        "occurredAt": "2026-09-14T10:01:05.000Z",
        "marketplaceId": "allegro-pl",
        "payment": {"id": "p-1"},
        "participant": {"login": "buyer_login", "id": "buyer-1"},
    }
    operation.update(extra)
    return operation


def test_a_buyers_payment_is_kept_with_its_payment_id_and_wallet():
    operation = map_payment_operation(_operation())

    assert operation is not None
    assert (operation.source, operation.type, operation.group, operation.payment_id) == (
        OrderSource.ALLEGRO, "CONTRIBUTION", "INCOME", "p-1"
    )
    assert (operation.amount, operation.currency, operation.wallet_operator, operation.wallet_type) == (
        Decimal("167.00"), "PLN", "P24", "WAITING"
    )
    assert operation.wallet_balance == Decimal("167.00")
    assert operation.occurred_at == datetime(2026, 9, 14, 10, 1, 5, tzinfo=UTC)
    assert len(operation.fingerprint) == 64


def test_the_buyers_login_is_not_kept():
    operation = map_payment_operation(_operation())

    assert "buyer_login" not in operation.model_dump_json()


def test_a_refund_keeps_its_sign_and_a_payout_its_id():
    refund = map_payment_operation(_operation("REFUND_CHARGE", "REFUND", amount="-167.00", balance="0.00"))
    payout = map_payment_operation(
        _operation("PAYOUT", "OUTCOME", amount="-500.00", balance="0.00", payment=None, payout={"id": "po-1"})
    )

    assert (refund.amount, refund.payment_id) == (Decimal("-167.00"), "p-1")
    assert (payout.amount, payout.payout_id, payout.payment_id) == (Decimal("-500.00"), "po-1", None)


def test_the_same_operation_read_twice_has_the_same_fingerprint():
    assert map_payment_operation(_operation()).fingerprint == map_payment_operation(_operation()).fingerprint


def test_operations_that_differ_only_in_the_balance_after_them_are_two():
    first = map_payment_operation(_operation(balance="167.00"))
    second = map_payment_operation(_operation(balance="334.00"))

    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize(
    "raw",
    [_operation(type=None), _operation(group=None), _operation(occurredAt=None), _operation(amount="lots")],
)
def test_an_operation_without_what_makes_one_is_skipped(raw):
    assert map_payment_operation(raw) is None


class FakeClient:
    def __init__(self, pages_by_group):
        self.pages_by_group = pages_by_group
        self.calls = []

    def fetch_payment_operations(self, since, group, limit, offset):
        self.calls.append((group, offset))
        pages = self.pages_by_group.get(group, [])
        index = offset // limit
        return pages[index] if index < len(pages) else []


def test_reads_every_page_of_payments_refunds_and_payouts():
    full = [_operation(balance=str(n)) for n in range(PAYMENT_OPERATIONS_PAGE_SIZE)]
    client = FakeClient(
        {
            "INCOME": [full, [_operation(balance="x-last")]],
            "REFUND": [[_operation("REFUND_CHARGE", "REFUND", amount="-1.00")]],
            "OUTCOME": [[_operation("PAYOUT", "OUTCOME", payment=None, payout={"id": "po-1"}), _operation(type=None)]],
        }
    )

    operations = AllegroAdapter(client=client).fetch_payment_operations(datetime(2026, 9, 1, tzinfo=UTC))

    assert [c[0] for c in client.calls] == ["INCOME", "INCOME", "REFUND", "OUTCOME"]
    assert client.calls[1] == ("INCOME", PAYMENT_OPERATIONS_PAGE_SIZE)
    # one unreadable operation skipped, one with an unreadable balance kept without it
    assert len(operations) == PAYMENT_OPERATIONS_PAGE_SIZE + 1 + 1 + 1
    assert {o.group for o in operations} == {"INCOME", "REFUND", "OUTCOME"}


# --- the import -------------------------------------------------------------


def test_the_first_read_reaches_back_to_the_previous_months_first_day():
    assert start_of_previous_month(datetime(2026, 10, 3, 14, 0, tzinfo=UTC)) == datetime(2026, 9, 1, tzinfo=UTC)
    assert start_of_previous_month(datetime(2026, 1, 20, tzinfo=UTC)) == datetime(2025, 12, 1, tzinfo=UTC)


class OperationsAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, operations=None, error=None):
        self.operations = operations or []
        self.error = error
        self.since = []

    def fetch_payment_operations(self, since):
        self.since.append(since)
        if self.error:
            raise self.error
        return self.operations


def _service(session, adapter):
    session.add(IntegrationCredential(provider="ALLEGRO", refresh_token="t", seed_fingerprint="f"))
    session.commit()
    return OrderImportService(
        OrderRepository(session), adapter, credentials=IntegrationCredentialRepository(session), initial_days=7
    )


def test_operations_are_stored_once_and_read_again_from_a_day_before_the_latest(session):
    operation = map_payment_operation(_operation())
    adapter = OperationsAdapter([operation])
    service = _service(session, adapter)
    started = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)

    assert service._sync_payment_operations(started) == 1
    assert service._sync_payment_operations(started) == 0

    assert session.query(PaymentOperation).count() == 1
    assert adapter.since[0] == datetime(2026, 9, 1, tzinfo=UTC)
    assert adapter.since[1] == operation.occurred_at - PAYMENT_OPERATIONS_OVERLAP


def test_a_refused_read_of_the_operations_does_not_fail_the_import(session):
    service = _service(session, OperationsAdapter(error=IntegrationAuthError("missing allegro:api:payments:read")))

    assert service._sync_payment_operations(datetime.now(UTC)) == 0
    assert session.query(PaymentOperation).count() == 0


def _stored_order(session, external_id, paid_at, payment_id=None, source=OrderSource.ALLEGRO):
    order = Order(
        source=source,
        external_id=external_id,
        status=map_checkout_form(_checkout_form()).status,
        customer_email="buyer@example.com",
        total_amount=Decimal("10.00"),
        currency="PLN",
        ordered_at=paid_at or datetime(2026, 9, 10, tzinfo=UTC),
        paid_at=paid_at,
        payment_id=payment_id,
    )
    session.add(order)
    session.commit()
    return order


def test_paid_orders_stored_without_a_payment_id_are_named_oldest_first(session):
    since = datetime(2026, 9, 1, tzinfo=UTC)
    _stored_order(session, "late", datetime(2026, 9, 20, tzinfo=UTC))
    _stored_order(session, "early", datetime(2026, 9, 2, tzinfo=UTC))
    _stored_order(session, "traced", datetime(2026, 9, 5, tzinfo=UTC), payment_id="p-9")
    _stored_order(session, "unpaid", None)
    _stored_order(session, "august", datetime(2026, 8, 31, tzinfo=UTC))
    _stored_order(session, "erli", datetime(2026, 9, 3, tzinfo=UTC), source=OrderSource.ERLI)

    assert OrderRepository(session).untraced_paid_external_ids(OrderSource.ALLEGRO, since, 10) == ["early", "late"]
    assert OrderRepository(session).untraced_paid_external_ids(OrderSource.ALLEGRO, since, 1) == ["early"]


class ByIdAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, traces_payments):
        self.traces_payments = traces_payments
        self.asked = []

    def fetch_orders_by_id(self, external_ids):
        self.asked.append(list(external_ids))
        return []


@pytest.mark.parametrize("traces", [True, False])
def test_untraced_orders_are_read_again_only_where_the_marketplace_gives_the_id(session, traces):
    _stored_order(session, "early", datetime(2026, 9, 2, tzinfo=UTC))
    _stored_order(session, "already-read", datetime(2026, 9, 3, tzinfo=UTC))
    adapter = ByIdAdapter(traces)
    service = _service(session, adapter)

    service._read_untraced_orders({"already-read"}, datetime(2026, 10, 1, tzinfo=UTC))

    assert adapter.asked == ([["early"]] if traces else [])


def test_no_more_untraced_orders_than_the_limit_are_asked_for_in_one_import(session):
    for day in range(UNTRACED_ORDERS_PER_RUN + 5):
        _stored_order(session, f"o-{day}", datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=day))
    adapter = ByIdAdapter(True)

    _service(session, adapter)._read_untraced_orders(set(), datetime(2026, 10, 1, tzinfo=UTC))

    assert len(adapter.asked[0]) == UNTRACED_ORDERS_PER_RUN


def test_the_allegro_adapter_keeps_the_payment_id():
    assert AllegroAdapter(client=FakeClient({})).traces_payments is True


def test_an_order_read_back_shows_its_payment_id_and_extra_payments(session):
    order = _stored_order(session, "o-1", datetime(2026, 9, 2, tzinfo=UTC), payment_id="p-1")
    order.extra_payments = [
        OrderPayment(position=0, kind=OrderPaymentKind.SURCHARGE, external_id="s-1", paid_amount=Decimal("5.00"))
    ]
    session.commit()

    read = OrderDetailRead.from_order(order)

    assert read.payment.id == "p-1"
    assert [p.external_id for p in read.extra_payments] == ["s-1"]
