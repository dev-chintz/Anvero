"""Erasing buyers' personal data once it has no purpose left (GDPR, `docs/GDPR.md`).

Nothing is deleted: a row keeps its number, dates, amounts and items, so figures
and reports over past years still add up, while the fields that name, reach or
quote a person are emptied and `anonymized_at` is set. An import or sync no
longer touches an anonymized order or case, so the marketplace cannot bring the
data back; a message thread is the exception, since new activity from the buyer
is a new contact, and the retention rule then counts again from it.

The periods, decided by the owner on 2026-09-28 (`DECISIONS.md`):

- An order is kept whole for five years after the end of the year in which the
  tax on it was due. Income tax for a year is settled in the next one, so an
  order placed in 2020 is kept through 2026 and anonymized from 1 January 2027.
- A row of the non-invoiced sales record keeps its buyer copy for the same five
  years, counted from the row's own date (a sale's payment), and only
  retention erases it: a buyer's own request leaves it (`docs/GDPR.md`).
- A message thread is kept two years after its last message; an after-sales
  case two years after it was opened, once it is closed; what Anvero sent to a
  marketplace (a label's recipient, a reply's text) two years after it was sent.

`apply_retention` runs once a day by itself (`run_retention_daily`), and by hand
with `scripts/apply_retention.py`. `anonymize_order` and the others are also what
answering one buyer's request for erasure uses (`scripts/anonymize_person.py`).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.after_sales import AfterSalesCase
from app.models.inpost_shipment import InpostShipment
from app.models.marketplace_write import AppSetting, MarketplaceWrite
from app.models.message import MessageThread
from app.models.non_invoiced import LedgerEntry
from app.models.order import AddressType, Order, OrderAddress
from app.models.sales_report import SalesReportOverride
from app.models.shipping_label import ShippingLabel
from app.repositories.non_invoiced_repository import NonInvoicedRepository

logger = logging.getLogger(__name__)

ORDER_RETENTION_YEARS = 5
CONTACT_RETENTION_YEARS = 2

# what an emptied marketplace write's payload reads
ANONYMIZED_PAYLOAD = "{}"

LAST_RUN_KEY = "retention_last_run"
# how often the daily loop looks at the calendar
CHECK_SECONDS = 3600


@dataclass
class RetentionResult:
    orders: int = 0
    threads: int = 0
    cases: int = 0
    writes: int = 0
    # rows of the non-invoiced sales record whose buyer copy was erased
    ledger_entries: int = 0

    @property
    def total(self) -> int:
        return self.orders + self.threads + self.cases + self.writes + self.ledger_entries


def order_cutoff(now: datetime) -> datetime:
    """Orders placed before this moment (UTC) are anonymized: 1 January, in the
    business's own time zone, of the year after the last one whose tax period
    has run its five years."""
    zone = ZoneInfo(settings.business_timezone)
    year = now.astimezone(zone).year - ORDER_RETENTION_YEARS - 1
    return datetime(year, 1, 1, tzinfo=zone).astimezone(UTC)


def contact_cutoff(now: datetime) -> datetime:
    """Threads, cases and writes older than this (UTC) are anonymized."""
    now = now.astimezone(UTC)
    try:
        return now.replace(year=now.year - CONTACT_RETENTION_YEARS)
    except ValueError:
        # 29 February, two years on
        return now.replace(year=now.year - CONTACT_RETENTION_YEARS, day=28)


def _db_datetime(db: Session, value: datetime) -> datetime:
    # SQLite stores naive UTC, and an aware parameter would never compare equal
    if db.get_bind().dialect.name == "sqlite":
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _keeps_invoice(address: OrderAddress) -> bool:
    return address.type is AddressType.INVOICE and address.tax_id is not None


def anonymize_order(db: Session, order: Order, now: datetime, keep_invoice: bool = False) -> None:
    """Empty every field of the order that names, reaches or quotes the buyer.

    Kept: the numbers, dates, status, amounts, items, payment and delivery
    method, the pickup point (a public place), the delivery country and the
    tracking numbers. With `keep_invoice` (a buyer's own request, while the tax
    period still runs), a company invoice address keeps the company's name, tax
    id and address; the retention rule erases those too once the period is over.
    Staged on the session; the caller commits.
    """
    # required by the schema, so emptied rather than nulled
    order.customer_email = ""
    order.customer_login = None
    order.customer_first_name = None
    order.customer_last_name = None
    order.customer_company_name = None
    order.customer_phone = None
    order.buyer_message = None
    order.seller_note = None
    # the operator's own words may name or quote the buyer as well
    order.internal_note = None
    for address in order.addresses:
        address.first_name = None
        address.last_name = None
        address.phone = None
        if keep_invoice and _keeps_invoice(address):
            continue
        address.company_name = None
        address.street = None
        address.postal_code = None
        address.city = None
        address.tax_id = None
    for label in db.scalars(select(ShippingLabel).where(ShippingLabel.order_id == order.id)):
        # a carrier's refusal can quote the recipient's address back
        label.error = None
    for shipment in db.scalars(select(InpostShipment).where(InpostShipment.order_id == order.id)):
        shipment.error = None
        shipment.reference = None
    override = db.scalar(
        select(SalesReportOverride).where(
            SalesReportOverride.source == order.source,
            SalesReportOverride.order_external_id == order.external_id,
        )
    )
    if override is not None:
        override.note = None
    for write in db.scalars(
        select(MarketplaceWrite).where(
            MarketplaceWrite.order_id == order.id, MarketplaceWrite.anonymized_at.is_(None)
        )
    ):
        anonymize_write(write, now)
    order.anonymized_at = now


def anonymize_thread(thread: MessageThread, now: datetime) -> None:
    """Empty the buyer's login and every message's text; the thread, its dates
    and the order it names stay."""
    thread.interlocutor_login = None
    thread.last_message_text = None
    for message in thread.messages:
        message.author_login = None
        message.text = ""
    thread.anonymized_at = now


def anonymize_case(case: AfterSalesCase, now: datetime) -> None:
    case.buyer_login = None
    case.buyer_email = None
    case.summary = None
    case.detail = None
    case.anonymized_at = now


def anonymize_write(write: MarketplaceWrite, now: datetime) -> None:
    write.payload = ANONYMIZED_PAYLOAD
    write.detail = None
    write.anonymized_at = now


def anonymize_ledger_entry(entry: LedgerEntry, now: datetime) -> None:
    """Empty the buyer copy of a row of the non-invoiced sales record; the amount, date, order,
    payment trace and classification stay, so past totals still add up. Only retention does this: a
    buyer's own request leaves the copy, which is a tax record the law requires kept (GDPR art.
    17(3)(b), `docs/GDPR.md`). An override's note may name the buyer too."""
    entry.buyer_first_name = None
    entry.buyer_last_name = None
    entry.buyer_street = None
    entry.buyer_postal_code = None
    entry.buyer_city = None
    entry.override_note = None
    entry.anonymized_at = now


