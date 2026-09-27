"""The non-invoiced sales report's classification: only the two APPROVED rules the ported tool
registered (`BUSINESS_DECISIONS.md` in the tool it came from), nothing guessed beyond them."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models.order import OrderSource
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
        "marketplace_status_label": "SENT",
        "paid_amount": Decimal("100.00"),
        "invoice_company_name": None,
        "invoice_street": None,
        "invoice_postal_code": None,
        "invoice_city": None,
        "invoice_country_code": None,
        "invoice_tax_id": None,
    }
    fields.update(overrides)
    return OrderFacts(**fields)


def test_complete_company_invoice_excludes_as_company():
    result = classify(
        _facts(
            invoice_company_name="Firma sp. z o.o.",
            invoice_street="Kwiatowa 1",
            invoice_postal_code="00-001",
            invoice_city="Warszawa",
            invoice_country_code="PL",
            invoice_tax_id="1234567890",
        )
    )
    assert result.category is SalesReportCategory.COMPANY
    assert result.included is False
    assert result.rule_id == "INV-001"
    assert result.overridable is False


def test_incomplete_company_invoice_is_not_excluded_by_itself():
    # missing the tax id: not a complete company invoice, so INV-001 does not fire; nothing else
    # approved decides it either, so it falls to manual review rather than being guessed
    result = classify(_facts(invoice_company_name="Firma sp. z o.o.", invoice_street="Kwiatowa 1"))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_named_personal_invoice_does_not_exclude():
    # BD-001: a personal invoice is not a company invoice
    result = classify(_facts(invoice_company_name=None, invoice_tax_id=None))
    assert result.category is not SalesReportCategory.COMPANY


def test_cancelled_and_unpaid_excludes_as_out_of_scope():
    result = classify(_facts(marketplace_status_label="CANCELLED", paid_amount=Decimal("0.00")))
    assert result.category is SalesReportCategory.OUT_OF_SCOPE
    assert result.rule_id == "SEL-001"
    assert result.overridable is True


def test_suspended_and_unpaid_excludes_as_out_of_scope():
    result = classify(_facts(marketplace_status_label="SUSPENDED", paid_amount=None))
    assert result.category is SalesReportCategory.OUT_OF_SCOPE


def test_cancelled_but_paid_in_full_is_not_excluded_by_that_rule():
    # a completed sale before cancellation is not "out of scope" under BD-002; nothing approved
    # says what it is instead, so it stays MANUAL_REVIEW rather than being guessed as retail
    result = classify(_facts(marketplace_status_label="CANCELLED", paid_amount=Decimal("100.00")))
    assert result.category is SalesReportCategory.MANUAL_REVIEW


def test_company_invoice_takes_priority_over_cancellation():
    # matches the ported tool's own rule order: INV-001 is checked before the cancellation rule
    result = classify(
        _facts(
            marketplace_status_label="CANCELLED",
            paid_amount=Decimal("0.00"),
            invoice_company_name="Firma sp. z o.o.",
            invoice_street="Kwiatowa 1",
            invoice_postal_code="00-001",
            invoice_city="Warszawa",
            invoice_country_code="PL",
            invoice_tax_id="1234567890",
        )
    )
    assert result.category is SalesReportCategory.COMPANY


def test_sent_and_paid_order_without_invoice_is_manual_review_not_guessed_retail():
    # the ported tool's own code also auto-includes this case as RETAIL (qualifyV1), but that path
    # has no entry in its BUSINESS_DECISIONS.md register, so it is deliberately not ported
    result = classify(_facts())
    assert result.category is SalesReportCategory.MANUAL_REVIEW
    assert result.rule_id == "REV-001"
