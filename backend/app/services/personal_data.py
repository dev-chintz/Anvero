"""Answering one buyer's request about their data (GDPR articles 15, 17 and 20).

A buyer is found by their marketplace login, their e-mail, or both: orders,
message threads and after-sales cases naming either, plus the threads and cases
of those orders even when they name neither. `export_person` gives everything
held about them as plain data; `anonymize_person` erases it with the same
functions the retention rule uses (app/services/retention.py). An order still
inside its tax period keeps a company invoice's name, tax id and address,
which the law requires kept (article 17(3)(b)); retention erases those later.
The non-invoiced sales record's copy of the buyer is kept for the same reason
and left to retention alike.

Used by `scripts/export_person.py` and `scripts/anonymize_person.py`.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.models.after_sales import AfterSalesCase
from app.models.inpost_shipment import InpostShipment
from app.models.marketplace_write import MarketplaceWrite
from app.models.message import MessageThread
from app.models.order import Order
from app.models.shipping_label import ShippingLabel
from app.repositories.non_invoiced_repository import NonInvoicedRepository
from app.services.retention import (
    anonymize_case,
    anonymize_order,
    anonymize_thread,
    order_cutoff,
)


@dataclass
class PersonData:
    orders: list[Order] = field(default_factory=list)
    threads: list[MessageThread] = field(default_factory=list)
    cases: list[AfterSalesCase] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.orders or self.threads or self.cases)


def _matches(column, value: str | None):
    return func.lower(column) == value.strip().lower() if value else None


def find_person(db: Session, login: str | None = None, email: str | None = None) -> PersonData:
    """Everything held about the buyer with this login or e-mail (matched
    ignoring case). At least one is required."""
    if not (login and login.strip()) and not (email and email.strip()):
        raise ValueError("A login or an e-mail is required")

    def either(*pairs):
        conditions = [c for column, value in pairs if (c := _matches(column, value)) is not None]
        return or_(false(), *conditions)

    orders = db.scalars(
        select(Order)
        .where(either((Order.customer_login, login), (Order.customer_email, email)))
        .order_by(Order.ordered_at)
    ).all()
    order_refs = [(o.source, o.external_id) for o in orders]

    def of_orders(model):
        return [
            (model.source == source) & (model.order_external_id == external_id)
            for source, external_id in order_refs
        ]

    threads = db.scalars(
        select(MessageThread)
        .where(or_(either((MessageThread.interlocutor_login, login)), *of_orders(MessageThread)))
        .order_by(MessageThread.last_message_at)
    ).all()
    cases = db.scalars(
        select(AfterSalesCase)
        .where(
            or_(
                either((AfterSalesCase.buyer_login, login), (AfterSalesCase.buyer_email, email)),
                *of_orders(AfterSalesCase),
            )
        )
        .order_by(AfterSalesCase.opened_at)
    ).all()
    return PersonData(list(orders), list(threads), list(cases))


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _row(obj, leave_out: tuple[str, ...] = ()) -> dict[str, Any]:
    """Every column of the row, so an export holds all that is stored."""
    return {
        column.key: _value(getattr(obj, column.key))
        for column in obj.__table__.columns
        if column.key not in leave_out
    }


def export_person(db: Session, person: PersonData) -> dict[str, Any]:
    """Everything held about the person, as JSON-ready data."""
    orders = []
    for order in person.orders:
        entry = _row(order, leave_out=("deleted_by_user_id",))
        entry["addresses"] = [_row(a, leave_out=("id", "order_id")) for a in order.addresses]
        entry["items"] = [_row(i, leave_out=("id", "order_id")) for i in order.items]
        entry["shipments"] = [_row(s, leave_out=("id", "order_id")) for s in order.shipments]
        entry["labels"] = [
            _row(label, leave_out=("order_id", "created_by_user_id"))
            for label in db.scalars(select(ShippingLabel).where(ShippingLabel.order_id == order.id))
        ] + [
            _row(shipment, leave_out=("order_id", "created_by_user_id"))
            for shipment in db.scalars(
                select(InpostShipment).where(InpostShipment.order_id == order.id)
            )
        ]
        entry["sent_to_marketplace"] = [
            _row(write, leave_out=("order_id", "user_id"))
            for write in db.scalars(
                select(MarketplaceWrite).where(MarketplaceWrite.order_id == order.id)
            )
        ]
        entry["non_invoiced_record"] = [
            _row(row, leave_out=("order_id", "overridden_by_user_id"))
            for row in NonInvoicedRepository(db).entries_of_orders([order.id])
        ]
        orders.append(entry)
    threads = []
    for thread in person.threads:
        entry = _row(thread)
        entry["messages"] = [_row(m, leave_out=("thread_id",)) for m in thread.messages]
        threads.append(entry)
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "orders": orders,
        "message_threads": threads,
        "after_sales_cases": [_row(case) for case in person.cases],
    }


@dataclass
class ErasureResult:
    orders: int = 0
    invoices_kept: int = 0
    threads: int = 0
    cases: int = 0
    # rows of the non-invoiced sales record left as they are: a tax record the law requires kept
    # (article 17(3)(b)); retention erases their buyer copy once the period is over
    records_kept: int = 0


def anonymize_person(db: Session, person: PersonData, now: datetime | None = None) -> ErasureResult:
    """Erase what is held about the person, keeping a company invoice on an
    order still inside its tax period. Commits."""
    now = now or datetime.now(UTC)
    cutoff = order_cutoff(now)
    result = ErasureResult()
    for order in person.orders:
        ordered_at = order.ordered_at
        if ordered_at.tzinfo is None:
            ordered_at = ordered_at.replace(tzinfo=UTC)
        in_tax_period = ordered_at >= cutoff
        anonymize_order(db, order, now, keep_invoice=in_tax_period)
        result.orders += 1
        result.records_kept += sum(
            1 for row in NonInvoicedRepository(db).entries_of_orders([order.id]) if row.anonymized_at is None
        )
        if in_tax_period and any(a.tax_id for a in order.addresses):
            result.invoices_kept += 1
    for thread in person.threads:
        anonymize_thread(thread, now)
        result.threads += 1
    for case in person.cases:
        anonymize_case(case, now)
        result.cases += 1
    db.commit()
    return result
