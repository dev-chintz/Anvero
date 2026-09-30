"""The ledger of the non-invoiced sales record (docs/NON_INVOICED_SALES.md, 4b, 4c, 4d; stage 3):
what is written after an import, what follows the order and what never does, corrections from
refunds and from changes after a report was handed over, overrides, the payout link, excluded
goods, and the buyer copy's retention."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.integration import IntegrationCredential
from app.models.non_invoiced import PAYOUT_FIRST_AFTER, LedgerEntry, LedgerKind
from app.models.order import (
    AddressType,
    Order,
    OrderAddress,
    OrderItem,
    OrderPayment,
    OrderPaymentKind,
    OrderSource,
    OrderStatus,
    PaymentOperation,
    PaymentType,
)
from app.repositories.integration_credential_repository import IntegrationCredentialRepository
from app.repositories.non_invoiced_repository import NonInvoicedRepository
from app.repositories.order_repository import OrderRepository
from app.services import order_import_service
from app.services.non_invoiced.classifier import Category, Reason
from app.services.non_invoiced.ledger import (
    OverrideRefused,
    business_date,
    clear_override,
    decide,
    effective_category,
    link_payout,
    reclassification_amount,
    set_override,
    write_ledger,
)
from app.services.order_import_service import OrderImportService, start_of_previous_month
from app.services.personal_data import anonymize_person, export_person, find_person
from app.services.retention import apply_retention

NOW = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)
SINCE = start_of_previous_month(NOW)
PAID_AT = datetime(2026, 9, 14, 10, 1, tzinfo=UTC)


def _order(session, external_id="o-1", **changes) -> Order:
    """A private buyer's courier order, paid in full through Przelewy24."""
    order = Order(
        source=OrderSource.ALLEGRO,
        external_id=external_id,
        status=OrderStatus.SHIPPED,
        customer_email="buyer@example.com",
        customer_login="jan_k",
        customer_first_name="Jan",
        customer_last_name="Kowalski",
        total_amount=Decimal("167.00"),
        currency="PLN",
        ordered_at=PAID_AT - timedelta(minutes=2),
        payment_type=PaymentType.ONLINE,
        payment_provider="P24",
        paid_amount=Decimal("167.00"),
        paid_at=PAID_AT,
        payment_id=f"pay-{external_id}",
        delivery_method="Allegro Kurier DPD",
    )
    order.addresses = [
        OrderAddress(type=AddressType.BUYER, first_name="Jan", last_name="Kowalski", street="Lipowa 3", postal_code="80-001", city="Gdańsk", country_code="PL"),
        OrderAddress(type=AddressType.DELIVERY, first_name="Anna", last_name="Nowak", street="Prosta 1", postal_code="00-001", city="Warszawa", country_code="PL"),
    ]
    order.items = [OrderItem(position=0, offer_id="offer-1", name="Kubek", quantity=1, unit_price=Decimal("152.00"))]
    for key, value in changes.items():
        setattr(order, key, value)
    session.add(order)
    session.commit()
    return order


_seq = iter(range(1_000_000))


def _op(session, type_="CONTRIBUTION", group="INCOME", payment_id=None, amount="167.00", occurred_at=PAID_AT, **changes):
    operation = PaymentOperation(
        source=OrderSource.ALLEGRO,
        fingerprint=f"fp-{next(_seq)}",
        type=type_,
        group=group,
        occurred_at=occurred_at,
        amount=Decimal(amount),
        currency="PLN",
        wallet_operator="P24",
        wallet_type="WAITING",
        payment_id=payment_id,
    )
    for key, value in changes.items():
        setattr(operation, key, value)
    session.add(operation)
    session.commit()
    return operation


def _write(session, now=NOW, since=SINCE):
    return write_ledger(session, OrderSource.ALLEGRO, since=since, now=now)


def _rows(session, kind=None) -> list[LedgerEntry]:
    query = session.query(LedgerEntry)
    if kind is not None:
        query = query.filter(LedgerEntry.kind == kind)
    return query.order_by(LedgerEntry.entry_at, LedgerEntry.event_key).all()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- sales -----------------------------------------------------------------------------------


