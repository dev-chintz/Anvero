"""Reports of the non-invoiced sales record (docs/NON_INVOICED_SALES.md, sections 4c and 4f; stage 4
of the plan): what a date range holds, the checks before it is handed over to the accountant, the
VAT exemption limit, and handing it over.

A report reads the ledger (app/services/non_invoiced/ledger.py), never the orders:

- its **rows** are the ledger rows dated in the range, and the rows dated in a range already
  handed over that were written after it (a refund found late, a sale reclassified into the report
  after its month went to the accountant): those are carried by the next report instead of changing
  the one handed over;
- the rows it **lists** (the export) are those counting as EXEMPT_MAIL_ORDER and not locked: the
  sales first, then the corrections, each by date; for a range handed over, exactly the rows it
  listed then, in the same order;
- **handing it over** records those rows against it and locks them, so it stays the same file.

Nothing here writes except `hand_over`.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.non_invoiced import (
    HandedOverReport,
    HandedOverReportRow,
    LedgerEntry,
    LedgerKind,
)
from app.models.order import Order, PaymentOperation
from app.repositories.non_invoiced_repository import NonInvoicedRepository
from app.services.non_invoiced.classifier import CONTRIBUTION, RULESET, Category
from app.services.non_invoiced.ledger import business_date, decide, is_reclassification

ZERO = Decimal("0.00")

# the VAT exemption limit by turnover (art. 113 ust. 1 of the VAT act, since 2026-01-01), and the
# share of it from which the screen warns (4f); a warning, not a ruling: what counts toward it is
# the accountant's call
VAT_LIMIT = Decimal("240000.00")
LIMIT_WARNING_SHARE = Decimal("0.80")

CATEGORY_ORDER = [
    Category.EXEMPT_MAIL_ORDER,
    Category.TO_REVIEW,
    Category.NEEDS_REGISTER,
    Category.PRIVATE_INVOICED,
    Category.BUSINESS,
    Category.NOT_A_SALE,
]


class ReportRefused(ValueError):
    """Handing a report over that the rules do not allow; `code` says which rule."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ReportRow:
    entry: LedgerEntry
    # the category it counts in now: a sale's override or automatic result; a correction's, the
    # category of the sale it corrects while it follows it
    category: Category
    # dated in a range handed over, written after it: carried by this report
    late: bool = False

    @property
    def in_report(self) -> bool:
        return self.category is Category.EXEMPT_MAIL_ORDER


@dataclass
class CategoryTotal:
    category: Category
    sales: int = 0
    sales_amount: Decimal = ZERO
    corrections: int = 0
    corrections_amount: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.sales_amount + self.corrections_amount


@dataclass
class Checks:
    to_review: int = 0
    needs_register: int = 0
    # the buyers' payments the operators received in the range that no ledger row accounts for
    unmatched_payments: int = 0
    unmatched_amount: Decimal = ZERO
    # listed sales with no payment operation found for them
    untraced_sales: int = 0

    @property
    def blocking(self) -> bool:
        return self.to_review > 0

    @property
    def warnings(self) -> bool:
        return self.needs_register > 0 or self.unmatched_payments > 0 or self.untraced_sales > 0


@dataclass
class LimitStatus:
    year: int
    total: Decimal
    limit: Decimal = VAT_LIMIT
    # the first day the total counts from: the year's first paid order Anvero holds
    counted_from: date | None = None

    @property
    def share(self) -> Decimal:
        return (self.total / self.limit).quantize(Decimal("0.0001")) if self.limit else ZERO

    @property
    def warning(self) -> bool:
        return self.share >= LIMIT_WARNING_SHARE

    @property
    def exceeded(self) -> bool:
        return self.total > self.limit


@dataclass
class Report:
    date_from: date
    date_to: date
    rows: list[ReportRow]
    listed: list[ReportRow]
    totals: list[CategoryTotal]
    checks: Checks
    limit: LimitStatus
    # the report handed over for exactly this range, if there is one
    handed_over: HandedOverReport | None = None
    # reports handed over whose range overlaps this one without being it
    overlapping: list[HandedOverReport] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((row.entry.amount for row in self.listed), ZERO)

    @property
    def currency(self) -> str:
        return self.listed[0].entry.currency if self.listed else "PLN"


# --- the pure part ------------------------------------------------------------------------------


def listing_order(rows: list[ReportRow]) -> list[ReportRow]:
    """The rows a report lists, as it lists them: the sales, then the corrections, each by date."""
    return sorted(
        (row for row in rows if row.in_report and row.entry.locked_at is None),
        key=lambda row: (row.entry.kind is not LedgerKind.SALE, row.entry.entry_at, row.entry.order_number),
    )


