"""The non-invoiced sales report's classification: the rules approved from the ported tool
(`BUSINESS_DECISIONS.md` there, and the owner's own approval of `PAY-001` on 2026-09-27 after
seeing the ported tool's own code already relied on it), nothing guessed beyond them."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models.order import OrderSource, OrderStatus
from app.schemas.sales_report import SalesReportCategory
from app.services.sales_report import OrderFacts, classify

WHEN = datetime(2026, 6, 15, tzinfo=UTC)


def _facts(**overrides) -> OrderFacts:
    fields = {
        "source": OrderSource.ALLEGRO,
        "order_external_id": "ext-1",
        "ordered_at": WHEN,
        "amount": Decimal("100.00"),
        "currency": "PLN",
        "buyer_login": "buyer1",
        "status": OrderStatus.SHIPPED,
        "marketplace_status_label": "SENT",
        "paid_amount": Decimal("100.00"),
        "invoice_first_name": None,
        "invoice_last_name": None,
        "invoice_company_name": None,
        "invoice_street": None,
        "invoice_postal_code": None,
        "invoice_city": None,
        "invoice_country_code": None,
        "invoice_tax_id": None,
    }
    fields.update(overrides)
    return OrderFacts(**fields)


COMPANY_INVOICE = {
    "invoice_company_name": "Firma sp. z o.o.",
    "invoice_street": "Kwiatowa 1",
    "invoice_postal_code": "00-001",
    "invoice_city": "Warszawa",
    "invoice_country_code": "PL",
    "invoice_tax_id": "1234567890",
}


def test_complete_company_invoice_excludes_as_company():
    result = classify(_facts(**COMPANY_INVOICE))
    assert result.category is SalesReportCategory.COMPANY
    assert result.included is False
    assert result.rule_id == "INV-001"
    assert result.overridable is False


def test_incomplete_company_invoice_is_not_excluded_by_itself():
    # missing the tax id: not a complete company invoice, so INV-001 does not fire; it also is not
    # a named personal invoice (a company name is present), so PAY-001 does not fire either
    result = classify(_facts(invoice_company_name="Firma sp. z o.o.", invoice_street="Kwiatowa 1"))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_cancelled_and_unpaid_excludes_as_out_of_scope():
    result = classify(_facts(marketplace_status_label="CANCELLED", status=OrderStatus.CANCELLED, paid_amount=Decimal("0.00")))
    assert result.category is SalesReportCategory.OUT_OF_SCOPE
    assert result.rule_id == "SEL-001"
    assert result.overridable is True


def test_suspended_and_unpaid_excludes_as_out_of_scope():
    result = classify(_facts(marketplace_status_label="SUSPENDED", status=OrderStatus.CANCELLED, paid_amount=None))
    assert result.category is SalesReportCategory.OUT_OF_SCOPE


def test_cancelled_but_paid_in_full_is_not_excluded_by_that_rule():
    # a completed sale before cancellation is not "out of scope" under SEL-001; PAY-001 does not
    # reach it either, since it was never shipped, so it stays MANUAL_REVIEW
    result = classify(_facts(marketplace_status_label="CANCELLED", status=OrderStatus.CANCELLED, paid_amount=Decimal("100.00")))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_company_invoice_takes_priority_over_cancellation():
    # matches the ported tool's own rule order: INV-001 is checked before the cancellation rule
    result = classify(_facts(marketplace_status_label="CANCELLED", status=OrderStatus.CANCELLED, paid_amount=Decimal("0.00"), **COMPANY_INVOICE))
    assert result.category is SalesReportCategory.COMPANY


def test_paid_shipped_order_without_invoice_qualifies_as_retail():
    result = classify(_facts())
    assert result.category is SalesReportCategory.RETAIL
    assert result.included is True
    assert result.rule_id == "PAY-001"
    assert result.overridable is True


def test_paid_shipped_order_with_a_named_personal_invoice_qualifies_as_retail():
    result = classify(_facts(invoice_first_name="Jan", invoice_last_name="Kowalski", invoice_street="Polna 2"))
    assert result.category is SalesReportCategory.RETAIL


def test_not_yet_shipped_does_not_qualify_as_retail():
    result = classify(_facts(status=OrderStatus.CONFIRMED))
    assert result.category is SalesReportCategory.MANUAL_REVIEW
    assert result.rule_id == "REV-001"


def test_not_fully_paid_does_not_qualify_as_retail():
    result = classify(_facts(paid_amount=Decimal("50.00")))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_unpaid_amount_unknown_does_not_qualify_as_retail():
    result = classify(_facts(paid_amount=None))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_foreign_currency_does_not_qualify_as_retail():
    result = classify(_facts(currency="EUR"))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_a_name_alone_with_a_company_name_is_not_a_personal_invoice():
    # a company name present, even alongside a personal name, is not BD-001's "named personal
    # invoice", so PAY-001 does not fire; nothing approved says what it is instead
    result = classify(_facts(invoice_first_name="Jan", invoice_company_name="Firma sp. z o.o."))
    assert result.category is SalesReportCategory.MANUAL_REVIEW
