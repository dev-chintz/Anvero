"""Classifying the stored orders paid in a period (docs/NON_INVOICED_SALES.md, section 5, stage 2).

Reads only: the orders, their payment operations and nothing else, so it can run beside an import.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order, PaymentOperation
from app.services.non_invoiced.classifier import Category, Classification, Reason, classify, facts_from_order


@dataclass(frozen=True)
class ClassifiedOrder:
    order: Order
    classification: Classification


def classify_paid_between(
    db: Session,
    paid_from: datetime,
    paid_to: datetime,
    excluded_offer_ids: frozenset[str] = frozenset(),
) -> list[ClassifiedOrder]:
    """Every order paid in [paid_from, paid_to), not deleted, classified; oldest payment first.

    Orders never paid are not read: they belong to no period, and `classify` would only call them
    `NOT_A_SALE`.
    """
    if db.get_bind().dialect.name == "sqlite":
        # SQLite keeps naive UTC, and an aware bound would never compare equal
        paid_from = paid_from.astimezone(UTC).replace(tzinfo=None)
        paid_to = paid_to.astimezone(UTC).replace(tzinfo=None)
    orders = list(
        db.scalars(
            select(Order)
            .where(Order.deleted_at.is_(None), Order.paid_at >= paid_from, Order.paid_at < paid_to)
            .options(selectinload(Order.addresses), selectinload(Order.items), selectinload(Order.extra_payments))
            .order_by(Order.paid_at, Order.order_number)
        )
    )
    ids = {order.payment_id for order in orders if order.payment_id}
    ids |= {p.external_id for order in orders for p in order.extra_payments if p.external_id}
    operations: dict[str, list[PaymentOperation]] = {}
    for start in range(0, len(ids), 500):
        chunk = sorted(ids)[start : start + 500]
        for operation in db.scalars(
            select(PaymentOperation).where(
                or_(PaymentOperation.payment_id.in_(chunk), PaymentOperation.surcharge_id.in_(chunk))
            )
        ):
            for key in {operation.payment_id, operation.surcharge_id} - {None}:
                operations.setdefault(key, []).append(operation)

    classified = []
    for order in orders:
        keys = [order.payment_id] + [p.external_id for p in order.extra_payments]
        found = {id(op): op for key in keys if key for op in operations.get(key, [])}
        facts = facts_from_order(order, found.values(), excluded_offer_ids)
        classified.append(ClassifiedOrder(order, classify(facts)))
    return classified


def counts(classified: list[ClassifiedOrder]) -> tuple[Counter[Category], Counter[tuple[Category, Reason]]]:
    """How many orders fall in each category, and in each category and reason."""
    return (
        Counter(c.classification.category for c in classified),
        Counter((c.classification.category, c.classification.reason) for c in classified),
    )
