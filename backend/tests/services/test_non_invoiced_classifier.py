"""The classifier of the non-invoiced sales record (docs/NON_INVOICED_SALES.md, section 4a): one
test for each category and reason, each starting from a sale that is exempt under poz. 41 and
changing the one thing the rule looks at."""

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

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
from app.services.non_invoiced.classifier import (
    REASON_TEXT,
    RULESET,
    Category,
    ExtraPaymentFacts,
    Reason,
    SaleFacts,
    classify,
    facts_from_order,
)
from app.services.non_invoiced.run import classify_paid_between, counts


def _facts(**changes) -> SaleFacts:
    """A private buyer's courier order, paid in full through Przelewy24, its payment found."""
    facts = SaleFacts(
        source=OrderSource.ALLEGRO,
        status=OrderStatus.SHIPPED,
        cancelled_on_marketplace=False,
        total_amount=Decimal("167.00"),
        payment_type=PaymentType.ONLINE,
        payment_provider="P24",
        paid_amount=Decimal("167.00"),
        paid=True,
        payment_id="p-1",
        invoice_required=False,
        invoice_is_company=None,
        delivery_method="Allegro Paczkomaty InPost",
        delivery_country_code="PL",
        buyer_first_name="Jan",
        buyer_last_name="Kowalski",
        buyer_has_address=True,
        contribution_found=True,
    )
    return dataclasses.replace(facts, **changes)


def _decided(**changes):
    result = classify(_facts(**changes))
    return result.category, result.reason


def test_a_private_courier_order_paid_through_an_operator_is_exempt_under_poz_41():
    result = classify(_facts())

    assert (result.category, result.reason, result.ruleset) == (Category.EXEMPT_MAIL_ORDER, Reason.E41, RULESET)
    assert result.in_report is True


@pytest.mark.parametrize("provider", ["PAYU", "P24", "AF", "af", "ERLI"])
def test_every_payment_operator_counts(provider):
    assert _decided(payment_provider=provider) == (Category.EXEMPT_MAIL_ORDER, Reason.E41)


def test_a_bank_transfer_through_an_operator_counts_too():
    assert _decided(payment_type=PaymentType.BANK_TRANSFER) == (Category.EXEMPT_MAIL_ORDER, Reason.E41)


def test_a_surcharge_paid_and_found_keeps_it_exempt():
    surcharge = ExtraPaymentFacts(OrderPaymentKind.SURCHARGE, "s-1", Decimal("10.00"))

    decided = _decided(extra_payments=(surcharge,), total_amount=Decimal("177.00"), surcharge_ids_found=frozenset({"s-1"}))

    assert decided == (Category.EXEMPT_MAIL_ORDER, Reason.E41)


# --- 1. not a sale ---------------------------------------------------------------------------


def test_an_order_never_paid_is_not_a_sale():
    assert _decided(paid=False, paid_amount=None) == (Category.NOT_A_SALE, Reason.NOT_PAID)


def test_an_order_cancelled_before_payment_is_not_a_sale_either():
    assert _decided(paid=False, status=OrderStatus.CANCELLED) == (Category.NOT_A_SALE, Reason.NOT_PAID)


# --- 2. a company ----------------------------------------------------------------------------


def test_a_company_is_outside_the_obligation():
    assert _decided(invoice_is_company=True, invoice_required=True) == (Category.BUSINESS, Reason.COMPANY)


def test_where_the_marketplace_does_not_say_a_tax_id_makes_it_a_company():
    assert _decided(invoice_is_company=None, invoice_tax_id="1234563218") == (Category.BUSINESS, Reason.COMPANY)


def test_the_marketplace_saying_private_outweighs_a_stray_tax_id():
    assert _decided(invoice_is_company=False, invoice_tax_id="1234563218")[0] is Category.EXEMPT_MAIL_ORDER


def test_a_company_paying_cash_is_still_a_company():
    assert _decided(invoice_is_company=True, payment_type=PaymentType.CASH_ON_DELIVERY)[0] is Category.BUSINESS


# --- 3. needs the register -------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"payment_type": PaymentType.CASH_ON_DELIVERY},
        {"payment_provider": "OFFLINE"},
        {"extra_payments": (ExtraPaymentFacts(OrderPaymentKind.CASH_ON_DELIVERY, "cod-1", Decimal("5.00")),)},
    ],
)
def test_any_part_paid_in_cash_needs_the_register(changes):
    assert _decided(**changes) == (Category.NEEDS_REGISTER, Reason.CASH_PART)


