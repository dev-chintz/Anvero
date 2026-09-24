"""Returns, claims and disputes: the queue, and what one order has open."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.order_number import format_order_number
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.after_sales import AfterSalesCase, CaseAction, CaseKind
from app.repositories.after_sales_repository import AfterSalesRepository, CaseView
from app.repositories.order_repository import OrderRepository
from app.schemas.after_sales import AfterSalesSummary, CaseList, CaseRead
from app.schemas.types import _as_utc

router = APIRouter(tags=["After sales"], dependencies=[Depends(get_current_user)])


def _read(
    case: AfterSalesCase, order_id: uuid.UUID | None, order_number: int | None, now: datetime
) -> CaseRead:
    due = _as_utc(case.due_at) if case.due_at else None
    read = CaseRead.model_validate(case)
    read.overdue = bool(due and case.action is not CaseAction.NONE and due < now)
    read.order_id = order_id
    read.order_label = format_order_number(order_number) if order_number is not None else None
    return read


@router.get("/after-sales", response_model=CaseList)
def list_cases(
    view: CaseView = CaseView.ACTION,
    kind: CaseKind | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Cases, by default those waiting for the seller with the closest deadline first."""
    now = datetime.now(UTC)
    rows, total = AfterSalesRepository(db).list(view, kind, limit, offset)
    return CaseList(items=[_read(*row, now) for row in rows], total=total)


@router.get("/after-sales/summary", response_model=AfterSalesSummary)
def summary(db: Session = Depends(get_db)):
    return AfterSalesRepository(db).summary(datetime.now(UTC))


@router.get("/orders/{order_id}/after-sales", response_model=list[CaseRead])
def cases_of_order(order_id: uuid.UUID, db: Session = Depends(get_db)):
    order = OrderRepository(db).get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    now = datetime.now(UTC)
    rows = AfterSalesRepository(db).for_order(order.source, order.external_id)
    return [_read(*row, now) for row in rows]
