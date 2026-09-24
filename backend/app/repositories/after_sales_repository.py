import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import String, cast, func, select, true
from sqlalchemy.orm import Session

from app.models.after_sales import AfterSalesCase, CaseAction, CaseKind
from app.models.order import Order, OrderSource
from app.schemas.after_sales import AfterSalesSummary, SyncedCase
from app.schemas.types import _as_utc

# a deadline this close is "soon"
DUE_SOON = timedelta(days=3)


class CaseView(str, enum.Enum):
    # what waits for the seller, the closest deadline first
    ACTION = "action"
    # everything still going on, whether or not it waits for the seller
    OPEN = "open"
    ALL = "all"


class AfterSalesRepository:
    def __init__(self, db: Session):
        self.db = db

    def _to_db_datetime(self, value: datetime) -> datetime:
        """Match the bind parameter to how the backend stores timestamps.

        SQLite has no timezone-aware type and stores naive UTC, so an aware
        parameter would render with an offset and never compare equal.
        """
        if self.db.get_bind().dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def get_by_external_id(self, source: OrderSource, external_id: str) -> AfterSalesCase | None:
        return self.db.scalar(
            select(AfterSalesCase).where(
                AfterSalesCase.source == source, AfterSalesCase.external_id == external_id
            )
        )

    def upsert(
        self,
        source: OrderSource,
        data: SyncedCase,
        action: CaseAction,
        due_at: datetime | None,
    ) -> bool:
        """Store one case, replacing what was stored; True if it is new.

        The marketplace owns every field, so nothing is merged. Committed by
        the caller once the whole sync is read.
        """
        case = self.get_by_external_id(source, data.external_id)
        created = case is None
        if case is None:
            case = AfterSalesCase(source=source, external_id=data.external_id)
            self.db.add(case)
        case.kind = data.kind
        case.status = data.status
        case.is_open = data.is_open
        case.action = action
        case.due_at = self._to_db_datetime(due_at) if due_at else None
        case.reference_number = data.reference_number
        case.order_external_id = data.order_external_id
        case.buyer_login = data.buyer_login
        case.buyer_email = data.buyer_email
        case.opened_at = self._to_db_datetime(data.opened_at)
        case.reason = data.reason
        case.summary = data.summary
        case.detail = data.detail
        return created

    def close_issues_not_in(self, source: OrderSource, seen_ids: set[str]) -> int:
        """Close the disputes and claims stored as open that Allegro no longer
        lists as open, and say so: the seller has nothing left to do on them.

        Every open one is read on every sync however old, so one missing from
        that read has been closed (or removed) since.
        """
        self.db.flush()
        stale = self.db.scalars(
            select(AfterSalesCase).where(
                AfterSalesCase.source == source,
                AfterSalesCase.kind.in_([CaseKind.CLAIM, CaseKind.DISPUTE]),
                AfterSalesCase.is_open.is_(True),
                AfterSalesCase.external_id.not_in(seen_ids) if seen_ids else true(),
            )
        ).all()
        for case in stale:
            case.is_open = False
            case.action = CaseAction.NONE
            case.due_at = None
        return len(stale)

    def oldest_open_return(self, source: OrderSource) -> datetime | None:
        """When the oldest return still open here was made, so a sync reaches
        back far enough to see how it ended."""
        opened = self.db.scalar(
            select(func.min(AfterSalesCase.opened_at)).where(
                AfterSalesCase.source == source,
                AfterSalesCase.kind == CaseKind.RETURN,
                AfterSalesCase.is_open.is_(True),
            )
        )
        return _as_utc(opened) if opened else None

    def commit(self) -> None:
        self.db.commit()

    def _query(self):
        """A case with the Anvero order it belongs to, when there is one.

        `orders.source` is a native PostgreSQL enum and this table's is plain
        text, which PostgreSQL will not compare, hence the casts.
        """
        return select(AfterSalesCase, Order.id, Order.order_number).outerjoin(
            Order,
            (Order.external_id == AfterSalesCase.order_external_id)
            & (cast(Order.source, String) == cast(AfterSalesCase.source, String)),
        )

    def list(
        self,
        view: CaseView = CaseView.ACTION,
        kind: CaseKind | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[tuple[AfterSalesCase, uuid.UUID | None, int | None]], int]:
        """Cases with their order, and how many there are in all.

        `action` puts the closest deadline first (a case with none after
        those with one); the other views show the newest opened first.
        """
        query = self._query()
        if view is CaseView.ACTION:
            # by `action`, not `is_open`: a refunded return is closed, yet its
            # commission can still be claimed back
            query = query.where(AfterSalesCase.action != CaseAction.NONE).order_by(
                AfterSalesCase.due_at.is_(None), AfterSalesCase.due_at, AfterSalesCase.opened_at
            )
        else:
            if view is CaseView.OPEN:
                query = query.where(AfterSalesCase.is_open.is_(True))
            query = query.order_by(AfterSalesCase.opened_at.desc())
        if kind is not None:
            query = query.where(AfterSalesCase.kind == kind)
        total = self.db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        rows = self.db.execute(query.limit(limit).offset(offset)).all()
        return [(case, order_id, number) for case, order_id, number in rows], total or 0

    def for_order(
        self, source: OrderSource, external_id: str
    ) -> list[tuple[AfterSalesCase, uuid.UUID | None, int | None]]:
        rows = self.db.execute(
            self._query()
            .where(
                AfterSalesCase.source == source,
                AfterSalesCase.order_external_id == external_id,
            )
            .order_by(AfterSalesCase.opened_at.desc())
        ).all()
        return [(case, order_id, number) for case, order_id, number in rows]

    def summary(self, now: datetime) -> AfterSalesSummary:
        waiting = [AfterSalesCase.action != CaseAction.NONE]
        db_now = self._to_db_datetime(now)
        needs_action = self.db.scalar(select(func.count()).select_from(AfterSalesCase).where(*waiting)) or 0
        overdue = (
            self.db.scalar(
                select(func.count())
                .select_from(AfterSalesCase)
                .where(*waiting, AfterSalesCase.due_at < db_now)
            )
            or 0
        )
        due_soon = (
            self.db.scalar(
                select(func.count())
                .select_from(AfterSalesCase)
                .where(
                    *waiting,
                    AfterSalesCase.due_at >= db_now,
                    AfterSalesCase.due_at <= self._to_db_datetime(now + DUE_SOON),
                )
            )
            or 0
        )
        return AfterSalesSummary(needs_action=needs_action, overdue=overdue, due_soon=due_soon)