def test_a_paid_order_becomes_one_sale_dated_its_payment_and_writing_again_adds_nothing(session):
    _order(session)
    _op(session, payment_id="pay-o-1")

    first = _write(session)
    second = _write(session)

    (sale,) = _rows(session)
    assert (first.sales, second.sales, second.corrections) == (1, 0, 0)
    assert (sale.kind, sale.event_key, sale.amount, sale.currency) == (LedgerKind.SALE, "ORDER:o-1", Decimal("167.00"), "PLN")
    assert _utc(sale.entry_at) == PAID_AT and sale.entry_date == date(2026, 9, 14)
    assert (sale.category, sale.reason) == (Category.EXEMPT_MAIL_ORDER.value, Reason.E41.value)
    assert (sale.payment_type, sale.payment_operator, sale.payment_id) == (PaymentType.ONLINE, "P24", "pay-o-1")
    assert sale.operation_fingerprint is not None


def test_the_buyer_and_their_own_address_are_copied_not_the_recipients(session):
    order = _order(session)
    _write(session)

    (sale,) = _rows(session)
    assert (sale.buyer_first_name, sale.buyer_last_name) == ("Jan", "Kowalski")
    assert (sale.buyer_street, sale.buyer_postal_code, sale.buyer_city, sale.buyer_country_code) == ("Lipowa 3", "80-001", "Gdańsk", "PL")
    assert (sale.order_id, sale.order_number, sale.order_external_id) == (order.id, order.order_number, "o-1")


def test_the_entry_date_is_the_payments_day_where_the_business_is():
    # 22:30 UTC on 30 September is 00:30 on 1 October in Warsaw
    assert business_date(datetime(2026, 9, 30, 22, 30, tzinfo=UTC)) == date(2026, 10, 1)
    assert business_date(datetime(2026, 9, 30, 22, 30)) == date(2026, 10, 1)


def test_an_order_never_paid_gets_no_row(session):
    _order(session, paid_at=None, paid_amount=None)
    _order(session, "zero", paid_amount=Decimal("0.00"))

    assert _write(session).sales == 0
    assert _rows(session) == []


def test_an_order_paid_before_the_period_is_not_written(session):
    _order(session, paid_at=datetime(2026, 8, 31, 21, 0, tzinfo=UTC))

    assert _write(session).sales == 0


def test_each_surcharge_is_a_sale_of_its_own_dated_its_own_payment(session):
    order = _order(session, total_amount=Decimal("177.00"))
    surcharge_paid = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)
    order.extra_payments = [
        OrderPayment(
            position=0,
            kind=OrderPaymentKind.SURCHARGE,
            external_id="s-1",
            payment_type=PaymentType.ONLINE,
            provider="PAYU",
            paid_amount=Decimal("10.00"),
            currency="PLN",
            paid_at=surcharge_paid,
        ),
        # cash is never a sale of its own here; it makes the order NEEDS_REGISTER instead
        OrderPayment(position=1, kind=OrderPaymentKind.CASH_ON_DELIVERY, external_id="cod-1", paid_amount=Decimal("0.00")),
    ]
    session.commit()
    _op(session, payment_id="pay-o-1")
    _op(session, "SURCHARGE", payment_id="s-1", amount="10.00", occurred_at=surcharge_paid, wallet_operator="PAYU")

    _write(session)
    _write(session)

    main, surcharge = _rows(session)
    assert (main.event_key, main.amount) == ("ORDER:o-1", Decimal("167.00"))
    assert (surcharge.event_key, surcharge.amount, surcharge.payment_id, surcharge.payment_operator) == (
        "SURCHARGE:s-1", Decimal("10.00"), "s-1", "PAYU"
    )
    assert _utc(surcharge.entry_at) == surcharge_paid
    assert surcharge.category == main.category == Category.EXEMPT_MAIL_ORDER.value
    assert surcharge.operation_fingerprint is not None


def test_an_order_whose_surcharge_was_paid_in_the_period_is_read_though_the_order_was_paid_before(session):
    order = _order(session, paid_at=datetime(2026, 8, 20, tzinfo=UTC))
    order.extra_payments = [
        OrderPayment(position=0, kind=OrderPaymentKind.SURCHARGE, external_id="s-1", paid_amount=Decimal("10.00"), paid_at=datetime(2026, 9, 2, tzinfo=UTC))
    ]
    session.commit()

    _write(session)

    assert {row.event_key for row in _rows(session)} == {"ORDER:o-1", "SURCHARGE:s-1"}


