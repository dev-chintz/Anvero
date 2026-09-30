"""The database side of the non-invoiced sales record (docs/NON_INVOICED_SALES.md): what the
ledger's writer (app/services/non_invoiced/ledger.py) reads and writes, and the product flag."""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.non_invoiced import LedgerEntry, LedgerKind, ProductSetting
from app.models.order import Order, OrderPayment, OrderSource, PaymentOperation

# the payment operation types a payout is (INTEGRATIONS.md, "Payouts")
PAYOUT = "PAYOUT"
PAYOUT_CANCEL = "PAYOUT_CANCEL"
# the group Allegro puts money returned to a buyer in
REFUND_GROUP = "REFUND"

CHUNK = 500


def _chunks(values: Iterable[str]) -> Iterable[list[str]]:
    values = sorted(set(values))
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


class NonInvoicedRepository:
    def __init__(self, db: Session):
        self.db = db

    def _db_datetime(self, value: datetime) -> datetime:
        # SQLite keeps naive UTC, and an aware bound would never compare equal
        if self.db.get_bind().dialect.name == "sqlite":
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    # --- the product flag (§ 4) ---------------------------------------------------------------

    def excluded_offer_ids(self, source: OrderSource) -> frozenset[str]:
        """The offers of `source` flagged as goods that can never use the exemption."""
        return frozenset(
            self.db.scalars(
                select(ProductSetting.offer_id).where(
                    ProductSetting.source == source, ProductSetting.excluded_from_exemption.is_(True)
                )
            )
        )

    def set_excluded_from_exemption(
        self, source: OrderSource, offer_id: str, excluded: bool, user_id: int | None = None
    ) -> ProductSetting:
        setting = self.db.scalar(
            select(ProductSetting).where(ProductSetting.source == source, ProductSetting.offer_id == offer_id)
        )
        if setting is None:
            setting = ProductSetting(source=source, offer_id=offer_id)
            self.db.add(setting)
        setting.excluded_from_exemption = excluded
        setting.updated_by_user_id = user_id
        self.db.commit()
        return setting

    # --- what the writer reads ------------------------------------------------------------------

    def orders_paid_since(self, source: OrderSource, since: datetime) -> list[Order]:
        """The orders of `source` whose main payment or a surcharge was paid since `since`, with
        what the classifier needs loaded; oldest payment first. Deleted orders are left out, as
        the classifier's run leaves them out (app/services/non_invoiced/run.py)."""
        since = self._db_datetime(since)
        surcharged = select(OrderPayment.order_id).where(OrderPayment.paid_at >= since)
        return list(
            self.db.scalars(
                select(Order)
                .where(
                    Order.source == source,
                    Order.deleted_at.is_(None),
                    or_(Order.paid_at >= since, Order.id.in_(surcharged)),
                )
                .options(selectinload(Order.addresses), selectinload(Order.items), selectinload(Order.extra_payments))
                .order_by(Order.paid_at, Order.order_number)
            )
        )

    def orders_by_id(self, ids: Iterable[uuid.UUID]) -> list[Order]:
        ids = list(set(ids))
        if not ids:
            return []
        return list(
            self.db.scalars(
                select(Order)
                .where(Order.id.in_(ids))
                .options(selectinload(Order.addresses), selectinload(Order.items), selectinload(Order.extra_payments))
                .order_by(Order.order_number)
            )
        )

    def operations_naming(self, source: OrderSource, ids: Iterable[str]) -> dict[str, list[PaymentOperation]]:
        """The payment operations naming any of these payment or surcharge ids, by the id."""
        found: dict[str, list[PaymentOperation]] = {}
        for chunk in _chunks(ids):
            for operation in self.db.scalars(
                select(PaymentOperation)
                .where(
                    PaymentOperation.source == source,
                    or_(PaymentOperation.payment_id.in_(chunk), PaymentOperation.surcharge_id.in_(chunk)),
                )
                .order_by(PaymentOperation.occurred_at)
            ):
                for key in {operation.payment_id, operation.surcharge_id} - {None}:
                    found.setdefault(key, []).append(operation)
        return found

    def payout_operations_since(self, source: OrderSource, since: datetime) -> list[PaymentOperation]:
        """The payouts and their cancellings since `since`, oldest first."""
        return list(
            self.db.scalars(
                select(PaymentOperation)
                .where(
                    PaymentOperation.source == source,
                    PaymentOperation.type.in_((PAYOUT, PAYOUT_CANCEL)),
                    PaymentOperation.occurred_at >= self._db_datetime(since),
                )
                .order_by(PaymentOperation.occurred_at)
            )
        )

    def refund_operations_since(self, source: OrderSource, since: datetime) -> list[PaymentOperation]:
        """The operations of the REFUND group since `since` that name a payment, oldest first."""
        return list(
            self.db.scalars(
                select(PaymentOperation)
                .where(
                    PaymentOperation.source == source,
                    PaymentOperation.group == REFUND_GROUP,
                    PaymentOperation.payment_id.is_not(None),
                    PaymentOperation.occurred_at >= self._db_datetime(since),
                )
                .order_by(PaymentOperation.occurred_at)
            )
        )

    # --- the ledger -----------------------------------------------------------------------------

    def entries_by_key(self, source: OrderSource, keys: Iterable[str]) -> dict[str, LedgerEntry]:
        found: dict[str, LedgerEntry] = {}
        for chunk in _chunks(keys):
            for entry in self.db.scalars(
                select(LedgerEntry).where(LedgerEntry.source == source, LedgerEntry.event_key.in_(chunk))
            ):
                found[entry.event_key] = entry
        return found

    def sales_by_payment_id(self, source: OrderSource, payment_ids: Iterable[str]) -> dict[str, LedgerEntry]:
        """The SALE rows carrying these payment (or surcharge) ids, by the id."""
        found: dict[str, LedgerEntry] = {}
        for chunk in _chunks(payment_ids):
            for entry in self.db.scalars(
                select(LedgerEntry).where(
                    LedgerEntry.source == source,
                    LedgerEntry.kind == LedgerKind.SALE,
                    LedgerEntry.payment_id.in_(chunk),
                )
            ):
                found.setdefault(entry.payment_id, entry)
        return found

    def corrections_of(self, sale_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, list[LedgerEntry]]:
        """Every correction of these sales, by the sale; in the order they were written."""
        found: dict[uuid.UUID, list[LedgerEntry]] = {}
        ids = list(set(sale_ids))
        for start in range(0, len(ids), CHUNK):
            for entry in self.db.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.corrects_entry_id.in_(ids[start : start + CHUNK]))
                .order_by(LedgerEntry.created_at, LedgerEntry.event_key)
            ):
                found.setdefault(entry.corrects_entry_id, []).append(entry)
        return found

    def get(self, entry_id: uuid.UUID) -> LedgerEntry | None:
        return self.db.get(LedgerEntry, entry_id)

    def add(self, entry: LedgerEntry) -> LedgerEntry:
        """Stage a new row; the writer commits once at the end."""
        self.db.add(entry)
        self.db.flush()
        return entry

    def lock(self, entry_ids: Iterable[uuid.UUID], at: datetime) -> int:
        """Lock the rows a report handed over to the accountant held; a row already locked keeps
        its first lock. Returns how many were locked now. Commits."""
        ids = list(set(entry_ids))
        locked = 0
        for start in range(0, len(ids), CHUNK):
            result = self.db.execute(
                update(LedgerEntry)
                .where(LedgerEntry.id.in_(ids[start : start + CHUNK]), LedgerEntry.locked_at.is_(None))
                .values(locked_at=at.astimezone(UTC))
                .execution_options(synchronize_session="fetch")
            )
            locked += result.rowcount or 0
        self.db.commit()
        return locked

    def entries_with_buyer_before(self, before: datetime) -> list[LedgerEntry]:
        """The rows dated before `before` whose buyer fields retention has not erased yet."""
        return list(
            self.db.scalars(
                select(LedgerEntry).where(
                    LedgerEntry.entry_at < self._db_datetime(before), LedgerEntry.anonymized_at.is_(None)
                )
            )
        )

    def entries_of_orders(self, order_ids: Iterable[uuid.UUID]) -> list[LedgerEntry]:
        ids = list(set(order_ids))
        if not ids:
            return []
        return list(
            self.db.scalars(
                select(LedgerEntry).where(LedgerEntry.order_id.in_(ids)).order_by(LedgerEntry.entry_at)
            )
        )
