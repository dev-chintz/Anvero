"""Reports of the non-invoiced sales record (docs/NON_INVOICED_SALES.md, 4c, 4e, 4f; stage 4): what
a range lists, its totals and checks, the VAT limit, handing it over and what a handed-over report
stays, and the exports."""

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.models.non_invoiced import LedgerKind
from app.models.order import OrderStatus, PaymentType
from app.services.non_invoiced.classifier import Category
from app.services.non_invoiced.export import resolve_columns, to_csv, to_pdf, to_xlsx
from app.services.non_invoiced.ledger import set_override
from app.services.non_invoiced.report import (
    ReportRefused,
    build_report,
    hand_over,
    limit_status,
)
from tests.services.test_non_invoiced_ledger import (
    NOW,
    PAID_AT,
    _op,
    _order,
    _rows,
    _write,
)

SEPTEMBER = (date(2026, 9, 1), date(2026, 9, 30))
OCTOBER = (date(2026, 10, 1), date(2026, 10, 31))


def _exempt(session, external_id="o-1", paid_at=PAID_AT, **changes):
    order = _order(session, external_id, paid_at=paid_at, **changes)
    _op(session, payment_id=order.payment_id, occurred_at=paid_at, amount=str(order.paid_amount))
    return order


def _september(session):
    return build_report(session, *SEPTEMBER)


def test_a_range_lists_its_exempt_sales_then_their_refunds_and_totals_them(session):
    _exempt(session, "o-1")
    second = _exempt(session, "o-2", paid_at=PAID_AT + timedelta(days=2), paid_amount=Decimal("50.00"), total_amount=Decimal("50.00"))
    _op(session, "REFUND_CHARGE", "REFUND", payment_id=second.payment_id, amount="-20.00", occurred_at=PAID_AT + timedelta(days=5))
    _write(session)

    report = _september(session)

    assert [(r.entry.kind, r.entry.amount) for r in report.listed] == [
        (LedgerKind.SALE, Decimal("167.00")),
        (LedgerKind.SALE, Decimal("50.00")),
        (LedgerKind.CORRECTION, Decimal("-20.00")),
    ]
    assert report.total == Decimal("197.00")
    exempt = next(t for t in report.totals if t.category is Category.EXEMPT_MAIL_ORDER)
    assert (exempt.sales, exempt.sales_amount, exempt.corrections_amount, exempt.total) == (
        2,
        Decimal("217.00"),
        Decimal("-20.00"),
        Decimal("197.00"),
    )
    assert report.checks.blocking is False and report.checks.warnings is False


def test_a_company_is_counted_apart_and_not_listed(session):
    _exempt(session, "o-1")
    _exempt(session, "o-2", invoice_is_company=True)
    _write(session)

    report = _september(session)

    assert len(report.listed) == 1
    business = next(t for t in report.totals if t.category is Category.BUSINESS)
    assert business.sales == 1


def test_a_sale_to_decide_blocks_handing_over_until_decided(session):
    _exempt(session, "o-1", status=OrderStatus.CANCELLED)
    _write(session)
    report = _september(session)
    assert report.checks.to_review == 1

    with pytest.raises(ReportRefused) as refused:
        hand_over(session, *SEPTEMBER, user_id=None, now=NOW)
    assert refused.value.code == "TO_REVIEW"

    (sale,) = _rows(session, LedgerKind.SALE)
    set_override(session, sale.id, Category.NOT_A_SALE, "Anulowane i zwrócone w całości", user_id=None, now=NOW)
    assert _september(session).checks.to_review == 0


def test_a_sale_needing_the_register_is_a_warning_to_acknowledge(session):
    _exempt(session, "o-1", payment_type=PaymentType.CASH_ON_DELIVERY)
    _write(session)
    assert _september(session).checks.needs_register == 1

    with pytest.raises(ReportRefused) as refused:
        hand_over(session, *SEPTEMBER, user_id=None, now=NOW)
    assert refused.value.code == "NOT_ACKNOWLEDGED"

    handed = hand_over(session, *SEPTEMBER, user_id=None, acknowledged=True, now=NOW)
    assert handed.row_count == 0


def test_a_payment_no_row_accounts_for_is_a_warning(session):
    _exempt(session, "o-1")
    _op(session, payment_id="someone-elses", amount="30.00")
    _write(session)

    checks = _september(session).checks

    assert (checks.unmatched_payments, checks.unmatched_amount, checks.warnings) == (1, Decimal("30.00"), True)