# --- corrections from refunds ------------------------------------------------------------------


def test_a_refund_is_a_negative_correction_and_its_cancelling_a_positive_one(session):
    _order(session)
    _op(session, payment_id="pay-o-1")
    refunded = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    _op(session, "REFUND_CHARGE", "REFUND", payment_id="pay-o-1", amount="-167.00", occurred_at=refunded)
    _op(session, "REFUND_CANCEL", "REFUND", payment_id="pay-o-1", amount="167.00", occurred_at=refunded + timedelta(hours=1))

    first = _write(session)
    second = _write(session)

    sale = _rows(session, LedgerKind.SALE)[0]
    refund, cancel = _rows(session, LedgerKind.CORRECTION)
    assert (first.corrections, second.corrections) == (2, 0)
    assert (refund.amount, _utc(refund.entry_at), refund.entry_date) == (Decimal("-167.00"), refunded, date(2026, 9, 20))
    assert cancel.amount == Decimal("167.00")
    assert refund.corrects_entry_id == cancel.corrects_entry_id == sale.id
    assert refund.category == cancel.category == Category.EXEMPT_MAIL_ORDER.value
    assert (refund.buyer_last_name, refund.buyer_city, refund.order_number) == ("Kowalski", "Gdańsk", sale.order_number)
    assert refund.event_key.startswith("OPERATION:") and refund.operation_fingerprint in refund.event_key


def test_a_refund_of_a_sale_the_ledger_never_held_is_not_a_correction(session):
    _order(session, "august", paid_at=datetime(2026, 8, 10, tzinfo=UTC))
    _op(session, "REFUND_CHARGE", "REFUND", payment_id="pay-august", amount="-167.00", occurred_at=datetime(2026, 9, 5, tzinfo=UTC))

    assert _write(session).corrections == 0
    assert _rows(session) == []


def test_a_refund_of_a_sale_paid_before_the_period_is_a_correction_of_it(session):
    order = _order(session, paid_at=datetime(2026, 9, 3, tzinfo=UTC))
    _write(session)
    # a month later the sale is before the period the writer reads, but its refund is in it
    later = datetime(2026, 11, 2, tzinfo=UTC)
    _op(session, "REFUND_CHARGE", "REFUND", payment_id=order.payment_id, amount="-20.00", occurred_at=datetime(2026, 10, 15, tzinfo=UTC))

    assert _write(session, now=later, since=start_of_previous_month(later)).corrections == 1


def test_a_refund_follows_its_sale_into_the_report_while_neither_is_locked(session):
    _order(session)
    _op(session, "REFUND_CHARGE", "REFUND", payment_id="pay-o-1", amount="-50.00", occurred_at=datetime(2026, 9, 20, tzinfo=UTC))
    _write(session)
    assert {row.category for row in _rows(session)} == {Category.TO_REVIEW.value}

    # its payment arrives at the operator later: the sale and its refund move together
    _op(session, payment_id="pay-o-1")
    result = _write(session)

    assert result.reclassified == 1 and result.corrections == 0
    assert {row.category for row in _rows(session)} == {Category.EXEMPT_MAIL_ORDER.value}


# --- classified again before a lock, corrected after it ------------------------------------------


def test_before_a_lock_only_the_classification_follows_the_order(session):
    order = _order(session)
    _op(session, payment_id="pay-o-1")
    _write(session)

    order.invoice_is_company = True
    order.customer_first_name = "Zmieniony"
    order.paid_amount = Decimal("999.00")
    order.address(AddressType.BUYER).city = "Sopot"
    session.commit()
    result = _write(session)

    (sale,) = _rows(session)
    assert result.reclassified == 1
    assert (sale.category, sale.reason) == (Category.BUSINESS.value, Reason.COMPANY.value)
    assert (sale.amount, sale.buyer_first_name, sale.buyer_city, _utc(sale.entry_at)) == (Decimal("167.00"), "Jan", "Gdańsk", PAID_AT)


