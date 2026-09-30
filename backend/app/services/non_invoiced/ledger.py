"""The ledger of the non-invoiced sales record (docs/NON_INVOICED_SALES.md, sections 4b, 4c and 4d,
stage 3 of the plan): one row per money event, written after every import.

`write_ledger` goes through the orders paid since a given moment (the import passes the start of
the previous month) and the refunds since then:

- a paid order without a row gets one: a SALE for its main payment, dated the payment's time, and
  one for each surcharge paid, dated that surcharge's; classified by the stage 2 classifier;
- a SALE row not locked is classified again, and only its classification (and the trace of its
  money, which can only be completed later) follows the order, never the amount, date or buyer;
- a refund's operation naming a sale's payment becomes a CORRECTION of that sale, dated when the
  money went back; its category follows the sale's, so a report only carries corrections of the
  sales it carries;
- a sale whose place in the report changes after a report holding it (or one of its corrections)
  was handed over is not changed: a CORRECTION dated now moves its money in or out (4c).

What decides is kept in small pure functions (`effective_category`, `link_payout`,
`reclassification_amount`), tested on their own; the database is reached through
NonInvoicedRepository.
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.non_invoiced import PAYOUT_FIRST_AFTER, LedgerEntry, LedgerKind
from app.models.order import (
    AddressType,
    Order,
    OrderPayment,
    OrderPaymentKind,
    OrderSource,
    PaymentOperation,
    PaymentType,
)
from app.repositories.non_invoiced_repository import PAYOUT, PAYOUT_CANCEL, NonInvoicedRepository
from app.schemas.types import _as_utc
from app.services.non_invoiced.classifier import (
    CONTRIBUTION,
    SURCHARGE,
    Category,
    Classification,
    classify,
    facts_from_order,
)

logger = logging.getLogger(__name__)

ORDER_KEY = "ORDER:"
SURCHARGE_KEY = "SURCHARGE:"
OPERATION_KEY = "OPERATION:"
RECLASSIFIED_KEY = "RECLASSIFIED:"

ZERO = Decimal("0.00")


class OverrideRefused(ValueError):
    """An override that the rules do not allow on this row."""


# --- the pure part ------------------------------------------------------------------------------


def business_date(moment: datetime) -> date:
    """The calendar day of `moment` where the business is (a stored naive time is UTC)."""
    return _as_utc(moment).astimezone(ZoneInfo(settings.business_timezone)).date()


def decide(automatic: Category, override: str | None) -> Category:
    """The category that counts: a person's override, except over a company's sale, which is
    outside the cash register obligation whatever anyone says (design 4a)."""
    if automatic is Category.BUSINESS or override is None:
        return automatic
    return Category(override)


def effective_category(entry: LedgerEntry) -> Category:
    """The category a row counts in: for a sale its override or its automatic result, for a
    correction the category whose total it adjusts."""
    if entry.kind is LedgerKind.CORRECTION:
        return Category(entry.category)
    return decide(Category(entry.category), entry.override_category)


def is_reclassification(entry: LedgerEntry) -> bool:
    return entry.event_key.startswith(RECLASSIFIED_KEY)


def reclassification_amount(sale: LedgerEntry, corrections: Iterable[LedgerEntry], in_report: bool) -> Decimal:
    """What a new correction must carry so that the report holds the sale's money exactly when the
    sale belongs in it.

    The sale's money is its own amount and its refunds'. The report carries whatever of the sale and
    its corrections counts as EXEMPT_MAIL_ORDER. While nothing is locked the two agree by
    themselves, since every row follows the sale's category; once a row is locked it no longer
    follows, and the difference is what is returned here (zero when nothing needs moving).
    """
    corrections = list(corrections)
    money = sale.amount + sum((c.amount for c in corrections if not is_reclassification(c)), ZERO)
    carried = sum(
        (row.amount for row in [sale, *corrections] if effective_category(row) is Category.EXEMPT_MAIL_ORDER),
        ZERO,
    )
    return (money if in_report else ZERO) - carried


@dataclass(frozen=True)
class PayoutLink:
    payout_id: str
    payout_at: datetime
    link: str = PAYOUT_FIRST_AFTER


def link_payout(payment: PaymentOperation, operations: Iterable[PaymentOperation]) -> PayoutLink | None:
    """The payout a buyer's payment most likely went out to the bank in (design 4d).

    The first `PAYOUT` of the same wallet operator after the payment, leaving out any payout a
    `PAYOUT_CANCEL` with the same payout id cancelled. An approximation: Allegro's operations do not
    show when money moves from WAITING to AVAILABLE, so a payment may in fact wait for a later
    payout. To be checked against the payout report Allegro's Sales Center exports.
    """
    if not payment.wallet_operator:
        return None
    operations = list(operations)
    cancelled = {op.payout_id for op in operations if op.type == PAYOUT_CANCEL and op.payout_id}
    paid_at = _as_utc(payment.occurred_at)
    payouts = sorted(
        (
            op
            for op in operations
            if op.type == PAYOUT
            and op.payout_id
            and op.payout_id not in cancelled
            and op.wallet_operator == payment.wallet_operator
            and _as_utc(op.occurred_at) > paid_at
        ),
        key=lambda op: _as_utc(op.occurred_at),
    )
    if not payouts:
        return None
    return PayoutLink(payouts[0].payout_id, _as_utc(payouts[0].occurred_at))


# --- the payments of an order --------------------------------------------------------------------


@dataclass(frozen=True)
class _Payment:
    """One payment of an order that is a SALE of its own."""

    key: str
    amount: Decimal
    currency: str
    paid_at: datetime
    payment_type: PaymentType | None
    operator: str | None
    payment_id: str | None
    # the operation proving it arrived at the operator: the CONTRIBUTION, or the SURCHARGE
    operation: PaymentOperation | None


def _surcharge_key(order: Order, payment: OrderPayment) -> str:
    # a surcharge Allegro always names by an id; one read without it is keyed by its place
    return SURCHARGE_KEY + (payment.external_id or f"{order.external_id}#{payment.position}")


def _payments(order: Order, operations: list[PaymentOperation]) -> list[_Payment]:
    payments = []
    if order.paid_at is not None and (order.paid_amount or ZERO) > 0:
        contribution = next(
            (op for op in operations if op.type == CONTRIBUTION and order.payment_id and op.payment_id == order.payment_id),
            None,
        )
        payments.append(
            _Payment(
                ORDER_KEY + order.external_id,
                order.paid_amount,
                order.currency,
                order.paid_at,
                order.payment_type,
                order.payment_provider,
                order.payment_id,
                contribution,
            )
        )
    for extra in order.extra_payments:
        if extra.kind is not OrderPaymentKind.SURCHARGE or extra.paid_at is None or (extra.paid_amount or ZERO) <= 0:
            continue
        operation = next(
            (
                op
                for op in operations
                if op.type == SURCHARGE and extra.external_id and extra.external_id in (op.surcharge_id, op.payment_id)
            ),
            None,
        )
        payments.append(
            _Payment(
                _surcharge_key(order, extra),
                extra.paid_amount,
                extra.currency or order.currency,
                extra.paid_at,
                extra.payment_type,
                extra.provider,
                extra.external_id,
                operation,
            )
        )
    return payments


def _classified(entry: LedgerEntry, classification: Classification) -> bool:
    """Put the classification on the row; whether it changed anything."""
    before = (entry.category, entry.reason, entry.ruleset)
    entry.category = classification.category.value
    entry.reason = classification.reason.value
    entry.ruleset = classification.ruleset
    return before != (entry.category, entry.reason, entry.ruleset)


def _traced(entry: LedgerEntry, payment: _Payment, payouts: list[PaymentOperation]) -> None:
    """Complete the trace of a row's money: its payment's id, the operation it was matched to and
    the payout (the operation and the payout often arrive after the row was written)."""
    if payment.payment_id:
        entry.payment_id = payment.payment_id
    if payment.operation is None:
        return
    entry.operation_fingerprint = payment.operation.fingerprint
    link = link_payout(payment.operation, payouts)
    entry.payout_id = link.payout_id if link else None
    entry.payout_at = link.payout_at if link else None
    entry.payout_link = link.link if link else None


def _new_sale(order: Order, payment: _Payment, classification: Classification) -> LedgerEntry:
    buyer = order.address(AddressType.BUYER)
    entry = LedgerEntry(
        kind=LedgerKind.SALE,
        event_key=payment.key,
        entry_at=_as_utc(payment.paid_at),
        entry_date=business_date(payment.paid_at),
        source=order.source,
        order_id=order.id,
        order_external_id=order.external_id,
        order_number=order.order_number,
        amount=payment.amount,
        currency=payment.currency,
        buyer_first_name=order.customer_first_name,
        buyer_last_name=order.customer_last_name,
        buyer_street=buyer.street if buyer else None,
        buyer_postal_code=buyer.postal_code if buyer else None,
        buyer_city=buyer.city if buyer else None,
        buyer_country_code=buyer.country_code if buyer else None,
        payment_type=payment.payment_type,
        payment_operator=payment.operator,
    )
    _classified(entry, classification)
    return entry


def _correction_of(sale: LedgerEntry, key: str, at: datetime, amount: Decimal, currency: str) -> LedgerEntry:
    """A correction of `sale`, copying what the record shows of it (the buyer from the sale row, not
    the order: the sale's copy is the one the record keeps)."""
    return LedgerEntry(
        kind=LedgerKind.CORRECTION,
        event_key=key,
        entry_at=_as_utc(at),
        entry_date=business_date(at),
        source=sale.source,
        order_id=sale.order_id,
        order_external_id=sale.order_external_id,
        order_number=sale.order_number,
        corrects_entry_id=sale.id,
        amount=amount,
        currency=currency,
        buyer_first_name=sale.buyer_first_name,
        buyer_last_name=sale.buyer_last_name,
        buyer_street=sale.buyer_street,
        buyer_postal_code=sale.buyer_postal_code,
        buyer_city=sale.buyer_city,
        buyer_country_code=sale.buyer_country_code,
        payment_type=sale.payment_type,
        payment_operator=sale.payment_operator,
        payment_id=sale.payment_id,
        # set by the caller
        category=sale.category,
        reason=sale.reason,
        ruleset=sale.ruleset,
    )


# --- the writer ---------------------------------------------------------------------------------


@dataclass
class LedgerResult:
    sales: int = 0
    reclassified: int = 0
    corrections: int = 0


def write_ledger(db: Session, source: OrderSource, since: datetime, now: datetime | None = None) -> LedgerResult:
    """Bring the ledger up to date with the orders of `source` paid since `since` and the refunds
    since then. Running it again writes nothing new. Commits."""
    now = now or datetime.now(UTC)
    repo = NonInvoicedRepository(db)
    result = LedgerResult()

    orders = {order.id: order for order in repo.orders_paid_since(source, since)}
    refunds = repo.refund_operations_since(source, since)
    stored_sales = repo.sales_by_payment_id(source, {op.payment_id for op in refunds})
    # the orders of sales refunded in the period, paid before it
    for order in repo.orders_by_id({s.order_id for s in stored_sales.values() if s.order_id} - set(orders)):
        orders[order.id] = order

    excluded = repo.excluded_offer_ids(source)
    ids = {order.payment_id for order in orders.values() if order.payment_id}
    ids |= {p.external_id for order in orders.values() for p in order.extra_payments if p.external_id}
    operations = repo.operations_naming(source, ids)

    of_order: dict[uuid.UUID, list[PaymentOperation]] = {}
    payments_of: dict[uuid.UUID, list[_Payment]] = {}
    for order in orders.values():
        keys = [order.payment_id] + [p.external_id for p in order.extra_payments]
        found = {op.fingerprint: op for key in keys if key for op in operations.get(key, [])}
        of_order[order.id] = sorted(found.values(), key=lambda op: _as_utc(op.occurred_at))
        payments_of[order.id] = _payments(order, of_order[order.id])

    matched = [p.operation for payments in payments_of.values() for p in payments if p.operation is not None]
    payouts = (
        repo.payout_operations_since(source, min(_as_utc(op.occurred_at) for op in matched)) if matched else []
    )
    keys = {p.key for payments in payments_of.values() for p in payments}
    keys |= {OPERATION_KEY + op.fingerprint for op in refunds}
    existing = repo.entries_by_key(source, keys)

    # 1. the sales: written, or classified again while not locked
    classification_of: dict[uuid.UUID, Classification | None] = {}
    sales: dict[uuid.UUID, LedgerEntry] = {}
    for order in orders.values():
        # a deleted order, or one whose buyer's data was erased, is left as its rows say: classified
        # again it would lose the facts it was classified on
        frozen = order.deleted_at is not None or order.anonymized_at is not None
        classification = None if frozen else classify(facts_from_order(order, of_order[order.id], excluded))
        classification_of[order.id] = classification
        for payment in payments_of[order.id]:
            entry = existing.get(payment.key)
            if entry is None:
                if classification is None or classification.category is Category.NOT_A_SALE:
                    continue
                entry = _new_sale(order, payment, classification)
                _traced(entry, payment, payouts)
                repo.add(entry)
                existing[payment.key] = entry
                result.sales += 1
            elif entry.locked_at is None:
                if classification is not None and _classified(entry, classification):
                    result.reclassified += 1
                _traced(entry, payment, payouts)
            sales[entry.id] = entry
    for sale in stored_sales.values():
        sales.setdefault(sale.id, sale)

    # 2. the refunds, as corrections of the sale whose payment they name (the order's main payment
    #    before a surcharge)
    by_payment: dict[str, LedgerEntry] = {}
    for sale in sorted(sales.values(), key=lambda s: not s.event_key.startswith(ORDER_KEY)):
        if sale.payment_id:
            by_payment.setdefault(sale.payment_id, sale)
    for operation in refunds:
        key = OPERATION_KEY + operation.fingerprint
        sale = by_payment.get(operation.payment_id)
        if key in existing or sale is None or operation.amount == 0:
            # a refund of a sale the ledger never held (paid before it began) is no correction of it
            continue
        correction = _correction_of(sale, key, operation.occurred_at, operation.amount, operation.currency)
        correction.operation_fingerprint = operation.fingerprint
        repo.add(correction)
        existing[key] = correction
        result.corrections += 1

    # 3. every sale's corrections follow it while they are not locked, and what is locked and no
    #    longer where it belongs is moved by a correction dated now
    corrections = repo.corrections_of(sales.keys())
    for sale in sales.values():
        classification = classification_of.get(sale.order_id)
        automatic = classification.category if classification is not None else Category(sale.category)
        reason = classification.reason.value if classification is not None else sale.reason
        ruleset = classification.ruleset if classification is not None else sale.ruleset
        category = decide(automatic, sale.override_category)
        own = corrections.get(sale.id, [])
        for correction in own:
            if correction.locked_at is None and not is_reclassification(correction):
                correction.category, correction.reason, correction.ruleset = category.value, reason, ruleset
        amount = reclassification_amount(sale, own, category is Category.EXEMPT_MAIL_ORDER)
        if amount == 0:
            continue
        moves = sum(1 for c in own if is_reclassification(c))
        moved = _correction_of(sale, f"{RECLASSIFIED_KEY}{sale.id}:{moves + 1}", now, amount, sale.currency)
        # it adjusts the report's total, so it counts where the report looks
        moved.category, moved.reason, moved.ruleset = Category.EXEMPT_MAIL_ORDER.value, reason, ruleset
        repo.add(moved)
        result.corrections += 1

    db.commit()
    if result.sales or result.reclassified or result.corrections:
        logger.info(
            "Non-invoiced ledger for %s: %d sales written, %d classified again, %d corrections",
            source.value,
            result.sales,
            result.reclassified,
            result.corrections,
        )
    return result


# --- overrides -----------------------------------------------------------------------------------


def _overridable(db: Session, entry_id) -> LedgerEntry:
    entry = NonInvoicedRepository(db).get(entry_id)
    if entry is None:
        raise LookupError("No such ledger row")
    if entry.kind is not LedgerKind.SALE:
        raise OverrideRefused("Only a sale can be overridden; a correction follows its sale")
    if entry.locked_at is not None:
        raise OverrideRefused(
            "The row was handed over to the accountant and cannot change; a later change is a correction"
        )
    if Category(entry.category) is Category.BUSINESS:
        raise OverrideRefused("A company's purchase is outside the cash register obligation and cannot be overridden")
    return entry


def set_override(
    db: Session,
    entry_id,
    category: Category,
    note: str,
    user_id: int | None,
    now: datetime | None = None,
) -> LedgerEntry:
    """A person's category for a sale, with the reason written down; the automatic result stays
    beside it. Commits."""
    if not (note and note.strip()):
        raise OverrideRefused("An override needs a written reason")
    entry = _overridable(db, entry_id)
    entry.override_category = Category(category).value
    entry.override_note = note.strip()
    entry.overridden_by_user_id = user_id
    entry.overridden_at = _as_utc(now or datetime.now(UTC))
    db.commit()
    return entry


def clear_override(db: Session, entry_id, user_id: int | None, now: datetime | None = None) -> LedgerEntry:
    """Back to the automatic result. Commits."""
    entry = _overridable(db, entry_id)
    entry.override_category = None
    entry.override_note = None
    entry.overridden_by_user_id = user_id
    entry.overridden_at = _as_utc(now or datetime.now(UTC))
    db.commit()
    return entry
