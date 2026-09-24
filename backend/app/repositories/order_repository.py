import enum
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Query, Session, selectinload

from app.core.config import settings
from app.core.order_number import parse_order_number
from app.models.order import (
    BillingEntry,
    Order,
    OrderAddress,
    OrderItem,
    OrderShipment,
    OrderSource,
    OrderStatus,
    OrderStatusHistory,
    PaymentType,
)
from app.schemas.order import BillingEntryCreate

PENDING_STATUSES = (OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.READY_FOR_SHIPMENT)
TO_MAKE_STATUSES = (OrderStatus.NEW, OrderStatus.CONFIRMED)
TO_SHIP_STATUSES = (OrderStatus.READY_FOR_SHIPMENT,)
# paid for only after it arrives, so no payment is owed before shipping
PAY_LATER_TYPES = (PaymentType.CASH_ON_DELIVERY, PaymentType.DEFERRED)


class OrderQueue(str, enum.Enum):
    """The work queues: ready-made views of the orders waiting on someone.

    None of them holds an order cancelled on its marketplace; those have
    their own warning.
    """

    # paid (or paid later) and still to be made or prepared
    TO_MAKE = "to_make"
    # still waiting, but the buyer has not paid what is due before shipping
    UNPAID = "unpaid"
    # made and packed, waiting for the carrier
    TO_SHIP = "to_ship"
    # in to_make or to_ship with its dispatch deadline passed; overlaps them
    LATE = "late"


class OrderSort(str, enum.Enum):
    NEWEST = "newest"
    OLDEST = "oldest"
    # closest dispatch deadline first; orders without one after all others
    AT_RISK = "at_risk"

# tracking codes after which a parcel needs no more asking about
FINAL_TRACKING_STATUSES = ("DELIVERED", "RETURNED")
TRACKING_HISTORY_DAYS = 60


class OrderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, order: Order) -> Order:
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def get(self, order_id: uuid.UUID) -> Order | None:
        return self.db.query(Order).filter(Order.id == order_id).first()

    def get_by_external_id(
        self, source: OrderSource, external_id: str
    ) -> Order | None:
        """Look an order up the way a marketplace identifies it.

        This is the pair an import matches on, so a re-run updates the
        existing order instead of inserting a second copy.
        """
        return (
            self.db.query(Order)
            .filter(Order.source == source, Order.external_id == external_id)
            .first()
        )

    def update_imported_fields(
        self,
        order: Order,
        customer_email: str,
        total_amount: Decimal,
        currency: str,
        cancelled_on_marketplace: bool = False,
        ordered_at: datetime | None = None,
        marketplace_status: OrderStatus | None = None,
        marketplace_status_label: str | None = None,
    ) -> Order:
        """Refresh the fields a marketplace owns.

        Excludes `status`: whether the marketplace's status moves it is the
        import service's call (it needs the previous `marketplace_status`,
        which this overwrites), and goes through `update_status` so the change
        lands in the history. What the marketplace says goes to
        `marketplace_status` beside it. A cancellation is recorded as well,
        and only the first time it is seen, so the timestamp says when it was
        noticed.
        """
        order.customer_email = customer_email
        order.total_amount = total_amount
        order.currency = currency
        if marketplace_status is not None:
            order.marketplace_status = marketplace_status
            # kept in step with it: a label left from an earlier import would
            # describe a status the order has moved on from
            order.marketplace_status_label = marketplace_status_label
        if ordered_at is not None:
            order.ordered_at = self._to_db_datetime(ordered_at.astimezone(UTC))
        if cancelled_on_marketplace and order.marketplace_cancelled_at is None:
            order.marketplace_cancelled_at = self._to_db_datetime(datetime.now(UTC))
        self.db.commit()
        self.db.refresh(order)
        return order

    def update_status(
        self,
        order: Order,
        status: OrderStatus,
        changed_by_user_id: int | None = None,
    ) -> Order:
        """Move the order to a new status and record the transition.

        The history row and the new status are committed together, so the
        log cannot drift from the order it describes.
        """
        if status == order.status:
            return order

        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=order.status,
                to_status=status,
                changed_by_user_id=changed_by_user_id,
                # set here rather than leaning on the column's server default:
                # SQLite's CURRENT_TIMESTAMP resolves to whole seconds, so two
                # changes in the same second would sort unpredictably
                changed_at=self._to_db_datetime(datetime.now(UTC)),
            )
        )
        order.status = status
        if changed_by_user_id is not None:
            order.status_set_at = self._to_db_datetime(datetime.now(UTC))
        self.db.commit()
        self.db.refresh(order)
        return order

    def record_marketplace_status(
        self, order: Order, status: OrderStatus, label: str | None
    ) -> None:
        """Note what the marketplace now says, after Anvero told it so.

        The next import compares against this, so the change Anvero just
        sent does not look like the marketplace moving on its own.
        """
        order.marketplace_status = status
        order.marketplace_status_label = label
        self.db.commit()

    def add_shipment(
        self,
        order: Order,
        carrier_id: str | None,
        carrier_name: str | None,
        waybill: str,
    ) -> OrderShipment:
        """Add a parcel entered in Anvero, after those already on the order."""
        shipment = OrderShipment(
            order_id=order.id,
            position=len(order.shipments),
            carrier_id=carrier_id,
            carrier_name=carrier_name,
            waybill=waybill,
            shipped_at=self._to_db_datetime(datetime.now(UTC)),
            added_in_anvero=True,
        )
        self.db.add(shipment)
        self.db.commit()
        self.db.refresh(order)
        return shipment

    def set_shipment_external_id(self, shipment: OrderShipment, external_id: str) -> None:
        shipment.external_id = external_id
        self.db.commit()

    def shipments_awaiting_tracking(
        self, source: OrderSource, limit: int = 200
    ) -> list[OrderShipment]:
        """Parcels of orders still marked shipped whose carrier has not said "delivered".

        Newest first, and only those the carrier can still report on (Allegro
        keeps tracking history for 60 days), so a parcel no carrier answers
        for does not use up the batch forever.
        """
        cutoff = datetime.now(UTC) - timedelta(days=TRACKING_HISTORY_DAYS)
        return list(
            self.db.scalars(
                select(OrderShipment)
                .join(Order, Order.id == OrderShipment.order_id)
                .where(
                    Order.source == source,
                    Order.status == OrderStatus.SHIPPED,
                    or_(
                        OrderShipment.tracking_status.is_(None),
                        OrderShipment.tracking_status.notin_(FINAL_TRACKING_STATUSES),
                    ),
                    or_(
                        OrderShipment.shipped_at.is_(None),
                        OrderShipment.shipped_at >= self._to_db_datetime(cutoff),
                    ),
                )
                .order_by(OrderShipment.shipped_at.desc())
                .limit(limit)
            )
        )

    def add_billing_entries(self, entries: list[BillingEntryCreate]) -> int:
        """Store the entries not stored yet; returns how many were new.

        An entry never changes once the marketplace has issued it, so one
        already stored is left alone, and reading an overlapping window twice
        adds nothing.
        """
        added = 0
        for start in range(0, len(entries), 500):
            chunk = entries[start : start + 500]
            known = set(
                self.db.scalars(
                    select(BillingEntry.external_id).where(
                        BillingEntry.source.in_({e.source for e in chunk}),
                        BillingEntry.external_id.in_([e.external_id for e in chunk]),
                    )
                )
            )
            for entry in chunk:
                if entry.external_id in known:
                    continue
                known.add(entry.external_id)
                self.db.add(BillingEntry(**entry.model_dump()))
                added += 1
        self.db.commit()
        return added

    def list_billing_entries(self, order: Order) -> list[BillingEntry]:
        return list(
            self.db.scalars(
                select(BillingEntry)
                .where(
                    BillingEntry.source == order.source,
                    BillingEntry.order_external_id == order.external_id,
                )
                .order_by(BillingEntry.occurred_at, BillingEntry.external_id)
            )
        )

    def update_tracking(
        self, shipment: OrderShipment, status: str, reported_at: datetime | None
    ) -> None:
        shipment.tracking_status = status
        shipment.tracking_updated_at = reported_at
        self.db.commit()

    def list_status_history(self, order_id: uuid.UUID) -> list[OrderStatusHistory]:
        return (
            self.db.query(OrderStatusHistory)
            .filter(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.changed_at.desc())
            .all()
        )

    def _to_db_datetime(self, value: datetime) -> datetime:
        """Match the bind parameter to how the backend stores timestamps.

        SQLite has no timezone-aware type and stores naive UTC, so an aware
        parameter would render with an offset and never compare equal.
        """
        if self.db.get_bind().dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def _day_start(self, day: date) -> datetime:
        """Local midnight of `day` in the business timezone, as stored UTC.

        A filter for 11 September means that calendar day where the business
        is. Using UTC midnight instead moved the boundary to 02:00 in Poland,
        so an order placed at 01:30 counted as the previous day.
        """
        local_midnight = datetime.combine(
            day, time.min, ZoneInfo(settings.business_timezone)
        )
        return self._to_db_datetime(local_midnight.astimezone(UTC))

    @staticmethod
    def _is_unpaid():
        """The buyer owes payment before the order may ship.

        Known unpaid (a paid amount short of the total), or paying up front
        with no payment recorded. An order whose payment is unknown in both
        type and amount, such as one entered by hand, is not called unpaid:
        that would park every such order where nobody looks. Written so it is
        never NULL, since the queues also use it negated.
        """
        pays_up_front = or_(
            Order.payment_type.is_(None), Order.payment_type.notin_(PAY_LATER_TYPES)
        )
        short = and_(Order.paid_amount.is_not(None), Order.paid_amount < Order.total_amount)
        nothing_recorded = and_(Order.paid_amount.is_(None), Order.payment_type.is_not(None))
        return and_(pays_up_front, or_(short, nothing_recorded))

    def _in_queue(self, queue: OrderQueue):
        """One definition per queue, shared by the list filter and the counts."""
        if queue is OrderQueue.LATE:
            return self._is_late()
        not_cancelled = Order.marketplace_cancelled_at.is_(None)
        if queue is OrderQueue.UNPAID:
            return and_(not_cancelled, Order.status.in_(PENDING_STATUSES), self._is_unpaid())
        statuses = TO_MAKE_STATUSES if queue is OrderQueue.TO_MAKE else TO_SHIP_STATUSES
        return and_(not_cancelled, Order.status.in_(statuses), not_(self._is_unpaid()))

    def _is_late(self):
        """In a queue that still needs work, past the dispatch deadline."""
        return and_(
            or_(self._in_queue(OrderQueue.TO_MAKE), self._in_queue(OrderQueue.TO_SHIP)),
            Order.dispatch_by < self._to_db_datetime(datetime.now(UTC)),
        )

    @staticmethod
    def _has_cancellation_warning():
        """Cancelled on the marketplace, but not (yet) cancelled in Anvero.

        One definition, shared by the list filter and the statistics, so the
        dashboard count always matches what the filtered list shows.
        """
        return (Order.marketplace_cancelled_at.is_not(None)) & (
            Order.status != OrderStatus.CANCELLED
        )

    def _filtered(
        self,
        source: OrderSource | None = None,
        status: OrderStatus | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cancellation_warning: bool = False,
        queue: OrderQueue | None = None,
    ) -> Query:
        """Single source of truth for filtering.

        list() and count() must apply identical predicates, otherwise a page
        of results and its reported total disagree.
        """
        query = self.db.query(Order)
        if queue is not None:
            query = query.filter(self._in_queue(queue))
        if cancellation_warning:
            query = query.filter(self._has_cancellation_warning())
        if source is not None:
            query = query.filter(Order.source == source)
        if status is not None:
            query = query.filter(Order.status == status)
        if date_from is not None:
            query = query.filter(Order.ordered_at >= self._day_start(date_from))
        if date_to is not None:
            # exclusive upper bound on the next day, so date_to itself is
            # fully included rather than cut off at midnight
            query = query.filter(
                Order.ordered_at < self._day_start(date_to + timedelta(days=1))
            )
        if search:
            # escape LIKE wildcards so a literal % typed by a user does not
            # silently match every row
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"

            def like(column):
                return column.ilike(pattern, escape="\\")

            full_name = Order.customer_first_name.concat(" ").concat(Order.customer_last_name)
            matches = [
                like(Order.external_id),
                like(Order.customer_email),
                # the buyer, however the operator remembers them
                like(Order.customer_login),
                like(full_name),
                like(Order.customer_last_name),
                like(Order.customer_company_name),
                like(Order.customer_phone),
                like(Order.pickup_point_id),
                like(Order.pickup_point_name),
                # EXISTS rather than joins, so an order matching on two of
                # its items or addresses is still one row, and counts once
                exists().where(
                    OrderItem.order_id == Order.id,
                    or_(like(OrderItem.sku), like(OrderItem.name)),
                ),
                exists().where(OrderAddress.order_id == Order.id, like(OrderAddress.city)),
                exists().where(OrderShipment.order_id == Order.id, like(OrderShipment.waybill)),
            ]
            # "AN-000123", "000123" and "123" all name order 123
            number = parse_order_number(search)
            if number is not None:
                matches.append(Order.order_number == number)
            query = query.filter(or_(*matches))
        return query

    def list(
        self,
        skip: int = 0,
        limit: int = 100,
        source: OrderSource | None = None,
        status: OrderStatus | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cancellation_warning: bool = False,
        queue: OrderQueue | None = None,
        sort: OrderSort = OrderSort.NEWEST,
    ) -> list[Order]:
        return (
            self._filtered(
                source=source,
                status=status,
                search=search,
                date_from=date_from,
                date_to=date_to,
                cancellation_warning=cancellation_warning,
                queue=queue,
            )
            .order_by(*self._ordering(sort))
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(
        self,
        source: OrderSource | None = None,
        status: OrderStatus | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cancellation_warning: bool = False,
        queue: OrderQueue | None = None,
    ) -> int:
        return self._filtered(
            source=source,
            status=status,
            search=search,
            date_from=date_from,
            date_to=date_to,
            cancellation_warning=cancellation_warning,
            queue=queue,
        ).count()

    @staticmethod
    def _ordering(sort: OrderSort) -> tuple:
        # created_at and id break ties: many orders share an ordered_at at
        # the database's timestamp resolution, and without a total order
        # offset pagination could repeat or skip rows between pages
        if sort is OrderSort.OLDEST:
            return (Order.ordered_at.asc(), Order.created_at.asc(), Order.id)
        if sort is OrderSort.AT_RISK:
            # "IS NULL" sorts false before true on both databases, which puts
            # orders without a deadline last without NULLS LAST syntax
            return (
                Order.dispatch_by.is_(None),
                Order.dispatch_by.asc(),
                Order.ordered_at.asc(),
                Order.id,
            )
        return (Order.ordered_at.desc(), Order.created_at.desc(), Order.id)

    def list_buyer_orders(self, order: Order, limit: int = 20) -> list[Order]:
        """The same buyer's other orders, newest first.

        The same buyer is the same email, or the same marketplace login on
        the same marketplace (a login is only unique within one). An order
        with neither to go on has no others.
        """
        same_buyer = [Order.customer_email == order.customer_email]
        if order.customer_login:
            same_buyer.append(
                and_(Order.source == order.source, Order.customer_login == order.customer_login)
            )
        return list(
            self.db.scalars(
                select(Order)
                .where(Order.id != order.id, or_(*same_buyer))
                .order_by(*self._ordering(OrderSort.NEWEST))
                .limit(limit)
            )
        )

    def list_in_queue_with_items(self, queue: OrderQueue) -> list[Order]:
        """Every order in a queue, with its items, most urgent first.

        Unpaged: a queue is the day's work, tens of orders, not the history.
        """
        return list(
            self.db.scalars(
                select(Order)
                .where(self._in_queue(queue))
                .options(selectinload(Order.items))
                .order_by(*self._ordering(OrderSort.AT_RISK))
            )
        )

    def _week_cutoff(self) -> datetime:
        return self._to_db_datetime(datetime.now(UTC) - timedelta(days=7))

    def stats(self) -> dict:
        """Aggregate order figures across the whole table.

        Computed in SQL rather than by summing a fetched page, so the numbers
        stay correct once the table outgrows one page.
        """
        total, revenue = self.db.execute(
            select(func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
        ).one()

        this_week = self.db.execute(
            select(func.count(Order.id)).where(Order.ordered_at >= self._week_cutoff())
        ).scalar_one()

        pending = self.db.execute(
            select(func.count(Order.id)).where(Order.status.in_(PENDING_STATUSES))
        ).scalar_one()

        cancellation_warnings = self.db.execute(
            select(func.count(Order.id)).where(self._has_cancellation_warning())
        ).scalar_one()

        queues = {
            queue.value: self.db.execute(
                select(func.count(Order.id)).where(self._in_queue(queue))
            ).scalar_one()
            for queue in OrderQueue
        }

        by_status = self.db.execute(
            select(Order.status, func.count(Order.id)).group_by(Order.status)
        ).all()

        by_source = self.db.execute(
            select(Order.source, func.count(Order.id)).group_by(Order.source)
        ).all()

        return {
            "total_orders": total,
            "total_revenue": Decimal(revenue),
            "this_week": this_week,
            "pending": pending,
            "cancellation_warnings": cancellation_warnings,
            "queues": queues,
            "by_status": {status.value: count for status, count in by_status},
            "by_source": {source.value: count for source, count in by_source},
        }