def apply_retention(
    db: Session, now: datetime | None = None, dry_run: bool = False
) -> RetentionResult:
    """Anonymize whatever is past its retention period; with `dry_run`, only
    count it. Running it again finds nothing new."""
    now = now or datetime.now(UTC)
    orders_before = _db_datetime(db, order_cutoff(now))
    contact_before = _db_datetime(db, contact_cutoff(now))

    due_orders = (
        Order.ordered_at < orders_before,
        or_(
            Order.anonymized_at.is_(None),
            # erased at the buyer's request, the invoice kept for the tax period
            Order.addresses.any(OrderAddress.tax_id.is_not(None)),
        ),
    )
    orders = db.scalars(select(Order).where(*due_orders)).all()
    threads = db.scalars(
        select(MessageThread).where(
            MessageThread.anonymized_at.is_(None),
            or_(
                MessageThread.last_message_at < contact_before,
                # a thread with no message date is judged by when it was stored
                MessageThread.last_message_at.is_(None)
                & (MessageThread.created_at < contact_before),
            ),
        )
    ).all()
    cases = db.scalars(
        select(AfterSalesCase).where(
            AfterSalesCase.anonymized_at.is_(None),
            AfterSalesCase.is_open.is_(False),
            AfterSalesCase.opened_at < contact_before,
        )
    ).all()
    # old enough on their own, or carried along by an order that is
    writes = db.scalars(
        select(MarketplaceWrite).where(
            MarketplaceWrite.anonymized_at.is_(None),
            or_(
                MarketplaceWrite.created_at < contact_before,
                MarketplaceWrite.order_id.in_(select(Order.id).where(*due_orders)),
            ),
        )
    ).all()

    # the record's rows by their own date (a sale's is its payment's), with the orders' period:
    # five years after the end of the year the tax was due
    ledger_entries = NonInvoicedRepository(db).entries_with_buyer_before(order_cutoff(now))

    result = RetentionResult(len(orders), len(threads), len(cases), len(writes), len(ledger_entries))
    if dry_run:
        return result

    for order in orders:
        anonymize_order(db, order, now)
    for thread in threads:
        anonymize_thread(thread, now)
    for case in cases:
        anonymize_case(case, now)
    for write in writes:
        # an order's own writes may have been emptied with it just above
        if write.anonymized_at is None:
            anonymize_write(write, now)
    for entry in ledger_entries:
        anonymize_ledger_entry(entry, now)
    db.commit()
    if result.total:
        logger.info(
            "Retention: anonymized %d orders, %d message threads, %d after-sales cases, "
            "%d marketplace writes, %d non-invoiced ledger rows",
            result.orders,
            result.threads,
            result.cases,
            result.writes,
            result.ledger_entries,
        )
    return result


def _run_if_not_run_today(now: datetime) -> RetentionResult | None:
    """Apply retention unless it already ran today (in the business's time
    zone), by this backend or another sharing the database. Never raises."""
    db = SessionLocal()
    try:
        today = now.astimezone(ZoneInfo(settings.business_timezone)).date().isoformat()
        row = db.get(AppSetting, LAST_RUN_KEY)
        if row is not None and row.value == today:
            return None
        result = apply_retention(db, now)
        if row is None:
            row = AppSetting(key=LAST_RUN_KEY)
            db.add(row)
        row.value = today
        db.commit()
        return result
    except Exception:
        db.rollback()
        logger.exception("Retention could not be applied; trying again within the hour")
        return None
    finally:
        db.close()


async def run_retention_daily(
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Apply retention once a day, until cancelled. Separate from the import
    schedule on purpose: switching imports off must not stop data from ageing
    out. Anonymizing twice is harmless, so backends sharing a database need no
    lease here."""
    while True:
        await asyncio.to_thread(_run_if_not_run_today, clock())
        await sleep(CHECK_SECONDS)
