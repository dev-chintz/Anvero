"""The money side of the orders: what was sold in a period, what the marketplaces
took for it, and what is left.

Two bases, as the marketplaces' own finance screens use them:

- The **summary** counts sales by the day an order was placed and fees by the
  day the marketplace booked them, as Allegro's Centrum Finansów does, so its
  fee total can be checked against Allegro's.
- The **orders** and **products** tables take the orders placed in the period
  and every fee booked for each of them, whenever it was booked, so each row
  says what that order (or product) left.

A fee is a billing entry with a negative amount; a refund of a fee is positive
and lowers the total. The marketplace taking its fees out of the proceeds (an
entry marked `is_settlement` by its adapter) is not a fee and is left out:
counted in, it would bring the fees to zero.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.order_number import format_order_number
from app.models.order import BillingEntry, Order, OrderSource, OrderStatus, Payout

# the commission, and what is given back of it: Allegro's SUC; Erli's
# commission, its correction and the rebates used on it
COMMISSION_TYPES = frozenset({"SUC", "COMM", "COCR", "CRUC", "CRUS", "CRCO"})

ZERO = Decimal("0.00")


def fee_kind(type_id: str, type_name: str | None) -> str:
    """"commission", "delivery" or "other", for the columns of the orders table."""
    if type_id in COMMISSION_TYPES:
        return "commission"
    name = (type_name or "").lower()
    if any(word in name for word in ("dostaw", "przesył", "delivery", "shipping")):
        return "delivery"
    return "other"


def previous_period(date_from: date, date_to: date) -> tuple[date, date]:
    """The period of the same length ending the day before `date_from`."""
    days = (date_to - date_from).days + 1
    return date_from - timedelta(days=days), date_from - timedelta(days=1)


@dataclass
class FeeTotals:
    commission: Decimal = ZERO
    delivery: Decimal = ZERO
    other: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.commission + self.delivery + self.other

    def add(self, kind: str, fee: Decimal) -> None:
        setattr(self, kind, getattr(self, kind) + fee)


@dataclass
class OrderMoney:
    id: uuid.UUID
    order_label: str
    source: OrderSource
    ordered_at: datetime
    currency: str
    sales: Decimal
    fees: FeeTotals


@dataclass
class ProductMoney:
    key: str
    name: str
    sku: str | None
    offer_id: str | None
    image_url: str | None
    quantity: int = 0
    sales: Decimal = ZERO
    fees: Decimal = ZERO
    orders: set = field(default_factory=set)


class FinanceService:
    def __init__(self, db: Session, currency: str = "PLN"):
        self.db = db
        self.currency = currency

    # ---- time ----

    def _bounds(self, date_from: date, date_to: date) -> tuple[datetime, datetime]:
        """Local midnight of the first day to local midnight after the last, as stored."""
        zone = ZoneInfo(settings.business_timezone)
        start = datetime.combine(date_from, time.min, zone).astimezone(UTC)
        end = datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(UTC)
        if self.db.get_bind().dialect.name == "sqlite":
            return start.replace(tzinfo=None), end.replace(tzinfo=None)
        return start, end

    # ---- what counts ----

    def _sold(self, start: datetime, end: datetime):
        """The orders that count as sold in the period: placed in it, in this currency,
        neither deleted nor cancelled (here or on the marketplace)."""
        return (
            Order.ordered_at >= start,
            Order.ordered_at < end,
            Order.currency == self.currency,
            Order.deleted_at.is_(None),
            Order.status != OrderStatus.CANCELLED,
            Order.marketplace_cancelled_at.is_(None),
        )

    def _is_fee(self):
        return (
            BillingEntry.is_settlement.is_(False),
            BillingEntry.currency == self.currency,
        )

    # ---- the summary ----

    def sales_by_source(self, date_from: date, date_to: date) -> dict[OrderSource, tuple[Decimal, int]]:
        start, end = self._bounds(date_from, date_to)
        rows = self.db.execute(
            select(Order.source, func.coalesce(func.sum(Order.total_amount), 0), func.count(Order.id))
            .where(*self._sold(start, end))
            .group_by(Order.source)
        ).all()
        return {source: (Decimal(total).quantize(ZERO), count) for source, total, count in rows}

    def delivery_paid(self, date_from: date, date_to: date) -> dict[OrderSource, Decimal]:
        """What the buyers paid for delivery in the orders sold in the period."""
        start, end = self._bounds(date_from, date_to)
        rows = self.db.execute(
            select(Order.source, func.coalesce(func.sum(Order.delivery_cost), 0))
            .where(*self._sold(start, end))
            .group_by(Order.source)
        ).all()
        return {source: Decimal(total).quantize(ZERO) for source, total in rows}

    def fees_by_type(self, date_from: date, date_to: date) -> dict[tuple[OrderSource, str], tuple[str | None, Decimal]]:
        """What each kind of fee came to, booked in the period, as a positive amount."""
        start, end = self._bounds(date_from, date_to)
        rows = self.db.execute(
            select(
                BillingEntry.source,
                BillingEntry.type_id,
                func.max(BillingEntry.type_name),
                func.coalesce(func.sum(BillingEntry.amount), 0),
            )
            .where(BillingEntry.occurred_at >= start, BillingEntry.occurred_at < end, *self._is_fee())
            .group_by(BillingEntry.source, BillingEntry.type_id)
        ).all()
        return {(source, type_id): (name, -Decimal(total).quantize(ZERO)) for source, type_id, name, total in rows}

    def settled(self, date_from: date, date_to: date) -> dict[OrderSource, Decimal]:
        """What each marketplace took out of the proceeds to pay its fees, in the period."""
        start, end = self._bounds(date_from, date_to)
        rows = self.db.execute(
            select(BillingEntry.source, func.coalesce(func.sum(BillingEntry.amount), 0))
            .where(
                BillingEntry.occurred_at >= start,
                BillingEntry.occurred_at < end,
                BillingEntry.is_settlement.is_(True),
                BillingEntry.currency == self.currency,
            )
            .group_by(BillingEntry.source)
        ).all()
        return {source: Decimal(total).quantize(ZERO) for source, total in rows}

    def unsettled(self) -> dict[OrderSource, tuple[Decimal, datetime]]:
        """Per marketplace, the fees it has not yet taken from the proceeds, over
        everything read, and since when that is.

        A month can end between a fee and its settlement (Erli takes the fees of
        the last days of a month in the next), so the check is made over all
        that is held, where the two meet.
        """
        rows = self.db.execute(
            select(
                BillingEntry.source,
                func.coalesce(func.sum(BillingEntry.amount), 0),
                func.min(BillingEntry.occurred_at),
            )
            .where(BillingEntry.currency == self.currency)
            .group_by(BillingEntry.source)
        ).all()
        # fees are negative and settlements positive, so what is owed is minus their sum
        return {source: (-Decimal(total).quantize(ZERO), since) for source, total, since in rows}

    def paid_out(self, date_from: date, date_to: date) -> dict[OrderSource, Decimal]:
        """What each marketplace sent to the bank in the period; a marketplace whose
        payouts are read but made none in the period has 0, one never read is absent."""
        start, end = self._bounds(date_from, date_to)
        read = set(self.db.scalars(select(Payout.source).distinct()))
        rows = dict(
            self.db.execute(
                select(Payout.source, func.coalesce(func.sum(Payout.amount), 0))
                .where(Payout.paid_at >= start, Payout.paid_at < end, Payout.currency == self.currency)
                .group_by(Payout.source)
            ).all()
        )
        return {source: Decimal(rows.get(source, 0)).quantize(ZERO) for source in read}

    # ---- per order and per product ----

    def _orders_sold(self, date_from: date, date_to: date, with_items: bool = False) -> list[Order]:
        start, end = self._bounds(date_from, date_to)
        query = select(Order).where(*self._sold(start, end)).order_by(Order.ordered_at.desc(), Order.id)
        if with_items:
            query = query.options(selectinload(Order.items))
        return list(self.db.scalars(query))

    def _fee_entries(self, orders: list[Order]) -> list[BillingEntry]:
        """Every fee booked for these orders, whenever it was booked."""
        by_source: dict[OrderSource, list[str]] = {}
        for order in orders:
            by_source.setdefault(order.source, []).append(order.external_id)
        entries: list[BillingEntry] = []
        for source, ids in by_source.items():
            # in chunks, so a long period stays under the databases' parameter limits
            for i in range(0, len(ids), 500):
                entries.extend(
                    self.db.scalars(
                        select(BillingEntry).where(
                            BillingEntry.source == source,
                            BillingEntry.order_external_id.in_(ids[i : i + 500]),
                            *self._is_fee(),
                        )
                    )
                )
        return entries

    def orders(self, date_from: date, date_to: date) -> list[OrderMoney]:
        """The orders placed in the period, newest first, each with its fees by kind."""
        orders = self._orders_sold(date_from, date_to)
        fees: dict[tuple[OrderSource, str], FeeTotals] = {}
        for entry in self._fee_entries(orders):
            key = (entry.source, entry.order_external_id)
            fees.setdefault(key, FeeTotals()).add(fee_kind(entry.type_id, entry.type_name), -entry.amount)
        return [
            OrderMoney(
                id=order.id,
                order_label=format_order_number(order.order_number),
                source=order.source,
                ordered_at=order.ordered_at,
                currency=order.currency,
                sales=order.total_amount,
                fees=fees.get((order.source, order.external_id), FeeTotals()),
            )
            for order in orders
        ]

    def products(self, date_from: date, date_to: date) -> list[ProductMoney]:
        """What each product sold in the period and what its fees came to.

        A fee that names an offer (Allegro's offer, Erli's item id) goes to the
        items of that offer in its order; a
        fee that names none (the delivery) is shared among the order's items by
        their value. A product is its SKU, else its offer, else its name, as on
        the To make page. The order's delivery charge to the buyer is not a
        product's sale, so an item's sale is its price times its quantity.
        """
        orders = self._orders_sold(date_from, date_to, with_items=True)
        entries_by_order: dict[tuple[OrderSource, str], list[BillingEntry]] = {}
        for entry in self._fee_entries(orders):
            entries_by_order.setdefault((entry.source, entry.order_external_id), []).append(entry)

        products: dict[str, ProductMoney] = {}
        for order in orders:
            items = list(order.items)
            if not items:
                continue
            values = [item.unit_price * item.quantity for item in items]
            shares = [ZERO for _ in items]
            for entry in entries_by_order.get((order.source, order.external_id), []):
                fee = -entry.amount
                matching = [
                    i
                    for i, item in enumerate(items)
                    if entry.offer_id and entry.offer_id in (item.offer_id, item.external_id)
                ]
                targets = matching or list(range(len(items)))
                base = sum((values[i] for i in targets), ZERO)
                for i in targets:
                    part = fee * values[i] / base if base else fee / len(targets)
                    shares[i] += part
            for item, value, share in zip(items, values, shares):
                key = f"sku:{item.sku}" if item.sku else f"offer:{item.offer_id}" if item.offer_id else f"name:{item.name}"
                product = products.get(key)
                if product is None:
                    product = products[key] = ProductMoney(
                        key=key, name=item.name, sku=item.sku, offer_id=item.offer_id, image_url=item.image_url
                    )
                product.image_url = product.image_url or item.image_url
                product.quantity += item.quantity
                product.sales += value
                product.fees += share
                product.orders.add(order.id)
        for product in products.values():
            product.sales = product.sales.quantize(ZERO)
            product.fees = product.fees.quantize(ZERO)
        return sorted(products.values(), key=lambda p: (p.sales - p.fees), reverse=True)