def test_a_cash_on_delivery_entry_with_nothing_collected_is_no_cash():
    nothing = ExtraPaymentFacts(OrderPaymentKind.CASH_ON_DELIVERY, "cod-1", Decimal("0.00"))

    assert _decided(extra_payments=(nothing,))[0] is Category.EXEMPT_MAIL_ORDER


@pytest.mark.parametrize("method", ["Odbiór osobisty", "Odbiór osobisty po przedpłacie", "ODBIÓR OSOBISTY"])
def test_personal_collection_is_not_mail_order(method):
    assert _decided(delivery_method=method) == (Category.NEEDS_REGISTER, Reason.PERSONAL_COLLECTION)


def test_excluded_goods_need_the_register():
    assert _decided(has_excluded_goods=True) == (Category.NEEDS_REGISTER, Reason.EXCLUDED_GOODS)


def test_cash_is_named_before_personal_collection_and_excluded_goods():
    decided = _decided(payment_type=PaymentType.CASH_ON_DELIVERY, delivery_method="Odbiór osobisty", has_excluded_goods=True)

    assert decided == (Category.NEEDS_REGISTER, Reason.CASH_PART)


# --- 4. a private buyer's invoice --------------------------------------------------------------


def test_a_private_buyer_asking_for_an_invoice_is_documented_by_it():
    assert _decided(invoice_required=True, invoice_is_company=False) == (Category.PRIVATE_INVOICED, Reason.PRIVATE_INVOICE)


def test_an_invoice_does_not_hide_a_cash_payment():
    assert _decided(invoice_required=True, payment_type=PaymentType.CASH_ON_DELIVERY)[0] is Category.NEEDS_REGISTER


# --- 5. to review ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"status": OrderStatus.CANCELLED}, Reason.CANCELLED_AFTER_PAYMENT),
        ({"cancelled_on_marketplace": True}, Reason.CANCELLED_AFTER_PAYMENT),
        ({"delivery_country_code": "DE"}, Reason.FOREIGN_DELIVERY),
        ({"delivery_method": None}, Reason.NO_DELIVERY_METHOD),
        ({"payment_type": PaymentType.DEFERRED}, Reason.NOT_VIA_OPERATOR),
        ({"payment_type": None}, Reason.NOT_VIA_OPERATOR),
        ({"payment_provider": None}, Reason.NOT_VIA_OPERATOR),
        ({"payment_provider": "EPT"}, Reason.NOT_VIA_OPERATOR),
        ({"paid_amount": Decimal("150.00")}, Reason.UNDERPAID),
        ({"buyer_first_name": None}, Reason.MISSING_BUYER_DATA),
        ({"buyer_last_name": ""}, Reason.MISSING_BUYER_DATA),
        ({"buyer_has_address": False}, Reason.MISSING_BUYER_DATA),
        ({"payment_id": None}, Reason.NO_PAYMENT_ID),
        ({"contribution_found": False}, Reason.NO_CONTRIBUTION),
        (
            {"extra_payments": (ExtraPaymentFacts(OrderPaymentKind.SURCHARGE, "s-1", Decimal("10.00")),)},
            Reason.SURCHARGE_UNTRACED,
        ),
    ],
)
def test_what_the_rules_cannot_decide_is_left_to_a_person(changes, reason):
    assert _decided(**changes) == (Category.TO_REVIEW, reason)


def test_an_erli_sale_is_judged_by_the_same_rules():
    # Erli collects the money through PayU and pays it out to the seller's bank account itself
    erli = {"source": OrderSource.ERLI, "payment_provider": "ERLI"}

    assert _decided(**erli) == (Category.EXEMPT_MAIL_ORDER, Reason.E41)
    assert _decided(**erli, contribution_found=False) == (Category.TO_REVIEW, Reason.NO_CONTRIBUTION)
    assert _decided(**erli, payment_type=PaymentType.CASH_ON_DELIVERY) == (Category.NEEDS_REGISTER, Reason.CASH_PART)


def test_a_marketplace_the_rules_do_not_know_is_left_to_a_person():
    class Other:
        value = "OTHER"

    assert _decided(source=Other()) == (Category.TO_REVIEW, Reason.SOURCE_NOT_SUPPORTED)


def test_a_delivery_with_no_country_recorded_is_not_taken_for_a_foreign_one():
    assert _decided(delivery_country_code=None)[0] is Category.EXEMPT_MAIL_ORDER