def test_after_a_lock_a_sale_leaving_the_report_is_corrected_not_changed(session):
    order = _order(session)
    _op(session, payment_id="pay-o-1")
    _write(session)
    (sale,) = _rows(session)
    NonInvoicedRepository(session).lock([sale.id], NOW)

    order.marketplace_cancelled_at = datetime(2026, 10, 5, tzinfo=UTC)
    session.commit()
    found = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)
    result = _write(session, now=found)
    again = _write(session, now=found + timedelta(hours=1))

    session.refresh(sale)
    (correction,) = _rows(session, LedgerKind.CORRECTION)
    assert (result.corrections, again.corrections, result.reclassified) == (1, 0, 0)
    assert (sale.category, sale.reason, sale.amount) == (Category.EXEMPT_MAIL_ORDER.value, Reason.E41.value, Decimal("167.00"))
    assert (correction.amount, _utc(correction.entry_at), correction.entry_date) == (Decimal("-167.00"), found, date(2026, 10, 6))
    assert (correction.category, correction.reason) == (Category.EXEMPT_MAIL_ORDER.value, Reason.CANCELLED_AFTER_PAYMENT.value)
    assert correction.corrects_entry_id == sale.id

    # and back into the report: the money is added again
    order.marketplace_cancelled_at = None
    session.commit()

    assert _write(session, now=found + timedelta(days=1)).corrections == 1
    assert sorted(c.amount for c in _rows(session, LedgerKind.CORRECTION)) == [Decimal("-167.00"), Decimal("167.00")]


def test_after_a_lock_a_sale_entering_the_report_is_added_by_a_correction(session):
    _order(session)
    _write(session)
    (sale,) = _rows(session)
    assert sale.category == Category.TO_REVIEW.value
    NonInvoicedRepository(session).lock([sale.id], NOW)

    _op(session, payment_id="pay-o-1")
    _write(session, now=NOW + timedelta(days=2))

    session.refresh(sale)
    (correction,) = _rows(session, LedgerKind.CORRECTION)
    assert sale.category == Category.TO_REVIEW.value
    assert (correction.amount, correction.category, correction.reason) == (Decimal("167.00"), Category.EXEMPT_MAIL_ORDER.value, Reason.E41.value)


def test_a_locked_sale_leaving_the_report_takes_its_locked_refund_with_it(session):
    order = _order(session)
    _op(session, payment_id="pay-o-1")
    _op(session, "REFUND_CHARGE", "REFUND", payment_id="pay-o-1", amount="-67.00", occurred_at=datetime(2026, 9, 20, tzinfo=UTC))
    _write(session)
    NonInvoicedRepository(session).lock([row.id for row in _rows(session)], NOW)

    order.invoice_is_company = True
    session.commit()
    _write(session, now=NOW + timedelta(days=1))

    moved = [c for c in _rows(session, LedgerKind.CORRECTION) if c.event_key.startswith("RECLASSIFIED:")]
    assert [c.amount for c in moved] == [Decimal("-100.00")]


def test_a_changed_order_that_changes_nothing_in_the_report_writes_nothing_after_a_lock(session):
    order = _order(session)
    _write(session)
    NonInvoicedRepository(session).lock([_rows(session)[0].id], NOW)

    # from one reason to review to another: out of the report either way
    order.delivery_method = None
    session.commit()

    assert _write(session).corrections == 0


def test_reclassification_amount_moves_only_what_the_report_carries_wrongly():
    sale = LedgerEntry(kind=LedgerKind.SALE, event_key="ORDER:x", amount=Decimal("100.00"), category="EXEMPT_MAIL_ORDER")
    refund = LedgerEntry(kind=LedgerKind.CORRECTION, event_key="OPERATION:f", amount=Decimal("-30.00"), category="EXEMPT_MAIL_ORDER")
    moved = LedgerEntry(kind=LedgerKind.CORRECTION, event_key="RECLASSIFIED:x:1", amount=Decimal("-70.00"), category="EXEMPT_MAIL_ORDER")

    assert reclassification_amount(sale, [refund], in_report=True) == 0
    assert reclassification_amount(sale, [refund], in_report=False) == Decimal("-70.00")
    assert reclassification_amount(sale, [refund, moved], in_report=False) == 0
    assert reclassification_amount(sale, [refund, moved], in_report=True) == Decimal("70.00")


