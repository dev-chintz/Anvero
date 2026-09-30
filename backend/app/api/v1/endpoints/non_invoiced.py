"""The non-invoiced sales record: a range's report, overrides, exports, handing over
(docs/API.md, "Non-invoiced sales record"; docs/NON_INVOICED_SALES.md, stage 4)."""

import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.order_number import format_order_number
from app.core.permissions import require_permission
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.non_invoiced import HandedOverReport, LedgerEntry
from app.models.user import User
from app.models.user_permission import PermissionArea, PermissionLevel
from app.schemas.non_invoiced import (
    CategoryTotalRead,
    ChecksRead,
    ExportColumnList,
    ExportColumnRead,
    HandedOverRead,
    HandOverIn,
    LedgerOverrideRead,
    LedgerRowRead,
    LimitRead,
    NonInvoicedReportRead,
    OverrideIn,
)
from app.services.non_invoiced.classifier import REASON_TEXT, Category, Reason
from app.services.non_invoiced.export import (
    CATEGORY_TEXT,
    COLUMNS,
    DEFAULT_COLUMNS,
    FORMATS,
    export,
    file_name,
    resolve_columns,
)
from app.services.non_invoiced.ledger import (
    OverrideRefused,
    business_date,
    clear_override,
    set_override,
)
from app.services.non_invoiced.report import (
    Report,
    ReportRefused,
    ReportRow,
    build_report,
    get_handed_over,
    hand_over,
    handed_over_reports,
)
from app.services.shipping_settings import get_shipping_settings

router = APIRouter(
    prefix="/non-invoiced",
    tags=["Non-invoiced sales record"],
    dependencies=[require_permission(PermissionArea.FINANCE)],
)
_manage = require_permission(PermissionArea.FINANCE, PermissionLevel.MANAGE)

logger = logging.getLogger(__name__)

MAX_DAYS = 366
# what a person may decide a sale is; "to review" is what waits for that decision, not one
OVERRIDABLE = {
    Category.EXEMPT_MAIL_ORDER,
    Category.PRIVATE_INVOICED,
    Category.BUSINESS,
    Category.NEEDS_REGISTER,
    Category.NOT_A_SALE,
}


def _range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="date_to is before date_from")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"A range may be at most {MAX_DAYS} days")


def _reason_text(code: str) -> str:
    try:
        return REASON_TEXT[Reason(code)]
    except (ValueError, KeyError):
        return code


def _row(row: ReportRow) -> LedgerRowRead:
    entry: LedgerEntry = row.entry
    name = " ".join(p for p in (entry.buyer_first_name, entry.buyer_last_name) if p) or None
    city = " ".join(p for p in (entry.buyer_postal_code, entry.buyer_city) if p)
    address = ", ".join(p for p in (entry.buyer_street, city) if p) or None
    override = None
    if entry.override_category:
        override = LedgerOverrideRead(
            category=Category(entry.override_category),
            note=entry.override_note,
            by=entry.overridden_by.email if entry.overridden_by else None,
            at=entry.overridden_at,
        )
    return LedgerRowRead(
        id=entry.id,
        kind=entry.kind,
        entry_date=entry.entry_date,
        entry_at=entry.entry_at,
        source=entry.source,
        order_id=entry.order_id,
        order_label=format_order_number(entry.order_number),
        order_external_id=entry.order_external_id,
        corrects_entry_id=entry.corrects_entry_id,
        buyer_name=name,
        buyer_address=address,
        amount=entry.amount,
        currency=entry.currency,
        category=row.category,
        automatic_category=Category(entry.category),
        reason=entry.reason,
        reason_text=_reason_text(entry.reason),
        ruleset=entry.ruleset,
        override=override,
        locked=entry.locked_at is not None,
        in_report=row.in_report,
        late=row.late,
        payment_operator=entry.payment_operator,
        payout_date=business_date(entry.payout_at) if entry.payout_at else None,
    )


def _handed(report: HandedOverReport) -> HandedOverRead:
    return HandedOverRead(
        id=report.id,
        date_from=report.date_from,
        date_to=report.date_to,
        handed_over_at=report.handed_over_at,
        handed_over_by=report.handed_over_by.email if report.handed_over_by else None,
        total=report.total,
        currency=report.currency,
        row_count=report.row_count,
        ruleset=report.ruleset,
    )


def _read(report: Report) -> NonInvoicedReportRead:
    ended = report.date_to < business_date(datetime.now(UTC))
    return NonInvoicedReportRead(
        date_from=report.date_from,
        date_to=report.date_to,
        rows=[_row(row) for row in report.rows],
        listed=[row.entry.id for row in report.listed],
        total=report.total,
        currency=report.currency,
        totals=[
            CategoryTotalRead(
                category=t.category,
                label=CATEGORY_TEXT[t.category],
                sales=t.sales,
                sales_amount=t.sales_amount,
                corrections=t.corrections,
                corrections_amount=t.corrections_amount,
                total=t.total,
            )
            for t in report.totals
        ],
        checks=ChecksRead(
            to_review=report.checks.to_review,
            needs_register=report.checks.needs_register,
            unmatched_payments=report.checks.unmatched_payments,
            unmatched_amount=report.checks.unmatched_amount,
            untraced_sales=report.checks.untraced_sales,
            blocking=report.checks.blocking,
            warnings=report.checks.warnings,
        ),
        limit=LimitRead(
            year=report.limit.year,
            total=report.limit.total,
            limit=report.limit.limit,
            share=report.limit.share,
            counted_from=report.limit.counted_from,
            warning=report.limit.warning,
            exceeded=report.limit.exceeded,
        ),
        handed_over=_handed(report.handed_over) if report.handed_over else None,
        overlapping=[_handed(r) for r in report.overlapping],
        ended=ended,
        can_hand_over=ended
        and report.handed_over is None
        and not report.overlapping
        and not report.checks.blocking,
    )


