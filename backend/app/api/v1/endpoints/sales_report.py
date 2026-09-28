"""The non-invoiced sales report: `docs/DECISIONS.md`, "Non-invoiced sales report, ported"."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.order import OrderSource
from app.models.user import User
from app.models.user_permission import PermissionArea, PermissionLevel
from app.schemas.sales_report import (
    SalesReportColumnList,
    SalesReportList,
    SalesReportOverrideIn,
)
from app.services.sales_report import SalesReportService
from app.services.sales_report_export import (
    COLUMNS,
    DEFAULT_COLUMNS,
    resolve_columns,
    to_csv,
)

router = APIRouter(
    prefix="/sales-report",
    tags=["Sales report"],
    dependencies=[require_permission(PermissionArea.FINANCE)],
)
_manage = require_permission(PermissionArea.FINANCE, PermissionLevel.MANAGE)

logger = logging.getLogger(__name__)

# columns that name or reach a person: an export holding any is logged with who
# made it (docs/GDPR.md, "Who looked at what")
PERSONAL_COLUMNS = {
    "customer_login",
    "customer_name",
    "customer_email",
    "customer_phone",
    "invoice_company_name",
    "invoice_tax_id",
    "invoice_address",
}

MAX_DAYS = 366


def _period(date_from: date, date_to: date) -> tuple[date, date]:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="date_to is before date_from")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"A period may be at most {MAX_DAYS} days")
    return date_from, date_to


@router.get("/orders", response_model=SalesReportList)
def orders(date_from: date, date_to: date, source: OrderSource | None = None, db: Session = Depends(get_db)):
    """Classify Anvero's own imported orders placed in the period. No CSV upload: that path is
    not built yet (`ROADMAP.md`)."""
    date_from, date_to = _period(date_from, date_to)
    return SalesReportService(db).from_orders(date_from, date_to, source)


@router.get("/columns", response_model=SalesReportColumnList)
def columns():
    """Every column the export can be built from, in the order the picker groups them, and the
    default set (`docs/DECISIONS.md`, "Export columns, chosen by the owner")."""
    return SalesReportColumnList(
        items=[{"key": c.key, "label": c.label} for c in COLUMNS.values()],
        default=DEFAULT_COLUMNS,
    )


@router.get("/orders/export")
def export(
    date_from: date,
    date_to: date,
    source: OrderSource | None = None,
    format: str = "csv",
    columns: str | None = Query(default=None, description="Comma-separated column keys, in order; the default set when omitted"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    date_from, date_to = _period(date_from, date_to)
    if format != "csv":
        # Excel and PDF are not built yet (ROADMAP.md); say so rather than silently giving CSV
        raise HTTPException(status_code=422, detail="Only format=csv is available so far")
    chosen = [key for key in columns.split(",") if key] if columns else None
    try:
        resolved = resolve_columns(chosen)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown export column: {exc.args[0]}") from exc
    pairs = SalesReportService(db).classified_orders(date_from, date_to, source)
    personal = [c.key for c in resolved if c.key in PERSONAL_COLUMNS]
    if personal:
        # the user and the column names only, never a value from the file
        logger.info(
            "Sales report %s..%s exported with personal data (%s, %d rows) by user %s",
            date_from, date_to, ", ".join(personal), len(pairs), current_user.id,
        )
    return Response(
        content=to_csv(pairs, resolved),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="raport-bezrachunkowy-{date_from}-{date_to}.csv"'},
    )


@router.put("/orders/{source}/{order_external_id}/override", dependencies=[_manage])
def set_override(
    source: OrderSource,
    order_external_id: str,
    body: SalesReportOverrideIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    SalesReportService(db).set_override(source, order_external_id, body.included, body.note, current_user.id)
    return {"ok": True}


@router.delete("/orders/{source}/{order_external_id}/override", dependencies=[_manage])
def clear_override(source: OrderSource, order_external_id: str, db: Session = Depends(get_db)):
    SalesReportService(db).clear_override(source, order_external_id)
    return {"ok": True}