# --- overrides ---------------------------------------------------------------------------------


def _to_review(session):
    _order(session)
    _write(session)
    return _rows(session)[0]


def test_an_override_counts_beside_the_automatic_result_it_leaves_alone(session):
    sale = _to_review(session)

    set_override(session, sale.id, Category.EXEMPT_MAIL_ORDER, "  Wpłata sprawdzona w raporcie Allegro  ", user_id=None, now=NOW)

    assert (sale.category, sale.override_category, sale.override_note) == (
        Category.TO_REVIEW.value, Category.EXEMPT_MAIL_ORDER.value, "Wpłata sprawdzona w raporcie Allegro"
    )
    assert effective_category(sale) is Category.EXEMPT_MAIL_ORDER
    assert sale.overridden_at is not None

    clear_override(session, sale.id, user_id=None)

    assert (sale.override_category, sale.override_note) == (None, None)
    assert effective_category(sale) is Category.TO_REVIEW


def test_an_override_survives_classifying_again_and_its_sales_refund_follows_it(session):
    sale = _to_review(session)
    set_override(session, sale.id, Category.EXEMPT_MAIL_ORDER, "Sprawdzone", user_id=None)
    _op(session, "REFUND_CHARGE", "REFUND", payment_id="pay-o-1", amount="-10.00", occurred_at=datetime(2026, 9, 25, tzinfo=UTC))

    _write(session)

    session.refresh(sale)
    (refund,) = _rows(session, LedgerKind.CORRECTION)
    assert (sale.category, sale.override_category) == (Category.TO_REVIEW.value, Category.EXEMPT_MAIL_ORDER.value)
    assert refund.category == Category.EXEMPT_MAIL_ORDER.value


@pytest.mark.parametrize("note", ["", "   ", None])
def test_an_override_needs_a_written_reason(session, note):
    sale = _to_review(session)

    with pytest.raises(OverrideRefused):
        set_override(session, sale.id, Category.EXEMPT_MAIL_ORDER, note, user_id=None)


def test_a_companys_sale_cannot_be_overridden(session):
    _order(session, invoice_is_company=True)
    _write(session)
    (sale,) = _rows(session)

    with pytest.raises(OverrideRefused):
        set_override(session, sale.id, Category.EXEMPT_MAIL_ORDER, "Mimo wszystko", user_id=None)


def test_an_override_given_before_the_sale_turned_out_a_companys_no_longer_counts():
    assert decide(Category.BUSINESS, Category.EXEMPT_MAIL_ORDER.value) is Category.BUSINESS
    assert decide(Category.TO_REVIEW, Category.EXEMPT_MAIL_ORDER.value) is Category.EXEMPT_MAIL_ORDER


def test_a_locked_row_cannot_be_overridden(session):
    sale = _to_review(session)
    NonInvoicedRepository(session).lock([sale.id], NOW)

    with pytest.raises(OverrideRefused):
        set_override(session, sale.id, Category.EXEMPT_MAIL_ORDER, "Za późno", user_id=None)
    with pytest.raises(OverrideRefused):
        clear_override(session, sale.id, user_id=None)


def test_a_correction_cannot_be_overridden(session):
    _order(session)
    _op(session, "REFUND_CHARGE", "REFUND", payment_id="pay-o-1", amount="-5.00", occurred_at=datetime(2026, 9, 20, tzinfo=UTC))
    _write(session)
    (correction,) = _rows(session, LedgerKind.CORRECTION)

    with pytest.raises(OverrideRefused):
        set_override(session, correction.id, Category.EXEMPT_MAIL_ORDER, "Nie", user_id=None)


# --- the payout (4d) ---------------------------------------------------------------------------


def _operation(type_, at, operator="P24", payout_id=None):
    return PaymentOperation(type=type_, occurred_at=at, wallet_operator=operator, payout_id=payout_id)