def test_every_reason_has_its_text():
    assert set(REASON_TEXT) == set(Reason)


# --- the facts of a stored order ---------------------------------------------------------------


PAID_AT = datetime(2026, 9, 14, 10, 1, tzinfo=UTC)


def _order(session, external_id="o-1", **changes) -> Order:
    order = Order(
        source=OrderSource.ALLEGRO,
        external_id=external_id,
        status=OrderStatus.SHIPPED,
        customer_email="buyer@example.com",
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


def _contribution(session, payment_id, occurred_at=PAID_AT, **changes) -> PaymentOperation:
    operation = PaymentOperation(
        source=OrderSource.ALLEGRO,
        fingerprint=f"fp-{payment_id}-{changes.get('type', 'CONTRIBUTION')}",
        type="CONTRIBUTION",
        group="INCOME",
        occurred_at=occurred_at,
        amount=Decimal("167.00"),
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


def test_a_stored_order_with_its_payment_found_is_exempt(session):
    order = _order(session)
    operation = _contribution(session, "pay-o-1")

    facts = facts_from_order(order, [operation])

    assert (facts.paid, facts.buyer_has_address, facts.contribution_found, facts.delivery_country_code) == (True, True, True, "PL")
    assert classify(facts).category is Category.EXEMPT_MAIL_ORDER


def test_an_operation_for_another_payment_is_not_this_ones(session):
    order = _order(session)

    assert facts_from_order(order, [_contribution(session, "someone-else")]).contribution_found is False


def test_the_recipients_address_is_not_the_buyers(session):
    order = _order(session)
    order.addresses = [a for a in order.addresses if a.type is not AddressType.BUYER]
    session.commit()

    assert classify(facts_from_order(order, [_contribution(session, "pay-o-1")])).reason is Reason.MISSING_BUYER_DATA


def test_an_erli_buyer_is_named_by_the_delivery_address(session):
    # Erli names no buyer apart from the delivery address (INTEGRATIONS.md, "Erli")
    order = _order(session, source=OrderSource.ERLI, payment_provider="ERLI")
    order.addresses = [a for a in order.addresses if a.type is not AddressType.BUYER]
    session.commit()

    facts = facts_from_order(order, [_contribution(session, "pay-o-1", source=OrderSource.ERLI, wallet_operator="PAYU")])

    assert facts.buyer_has_address is True
    assert classify(facts).category is Category.EXEMPT_MAIL_ORDER


def test_an_offer_flagged_as_excluded_goods_marks_the_order(session):
    order = _order(session)

    facts = facts_from_order(order, [], excluded_offer_ids=frozenset({"offer-1"}))

    assert facts.has_excluded_goods is True


def test_a_surcharge_is_found_by_its_own_id_or_its_payments(session):
    order = _order(session, total_amount=Decimal("177.00"))
    order.extra_payments = [OrderPayment(position=0, kind=OrderPaymentKind.SURCHARGE, external_id="s-1", paid_amount=Decimal("10.00"))]
    session.commit()
    surcharge = _contribution(session, "s-1", type="SURCHARGE", amount=Decimal("10.00"))

    facts = facts_from_order(order, [_contribution(session, "pay-o-1"), surcharge])

    assert "s-1" in facts.surcharge_ids_found
    assert classify(facts).category is Category.EXEMPT_MAIL_ORDER


def test_the_orders_paid_in_a_period_are_classified_with_their_own_operations(session):
    _order(session, "in-report")
    _contribution(session, "pay-in-report")
    _order(session, "company", invoice_is_company=True)
    _order(session, "untraced")
    _order(session, "august", paid_at=datetime(2026, 8, 31, 21, 0, tzinfo=UTC))
    _order(session, "unpaid", paid_at=None, paid_amount=None)

    classified = classify_paid_between(session, datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC))

    decided = {c.order.external_id: (c.classification.category, c.classification.reason) for c in classified}
    assert decided == {
        "in-report": (Category.EXEMPT_MAIL_ORDER, Reason.E41),
        "company": (Category.BUSINESS, Reason.COMPANY),
        "untraced": (Category.TO_REVIEW, Reason.NO_CONTRIBUTION),
    }
    by_category, by_reason = counts(classified)
    assert by_category[Category.EXEMPT_MAIL_ORDER] == 1
    assert by_reason[(Category.TO_REVIEW, Reason.NO_CONTRIBUTION)] == 1
