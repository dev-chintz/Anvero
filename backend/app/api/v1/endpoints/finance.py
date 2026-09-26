"""The Finance page: a period's sales, what the marketplaces took, and what is left."""

from datetime import date
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.order import OrderSource
from app.repositories.integration_credential_repository import IntegrationCredentialRepository
from app.schemas.finance import (
    FeeTypeMoney,
    FinanceSummary,
    OrderFees,
    OrderFeesList,
    ProductFees,
    ProductFeesList,
    Settlement,
    SourceMoney,
)
from app.services.finance import ZERO, FinanceService, previous_period

router = APIRouter(prefix="/finance", tags=["Finance"], dependencies=[Depends(get_current_user)])

# a period longer than this is refused: the tables are computed whole
MAX_DAYS = 366


class OrderFeesSort(str, Enum):
    NEWEST = "newest"
    # the largest share of the sale taken by fees first
    SHARE = "share"


def _period(date_from: date, date_to: date) -> tuple[date, date]:
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="date_to is before date_from")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"A period may be at most {MAX_DAYS} days")
    return date_from, date_to


@router.get("/summary", response_model=FinanceSummary)
def summary(date_from: date, date_to: date, db: Session = Depends(get_db)):
    """Sales by the day ordered and fees by the day booked, beside the period before."""
    date_from, date_to = _period(date_from, date_to)
    previous_from, previous_to = previous_period(date_from, date_to)
    finance = FinanceService(db)

    sales, previous_sales = finance.sales_by_source(date_from, date_to), finance.sales_by_source(previous_from, previous_to)
    fees, previous_fees = finance.fees_by_type(date_from, date_to), finance.fees_by_type(previous_from, previous_to)
    settled = finance.settled(date_from, date_to)
    paid_out = finance.paid_out(date_from, date_to)

    def fees_of(table, source):
        return sum((amount for (s, _), (_, amount) in table.items() if s == source), ZERO)

    sources = sorted(
        {*sales, *previous_sales, *(s for s, _ in fees), *(s for s, _ in previous_fees), *paid_out},
        key=lambda s: s.value,
    )
    by_source = [
        SourceMoney(
            source=source,
            sales=sales.get(source, (ZERO, 0))[0],
            orders=sales.get(source, (ZERO, 0))[1],
            fees=fees_of(fees, source),
            previous_sales=previous_sales.get(source, (ZERO, 0))[0],
            previous_fees=fees_of(previous_fees, source),
            paid_out=paid_out.get(source),
        )
        for source in sources
    ]
    by_type = sorted(
        (
            FeeTypeMoney(
                source=source,
                type_id=type_id,
                type_name=(fees.get((source, type_id)) or previous_fees.get((source, type_id)))[0],
                fees=fees.get((source, type_id), (None, ZERO))[1],
                previous_fees=previous_fees.get((source, type_id), (None, ZERO))[1],
            )
            for source, type_id in {*fees, *previous_fees}
        ),
        key=lambda row: (-row.fees, -row.previous_fees, row.type_id),
    )
    credentials = IntegrationCredentialRepository(db)
    unsettled = finance.unsettled()
    settlements = [
        Settlement(
            source=source,
            fees=fees_of(fees, source),
            settled=settled.get(source, ZERO),
            unsettled=unsettled.get(source, (ZERO, None))[0],
            held_since=unsettled.get(source, (ZERO, None))[1],
            synced_at=credentials.last_billing_synced_at(source.value),
        )
        for source in OrderSource
        if source in settled or any(s == source for s, _ in fees) or credentials.last_billing_synced_at(source.value)
    ]
    return FinanceSummary(
        date_from=date_from,
        date_to=date_to,
        previous_from=previous_from,
        previous_to=previous_to,
        currency=finance.currency,
        sales=sum((row.sales for row in by_source), ZERO),
        orders=sum(row.orders for row in by_source),
        fees=sum((row.fees for row in by_source), ZERO),
        previous_sales=sum((row.previous_sales for row in by_source), ZERO),
        previous_orders=sum(n for _, n in previous_sales.values()),
        previous_fees=sum((row.previous_fees for row in by_source), ZERO),
        paid_out=sum(paid_out.values(), ZERO) if paid_out else None,
        by_source=by_source,
        by_type=by_type,
        settlements=settlements,
    )


@router.get("/orders", response_model=OrderFeesList)
def orders(
    date_from: date,
    date_to: date,
    sort: OrderFeesSort = OrderFeesSort.NEWEST,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """The orders placed in the period, each with every fee booked for it."""
    date_from, date_to = _period(date_from, date_to)
    rows = FinanceService(db).orders(date_from, date_to)
    if sort is OrderFeesSort.SHARE:
        rows.sort(key=lambda r: (r.fees.total / r.sales if r.sales else Decimal(0)), reverse=True)
    page = rows[offset : offset + limit]
    return OrderFeesList(
        total=len(rows),
        items=[
            OrderFees(
                id=r.id,
                order_label=r.order_label,
                source=r.source,
                ordered_at=r.ordered_at,
                currency=r.currency,
                sales=r.sales,
                commission=r.fees.commission.quantize(ZERO),
                delivery=r.fees.delivery.quantize(ZERO),
                other=r.fees.other.quantize(ZERO),
                fees=r.fees.total.quantize(ZERO),
            )
            for r in page
        ],
    )


@router.get("/products", response_model=ProductFeesList)
def products(date_from: date, date_to: date, db: Session = Depends(get_db)):
    """Each product sold in the period, with its share of its orders' fees; most left first."""
    date_from, date_to = _period(date_from, date_to)
    return ProductFeesList(
        items=[
            ProductFees(
                key=p.key,
                name=p.name,
                sku=p.sku,
                offer_id=p.offer_id,
                image_url=p.image_url,
                quantity=p.quantity,
                orders=len(p.orders),
                sales=p.sales,
                fees=p.fees,
            )
            for p in FinanceService(db).products(date_from, date_to)
        ]
    )