def test_a_payment_goes_out_in_the_first_payout_of_its_wallet_after_it():
    payment = _operation("CONTRIBUTION", PAID_AT)
    payouts = [
        _operation("PAYOUT", PAID_AT - timedelta(hours=1), payout_id="before"),
        _operation("PAYOUT", PAID_AT + timedelta(days=3), payout_id="later"),
        _operation("PAYOUT", PAID_AT + timedelta(days=1), operator="PAYU", payout_id="other-wallet"),
        _operation("PAYOUT", PAID_AT + timedelta(days=2), payout_id="first"),
    ]

    link = link_payout(payment, payouts)

    assert (link.payout_id, link.payout_at, link.link) == ("first", PAID_AT + timedelta(days=2), PAYOUT_FIRST_AFTER)


def test_a_cancelled_payout_is_passed_over_for_the_next():
    payment = _operation("CONTRIBUTION", PAID_AT)
    payouts = [
        _operation("PAYOUT", PAID_AT + timedelta(days=1), payout_id="po-1"),
        _operation("PAYOUT_CANCEL", PAID_AT + timedelta(days=1, hours=2), payout_id="po-1"),
        _operation("PAYOUT", PAID_AT + timedelta(days=2), payout_id="po-2"),
    ]

    assert link_payout(payment, payouts).payout_id == "po-2"


def test_no_payout_yet_is_no_link():
    assert link_payout(_operation("CONTRIBUTION", PAID_AT), [_operation("PAYOUT", PAID_AT - timedelta(days=1), payout_id="x")]) is None
    assert link_payout(_operation("CONTRIBUTION", PAID_AT, operator=None), []) is None


def test_the_sale_keeps_the_payout_its_money_went_out_in_once_it_happens(session):
    _order(session)
    _op(session, payment_id="pay-o-1")
    _write(session)
    assert _rows(session)[0].payout_id is None

    _op(session, "PAYOUT", "OUTCOME", amount="-500.00", occurred_at=PAID_AT + timedelta(days=1), payout_id="po-1")
    _op(session, "PAYOUT_CANCEL", "OUTCOME", amount="500.00", occurred_at=PAID_AT + timedelta(days=1, hours=1), payout_id="po-1")
    _op(session, "PAYOUT", "OUTCOME", amount="-500.00", occurred_at=PAID_AT + timedelta(days=2), payout_id="po-2")
    _write(session)

    (sale,) = _rows(session)
    assert (sale.payout_id, sale.payout_link) == ("po-2", PAYOUT_FIRST_AFTER)
    assert _utc(sale.payout_at) == PAID_AT + timedelta(days=2)


# --- excluded goods (§ 4) ----------------------------------------------------------------------


def test_an_offer_flagged_as_excluded_goods_takes_the_sale_out_of_the_exemption(session):
    _order(session)
    _op(session, payment_id="pay-o-1")
    repo = NonInvoicedRepository(session)
    repo.set_excluded_from_exemption(OrderSource.ALLEGRO, "offer-1", True)
    repo.set_excluded_from_exemption(OrderSource.ERLI, "offer-2", True)

    _write(session)

    assert repo.excluded_offer_ids(OrderSource.ALLEGRO) == frozenset({"offer-1"})
    (sale,) = _rows(session)
    assert (sale.category, sale.reason) == (Category.NEEDS_REGISTER.value, Reason.EXCLUDED_GOODS.value)

    repo.set_excluded_from_exemption(OrderSource.ALLEGRO, "offer-1", False)
    _write(session)

    session.refresh(sale)
    assert repo.excluded_offer_ids(OrderSource.ALLEGRO) == frozenset()
    assert sale.category == Category.EXEMPT_MAIL_ORDER.value


# --- locking -----------------------------------------------------------------------------------


def test_locking_keeps_a_rows_first_lock(session):
    _order(session)
    _order(session, "o-2")
    _write(session)
    first, second = _rows(session)
    repo = NonInvoicedRepository(session)

    assert repo.lock([first.id], NOW) == 1
    assert repo.lock([first.id, second.id], NOW + timedelta(days=1)) == 1

    session.refresh(first)
    assert _utc(first.locked_at) == NOW


# --- personal data -----------------------------------------------------------------------------


