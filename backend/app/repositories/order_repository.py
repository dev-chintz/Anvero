import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Query, Session

from app.models.order import Order, OrderSource, OrderStatus

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

    def update_status(self, order: Order, status: OrderStatus) -> Order:
        order.status = status
        self.db.commit()
        self.db.refresh(order)
        return order

    def _to_db_datetime(self, value: datetime) -> datetime:
        """Match the bind parameter to how the backend stores timestamps.

        SQLite has no timezone-aware type and stores naive UTC, so an aware
        parameter would render with an offset and never compare equal.
        """
        if self.db.get_bind().dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def _filtered(
        self,
        source: OrderSource | None = None,
        status: OrderStatus | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Query:
        """Single source of truth for filtering.

        list() and count() must apply identical predicates, otherwise a page
        of results and its reported total disagree.
        """
        query = self.db.query(Order)
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
    ) -> list[Order]:
        return (
            self._filtered(
                source=source,
                status=status,
                search=search,
                date_from=date_from,
                date_to=date_to,
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
    ) -> int:
        return self._filtered(
            source=source,
            status=status,
            search=search,
            date_from=date_from,
            date_to=date_to,
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
            "by_status": {status.value: count for status, count in by_status},
            "by_source": {source.value: count for source, count in by_source},
        }