def totals_by_category(rows: list[ReportRow]) -> list[CategoryTotal]:
    totals = {category: CategoryTotal(category) for category in CATEGORY_ORDER}
    for row in rows:
        total = totals[row.category]
        if row.entry.kind is LedgerKind.SALE:
            total.sales += 1
            total.sales_amount += row.entry.amount
        else:
            total.corrections += 1
            total.corrections_amount += row.entry.amount
    return [totals[category] for category in CATEGORY_ORDER]


# --- reading ------------------------------------------------------------------------------------


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """The range's first and last moment where the business is, in UTC: [start, end)."""
    zone = ZoneInfo(settings.business_timezone)
    start = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def _db_datetime(db: Session, value: datetime) -> datetime:
    # SQLite keeps naive UTC, and an aware bound would never compare equal
    if db.get_bind().dialect.name == "sqlite":
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def handed_over_reports(db: Session) -> list[HandedOverReport]:
    """Every report handed over, the latest range first."""
    return list(
        db.scalars(
            select(HandedOverReport)
            .options(selectinload(HandedOverReport.handed_over_by))
            .order_by(HandedOverReport.date_from.desc(), HandedOverReport.handed_over_at.desc())
        )
    )


def get_handed_over(db: Session, report_id: uuid.UUID) -> HandedOverReport | None:
    return db.get(HandedOverReport, report_id)


def _effective(entries: list[LedgerEntry], sales: dict[uuid.UUID, LedgerEntry]) -> list[ReportRow]:
    rows = []
    for entry in entries:
        if entry.kind is LedgerKind.SALE:
            category = decide(Category(entry.category), entry.override_category)
        else:
            sale = sales.get(entry.corrects_entry_id) if entry.corrects_entry_id else None
            follows = entry.locked_at is None and not is_reclassification(entry) and sale is not None
            category = (
                decide(Category(sale.category), sale.override_category) if follows else Category(entry.category)
            )
        rows.append(ReportRow(entry, category))
    return rows


def _rows(db: Session, date_from: date, date_to: date, reports: list[HandedOverReport]) -> list[ReportRow]:
    in_range = LedgerEntry.entry_date.between(date_from, date_to)
    earlier = [r for r in reports if r.date_to < date_from]
    condition = in_range
    if earlier:
        # dated in a range handed over earlier, and not in it: written after it went
        late = and_(
            LedgerEntry.locked_at.is_(None),
            or_(*(LedgerEntry.entry_date.between(r.date_from, r.date_to) for r in earlier)),
        )
        condition = or_(in_range, late)
    entries = list(
        db.scalars(
            select(LedgerEntry)
            .where(condition)
            .options(selectinload(LedgerEntry.overridden_by))
            .order_by(LedgerEntry.entry_at, LedgerEntry.order_number)
        )
    )
    sale_ids = {e.corrects_entry_id for e in entries if e.corrects_entry_id}
    sales = {e.id: e for e in entries if e.kind is LedgerKind.SALE}
    missing = sale_ids - set(sales)
    if missing:
        sales.update({e.id: e for e in db.scalars(select(LedgerEntry).where(LedgerEntry.id.in_(missing)))})
    rows = _effective(entries, sales)
    for row in rows:
        row.late = row.entry.entry_date < date_from
    return rows


def _checks(db: Session, rows: list[ReportRow], listed: list[ReportRow], date_from: date, date_to: date) -> Checks:
    checks = Checks(
        to_review=sum(1 for row in rows if row.category is Category.TO_REVIEW),
        needs_register=sum(1 for row in rows if row.category is Category.NEEDS_REGISTER),
        untraced_sales=sum(
            1 for row in listed if row.entry.kind is LedgerKind.SALE and not row.entry.operation_fingerprint
        ),
    )
    start, end = _bounds(date_from, date_to)
    contributions = list(
        db.scalars(
            select(PaymentOperation).where(
                PaymentOperation.type == CONTRIBUTION,
                PaymentOperation.occurred_at >= _db_datetime(db, start),
                PaymentOperation.occurred_at < _db_datetime(db, end),
            )
        )
    )
    if contributions:
        fingerprints = [op.fingerprint for op in contributions]
        accounted = set(
            db.scalars(
                select(LedgerEntry.operation_fingerprint).where(LedgerEntry.operation_fingerprint.in_(fingerprints))
            )
        )
        unmatched = [op for op in contributions if op.fingerprint not in accounted]
        checks.unmatched_payments = len(unmatched)
        checks.unmatched_amount = sum((op.amount for op in unmatched), ZERO)
    return checks