def _row(session, entry_at, external_id="old"):
    entry = LedgerEntry(
        kind=LedgerKind.SALE,
        event_key=f"ORDER:{external_id}",
        entry_at=entry_at,
        entry_date=business_date(entry_at),
        source=OrderSource.ALLEGRO,
        order_external_id=external_id,
        order_number=1,
        amount=Decimal("50.00"),
        currency="PLN",
        buyer_first_name="Anna",
        buyer_last_name="Nowak",
        buyer_street="Długa 1",
        buyer_postal_code="30-001",
        buyer_city="Kraków",
        buyer_country_code="PL",
        category="TO_REVIEW",
        reason="NO_CONTRIBUTION",
        ruleset="poz41-2024/1",
        override_category="EXEMPT_MAIL_ORDER",
        override_note="Anna Nowak potwierdziła wpłatę",
    )
    session.add(entry)
    session.commit()
    return entry


def test_retention_erases_the_buyer_copy_once_the_tax_period_is_over(session):
    now = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
    # paid in 2020: its tax was due in 2021, kept through 2026
    old = _row(session, datetime(2020, 12, 31, 21, 0, tzinfo=UTC), "old")
    # paid on 1 January 2021, Polish time: kept another year
    kept = _row(session, datetime(2020, 12, 31, 23, 30, tzinfo=UTC), "kept")

    result = apply_retention(session, now)
    again = apply_retention(session, now)

    session.refresh(old)
    session.refresh(kept)
    assert (result.ledger_entries, again.ledger_entries) == (1, 0)
    assert (old.buyer_first_name, old.buyer_last_name, old.buyer_street, old.buyer_postal_code, old.buyer_city) == (None,) * 5
    assert old.override_note is None and old.anonymized_at is not None
    assert (old.amount, old.buyer_country_code, old.category, old.override_category) == (
        Decimal("50.00"), "PL", "TO_REVIEW", "EXEMPT_MAIL_ORDER"
    )
    assert kept.buyer_last_name == "Nowak" and kept.anonymized_at is None


def test_a_buyers_own_erasure_request_keeps_the_records_copy_and_the_order_is_not_classified_again(session):
    order = _order(session)
    _op(session, payment_id="pay-o-1")
    _write(session)
    person = find_person(session, login="jan_k")

    exported = export_person(session, person)
    result = anonymize_person(session, person, NOW)
    _write(session)

    (sale,) = _rows(session)
    session.refresh(order)
    assert [row["event_key"] for row in exported["orders"][0]["non_invoiced_record"]] == ["ORDER:o-1"]
    assert order.anonymized_at is not None and order.customer_last_name is None
    assert result.records_kept == 1
    assert (sale.buyer_first_name, sale.buyer_last_name, sale.buyer_city) == ("Jan", "Kowalski", "Gdańsk")
    # classified again, the erased order would lack its buyer and fall to review
    assert sale.category == Category.EXEMPT_MAIL_ORDER.value


# --- the import --------------------------------------------------------------------------------


class _Adapter:
    source = OrderSource.ALLEGRO

    def iter_order_pages(self, **filters):
        return []


def _service(session):
    session.add(IntegrationCredential(provider="ALLEGRO", refresh_token="t", seed_fingerprint="f"))
    session.commit()
    return OrderImportService(
        OrderRepository(session), _Adapter(), credentials=IntegrationCredentialRepository(session), initial_days=7
    )


def test_every_import_writes_the_ledger_for_the_orders_paid_since_the_previous_month(session):
    _order(session, paid_at=datetime.now(UTC) - timedelta(hours=1))

    _service(session).sync_orders()

    assert [row.event_key for row in _rows(session)] == ["ORDER:o-1"]


def test_a_failing_ledger_does_not_fail_the_import(session, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("the ledger broke")

    monkeypatch.setattr(order_import_service, "write_ledger", broken)
    _order(session, paid_at=datetime.now(UTC) - timedelta(hours=1))

    result = _service(session).sync_orders()

    assert result.total == 0
    assert "non-invoiced sales ledger failed" in caplog.text
    assert _rows(session) == []
    # the session is still usable for what comes after
    assert session.query(Order).count() == 1
