import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Query, Session

from app.models.order import Order, OrderSource, OrderStatus, OrderStatusHistory

PENDING_STATUSES = (OrderStatus.NEW, OrderStatus.CONFIRMED)


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
    ) -> Order:
        """Refresh the fields a marketplace owns.

        Deliberately excludes status: that one belongs to the operator, and a
        sync overwriting it would undo a decision recorded in the history. A
        marketplace cancellation is recorded beside it instead, and only the
        first time it is seen, so the timestamp says when it was noticed.
        """
        order.customer_email = customer_email
        order.total_amount = total_amount
        order.currency = currency
        if cancelled_on_marketplace and order.marketplace_cancelled_at is None:
            order.marketplace_cancelled_at = self._to_db_datetime(datetime.now(UTC))
        self.db.commit()
        self.db.refresh(order)
        return order

    def update_status(self, order: Order, status: OrderStatus) -> Order:
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
                # set here rather than leaning on the column's server default:
                # SQLite's CURRENT_TIMESTAMP resolves to whole seconds, so two
                # changes in the same second would sort unpredictably
                changed_at=self._to_db_datetime(datetime.now(UTC)),
            )
        )
        order.status = status
        self.db.commit()
        self.db.refresh(order)
        return order

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
    ) -> Query:
        """Single source of truth for filtering.

        list() and count() must apply identical predicates, otherwise a page
        of results and its reported total disagree.
        """
        query = self.db.query(Order)
        if cancellation_warning:
            query = query.filter(self._has_cancellation_warning())
        if source is not None:
            query = query.filter(Order.source == source)
        if status is not None:
            query = query.filter(Order.status == status)
        if date_from is not None:
            query = query.filter(
                Order.created_at
                >= self._to_db_datetime(datetime.combine(date_from, time.min, UTC))
            )
        if date_to is not None:
            # exclusive upper bound on the next day, so date_to itself is
            # fully included rather than cut off at midnight
            query = query.filter(
                Order.created_at
                < self._to_db_datetime(
                    datetime.combine(date_to + timedelta(days=1), time.min, UTC)
                )
            )
        if search:
            # escape LIKE wildcards so a literal % typed by a user does not
            # silently match every row
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            query = query.filter(
                or_(
                    Order.external_id.ilike(pattern, escape="\\"),
                    Order.customer_email.ilike(pattern, escape="\\"),
                )
            )
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
    ) -> list[Order]:
        return (
            self._filtered(
                source=source,
                status=status,
                search=search,
                date_from=date_from,
                date_to=date_to,
                cancellation_warning=cancellation_warning,
            )
            .order_by(Order.created_at.desc())
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
    ) -> int:
        return self._filtered(
            source=source,
            status=status,
            search=search,
            date_from=date_from,
            date_to=date_to,
            cancellation_warning=cancellation_warning,
        ).count()

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
            select(func.count(Order.id)).where(Order.created_at >= self._week_cutoff())
        ).scalar_one()

        pending = self.db.execute(
            select(func.count(Order.id)).where(Order.status.in_(PENDING_STATUSES))
        ).scalar_one()

        cancellation_warnings = self.db.execute(
            select(func.count(Order.id)).where(self._has_cancellation_warning())
        ).scalar_one()

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
            "by_status": {status.value: count for status, count in by_status},
            "by_source": {source.value: count for source, count in by_source},
        }