@router.get("/report", response_model=NonInvoicedReportRead)
def report(date_from: date, date_to: date, db: Session = Depends(get_db)):
    """What the range holds: its rows, what it lists, the totals, the checks and the VAT limit."""
    _range(date_from, date_to)
    return _read(build_report(db, date_from, date_to))


@router.get("/columns", response_model=ExportColumnList)
def columns():
    """Every column an export can hold, and the accountant's default set."""
    return ExportColumnList(
        items=[ExportColumnRead(key=c.key, label=c.label, personal=c.personal) for c in COLUMNS.values()],
        default=DEFAULT_COLUMNS,
    )


def _seller(db: Session) -> list[str]:
    """The seller as the PDF names them: the sender set in Integrations, when it is."""
    sender = get_shipping_settings(db).sender
    if sender is None:
        return []
    lines = [sender.company or sender.name]
    if sender.company:
        lines.append(sender.name)
    lines.append(f"{sender.street}, {sender.postal_code} {sender.city}")
    return lines


def _file(db: Session, report: Report, fmt: str, chosen: str | None, user: User) -> Response:
    if fmt not in FORMATS:
        raise HTTPException(status_code=422, detail="format must be csv, xlsx or pdf")
    try:
        resolved = resolve_columns([key for key in chosen.split(",") if key] if chosen else None)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown export column: {exc.args[0]}") from exc
    personal = [c.key for c in resolved if c.personal]
    if personal:
        # the user and the column names only, never a value from the file (docs/GDPR.md)
        logger.info(
            "Non-invoiced record %s..%s exported as %s with personal data (%s, %d rows) by user %s",
            report.date_from, report.date_to, fmt, ", ".join(personal), len(report.listed), user.id,
        )
    media_type, extension = FORMATS[fmt]
    return Response(
        content=export(report, fmt, resolved, _seller(db)),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name(report, extension)}"'},
    )


@router.get("/export")
def export_range(
    date_from: date,
    date_to: date,
    format: str = "csv",
    columns: str | None = Query(default=None, description="Comma-separated column keys, in order"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The rows the range's report lists as a file; for a range handed over, the same rows as
    then."""
    _range(date_from, date_to)
    return _file(db, build_report(db, date_from, date_to), format, columns, current_user)


@router.get("/reports", response_model=list[HandedOverRead])
def reports(db: Session = Depends(get_db)):
    """The reports handed over to the accountant, the latest range first."""
    return [_handed(r) for r in handed_over_reports(db)]


@router.post("/reports", response_model=HandedOverRead, status_code=201, dependencies=[_manage])
def hand_over_range(
    body: HandOverIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hand the range's report over to the accountant: it is recorded with the rows it lists, and
    they are locked."""
    _range(body.date_from, body.date_to)
    try:
        handed = hand_over(db, body.date_from, body.date_to, current_user.id, body.acknowledged)
    except ReportRefused as exc:
        status = 409 if exc.code == "ALREADY_HANDED_OVER" else 422
        raise HTTPException(status_code=status, detail={"code": exc.code, "message": str(exc)}) from exc
    logger.info(
        "Non-invoiced record %s..%s handed over by user %s (%d rows)",
        handed.date_from, handed.date_to, current_user.id, handed.row_count,
    )
    return _handed(handed)


@router.get("/reports/{report_id}/export")
def export_handed_over(
    report_id: uuid.UUID,
    format: str = "csv",
    columns: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    handed = get_handed_over(db, report_id)
    if handed is None:
        raise HTTPException(status_code=404, detail="No such report")
    return _file(db, build_report(db, handed.date_from, handed.date_to), format, columns, current_user)


@router.put("/entries/{entry_id}/override", response_model=LedgerOverrideRead, dependencies=[_manage])
def put_override(
    entry_id: uuid.UUID,
    body: OverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A person's category for a sale, with the reason written down; the classifier's result stays
    beside it."""
    if body.category not in OVERRIDABLE:
        raise HTTPException(status_code=422, detail="A sale cannot be decided to be still to review")
    try:
        entry = set_override(db, entry_id, body.category, body.note, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OverrideRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return LedgerOverrideRead(
        category=Category(entry.override_category),
        note=entry.override_note,
        by=current_user.email,
        at=entry.overridden_at,
    )


@router.delete("/entries/{entry_id}/override", status_code=204, dependencies=[_manage])
def delete_override(
    entry_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Back to the classifier's result."""
    try:
        clear_override(db, entry_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OverrideRefused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=204)