def test_a_range_not_ended_cannot_be_handed_over(session):
    _write(session)

    with pytest.raises(ReportRefused) as refused:
        hand_over(session, *OCTOBER, user_id=None, now=NOW)
    assert refused.value.code == "NOT_ENDED"


def test_handing_over_locks_what_it_lists_and_keeps_it_the_same(session):
    _exempt(session, "o-1")
    _exempt(session, "o-2", paid_at=PAID_AT + timedelta(days=1))
    _write(session)

    handed = hand_over(session, *SEPTEMBER, user_id=None, now=NOW)

    assert (handed.row_count, handed.total) == (2, Decimal("334.00"))
    assert all(row.locked_at is not None for row in _rows(session, LedgerKind.SALE))
    again = _september(session)
    assert again.handed_over is not None
    assert [r.entry.id for r in again.listed] == [row.entry_id for row in handed.rows]
    with pytest.raises(ReportRefused) as refused:
        hand_over(session, *SEPTEMBER, user_id=None, now=NOW)
    assert refused.value.code == "ALREADY_HANDED_OVER"


def test_a_refund_found_after_its_month_went_is_carried_by_the_next_report(session):
    order = _exempt(session, "o-1")
    _write(session)
    hand_over(session, *SEPTEMBER, user_id=None, now=NOW)

    # the refund was made on 20 September but read only in October
    _op(session, "REFUND_CHARGE", "REFUND", payment_id=order.payment_id, amount="-40.00", occurred_at=PAID_AT + timedelta(days=6))
    _write(session, now=NOW + timedelta(days=2))

    september = _september(session)
    october = build_report(session, *OCTOBER)
    assert september.total == Decimal("167.00")
    assert [(r.entry.amount, r.late) for r in october.listed] == [(Decimal("-40.00"), True)]


def test_an_override_moves_its_refunds_with_it_at_once(session):
    order = _exempt(session, "o-1")
    _op(session, "REFUND_CHARGE", "REFUND", payment_id=order.payment_id, amount="-40.00", occurred_at=PAID_AT + timedelta(days=1))
    _write(session)
    (sale,) = _rows(session, LedgerKind.SALE)

    set_override(session, sale.id, Category.PRIVATE_INVOICED, "Faktura wystawiona poza Allegro", user_id=None, now=NOW)

    assert _september(session).listed == []


def test_the_vat_limit_counts_the_years_sales(session):
    _exempt(session, "o-1")
    _exempt(session, "o-2", invoice_is_company=True)
    _write(session)

    status = limit_status(session, 2026)

    assert status.total == Decimal("334.00")
    assert status.counted_from == date(2026, 9, 14)
    assert (status.warning, status.exceeded) == (False, False)


# --- exports -------------------------------------------------------------------------------------


def _report_of_two(session):
    _exempt(session, "o-1")
    _exempt(session, "o-2", paid_at=PAID_AT + timedelta(days=1), paid_amount=Decimal("1234.50"), total_amount=Decimal("1234.50"))
    _write(session)
    return _september(session)


def test_the_csv_holds_the_accountants_columns_and_the_total(session):
    report = _report_of_two(session)

    data = to_csv(report, resolve_columns(None))

    assert data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    assert rows == [
        ["Lp.", "Data", "Imię i nazwisko", "Kwota"],
        ["1", "14.09.2026", "Jan Kowalski", "167,00"],
        ["2", "15.09.2026", "Jan Kowalski", "1234,50"],
        ["", "Razem", "", "1401,50"],
    ]


def test_chosen_columns_come_in_the_order_chosen_after_lp():
    assert [c.key for c in resolve_columns(["amount", "order_number", "lp"])] == ["lp", "amount", "order_number"]
    with pytest.raises(KeyError):
        resolve_columns(["nope"])


def test_the_excel_file_has_numbers_and_dates(session):
    report = _report_of_two(session)

    book = load_workbook(io.BytesIO(to_xlsx(report, resolve_columns(None))))
    sheet = book.active

    assert [c.value for c in sheet[4]] == ["Lp.", "Data", "Imię i nazwisko", "Kwota"]
    assert sheet["D5"].value == Decimal("167.00") or sheet["D5"].value == 167
    assert isinstance(sheet["B5"].value, datetime)
    assert sheet["D7"].value in (Decimal("1401.50"), 1401.5)


def test_the_pdf_is_a_pdf_with_polish_letters_embedded(session):
    report = _report_of_two(session)

    data = to_pdf(report, resolve_columns(["buyer_address", "order_number"]), ["Pracownia Ceramiki Żółw", "Lipowa 3, 80-001 Gdańsk"])

    assert data.startswith(b"%PDF")
    assert b"DejaVu" in data