def limit_status(db: Session, year: int) -> LimitStatus:
    """The year's sales on every channel against the VAT exemption limit (4f): the ledger's rows of
    the year, sales and corrections, and before the ledger's first row the paid orders Anvero holds.
    """
    first_day, last_day = date(year, 1, 1), date(year, 12, 31)
    ledger_total = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.entry_date.between(first_day, last_day)
        )
    )
    ledger_start = db.scalar(select(func.min(LedgerEntry.entry_date)))
    before_end = min(ledger_start, last_day + timedelta(days=1)) if ledger_start else last_day + timedelta(days=1)
    start, _ = _bounds(first_day, first_day)
    end, _ = _bounds(before_end, before_end)
    before_total, first_paid = ZERO, None
    if before_end > first_day:
        before_total = db.scalar(
            select(func.coalesce(func.sum(Order.paid_amount), 0)).where(
                Order.deleted_at.is_(None),
                Order.paid_at >= _db_datetime(db, start),
                Order.paid_at < _db_datetime(db, end),
            )
        )
    first_paid_at = db.scalar(
        select(func.min(Order.paid_at)).where(
            Order.deleted_at.is_(None),
            Order.paid_at >= _db_datetime(db, start),
            Order.paid_at < _db_datetime(db, _bounds(last_day, last_day)[1]),
        )
    )
    if first_paid_at is not None:
        first_paid = business_date(first_paid_at)
    candidates = [d for d in (first_paid, ledger_start) if d is not None and d.year == year]
    counted_from = min(candidates) if candidates else None
    total = Decimal(str(ledger_total or 0)) + Decimal(str(before_total or 0))
    return LimitStatus(year=year, total=total.quantize(Decimal("0.01")), counted_from=counted_from)


def build_report(db: Session, date_from: date, date_to: date) -> Report:
    """What the range holds, as described in the module's docstring."""
    reports = handed_over_reports(db)
    exact = next((r for r in reports if r.date_from == date_from and r.date_to == date_to), None)
    overlapping = [
        r for r in reports if r is not exact and r.date_from <= date_to and r.date_to >= date_from
    ]
    rows = _rows(db, date_from, date_to, [r for r in reports if r is not exact])
    if exact is not None:
        by_id = {row.entry.id: row for row in rows}
        listed = []
        for stored in exact.rows:
            if stored.entry_id in by_id:
                listed.append(by_id[stored.entry_id])
            elif stored.entry is not None:
                listed.append(ReportRow(stored.entry, Category.EXEMPT_MAIL_ORDER, late=True))
    else:
        listed = listing_order(rows)
    return Report(
        date_from=date_from,
        date_to=date_to,
        rows=rows,
        listed=listed,
        totals=totals_by_category(rows),
        checks=_checks(db, rows, listed, date_from, date_to),
        limit=limit_status(db, date_to.year),
        handed_over=exact,
        overlapping=overlapping,
    )


# --- handing over -------------------------------------------------------------------------------


def hand_over(
    db: Session,
    date_from: date,
    date_to: date,
    user_id: int | None,
    acknowledged: bool = False,
    now: datetime | None = None,
) -> HandedOverReport:
    """Record the range's report as handed over to the accountant and lock the rows it lists.
    Commits. Refused (ReportRefused) when the range has not ended, overlaps a range handed over,
    holds a sale still to decide, or has a warning not acknowledged."""
    now = now or datetime.now(UTC)
    if date_to < date_from:
        raise ReportRefused("INVALID_RANGE", "The range ends before it begins")
    if date_to >= business_date(now):
        raise ReportRefused("NOT_ENDED", "A range can be handed over once it has ended")
    report = build_report(db, date_from, date_to)
    if report.handed_over is not None or report.overlapping:
        raise ReportRefused("ALREADY_HANDED_OVER", "Part of this range was already handed over")
    if report.checks.blocking:
        raise ReportRefused(
            "TO_REVIEW", f"{report.checks.to_review} sale(s) still wait for a decision; decide them first"
        )
    if report.checks.warnings and not acknowledged:
        raise ReportRefused("NOT_ACKNOWLEDGED", "The report has warnings; acknowledge them to hand it over")

    handed = HandedOverReport(
        date_from=date_from,
        date_to=date_to,
        handed_over_at=now,
        handed_over_by_user_id=user_id,
        ruleset=RULESET,
        total=report.total,
        currency=report.currency,
        row_count=len(report.listed),
    )
    handed.rows = [
        HandedOverReportRow(position=position, entry_id=row.entry.id)
        for position, row in enumerate(report.listed, start=1)
    ]
    db.add(handed)
    db.flush()
    NonInvoicedRepository(db).lock([row.entry.id for row in report.listed], now)
    db.refresh(handed)
    return handed
