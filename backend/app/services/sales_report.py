"""The non-invoiced sales report: ported from a standalone tool (`docs/RITEVO.md`'s sibling,
`temp/`, kept out of this repository) that classified an Allegro CSV export for accounting.

Three rules, in the ported tool's own priority order:

- A complete company invoice (name, street, postal code, city, country and tax id all present)
  excludes an order as `COMPANY`. Checked first and never open to a manual override, the same as
  in the ported tool ("Priorytet 1 jest automatyczny") — `BUSINESS_DECISIONS.md` BD-001/BD-015.
- An order the marketplace shows cancelled or suspended, and that was never paid in full,
  excludes as `OUT_OF_SCOPE` (BD-002).
- An order paid in full, in PLN, shipped, and with no invoice or only a personal one (a name,
  never a company name or tax id) qualifies as `RETAIL` on its own (`PAY-001`). The ported tool's
  own code has this rule (`qualifyV1` in `js/business/rules/rule-utils.js`) without an entry in
  its `BUSINESS_DECISIONS.md` register — a gap in that tool's own governance, not evidence the
  rule is wrong: its `RULE_REFINEMENT_REPORT.md` shows it is what kept "for review" small in
  practice (74 of 614 orders on its June baseline). Approved here on 2026-09-27 after the owner
  saw the gap for themselves (`docs/DECISIONS.md`). "Shipped" is read off Anvero's own status
  (`SHIPPED`/`DELIVERED`), not the marketplace's raw label as the ported tool did (`SENT`
  literally): Anvero's own status collapses the marketplace's wider vocabulary to the same effect
  the ported tool got from a CSV export that only ever held `SENT`, `CANCELLED` or `SUSPENDED`.
- Everything else is `MANUAL_REVIEW`, never guessed further.

A row's `included`/`category` can be overridden by an operator (`SalesReportOverride`), except a
`COMPANY` row from the first rule.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.order_number import format_order_number
from app.models.order import AddressType, Order, OrderSource, OrderStatus
from app.models.sales_report import SalesReportOverride
from app.schemas.sales_report import (
    SalesReportCategory,
    SalesReportList,
    SalesReportRow,
    SalesReportSummary,
)

# what a completed sale, for the second and third rules, must at least clear
ZERO = Decimal("0.00")

# "shipped", for the third rule: Anvero's own status, which already collapses the marketplace's
# wider vocabulary (DATABASE.md, "marketplace_status_label") to the distinction the rule needs
SHIPPED_STATUSES = frozenset({OrderStatus.SHIPPED, OrderStatus.DELIVERED})


@dataclass(frozen=True)
class OrderFacts:
    """What the rules need, independent of whether it came from an Anvero order or a CSV row —
    so an eventual CSV path (`ROADMAP.md`) reuses the same `classify`."""

    source: OrderSource
    order_external_id: str
    ordered_at: datetime
    amount: Decimal
    currency: str
    buyer_login: str | None
    # Anvero's own status: NEW/CONFIRMED/READY_FOR_SHIPMENT/SHIPPED/DELIVERED/CANCELLED
    status: OrderStatus
    # the marketplace's own status word, unmapped (Anvero's own five statuses collapse
    # distinctions this rule needs, e.g. Allegro's SUSPENDED)
    marketplace_status_label: str | None
    paid_amount: Decimal | None
    invoice_first_name: str | None
    invoice_last_name: str | None
    invoice_company_name: str | None
    invoice_street: str | None
    invoice_postal_code: str | None
    invoice_city: str | None
    invoice_country_code: str | None
    invoice_tax_id: str | None


@dataclass(frozen=True)
class Classification:
    category: SalesReportCategory
    included: bool
    reason: str
    rule_id: str
    # whether an operator's override may still change this row
    overridable: bool


def _is_complete_company_invoice(facts: OrderFacts) -> bool:
    return all(
        (facts.invoice_company_name, facts.invoice_street, facts.invoice_postal_code, facts.invoice_city, facts.invoice_country_code, facts.invoice_tax_id)
    )


def _is_cancelled_or_suspended_unpaid(facts: OrderFacts) -> bool:
    status = (facts.marketplace_status_label or "").strip().upper()
    if status not in ("CANCELLED", "SUSPENDED"):
        return False
    if facts.paid_amount is None:
        return True
    return facts.paid_amount < facts.amount


def _is_named_personal_invoice(facts: OrderFacts) -> bool:
    return bool(facts.invoice_first_name or facts.invoice_last_name) and not facts.invoice_company_name and not facts.invoice_tax_id


def _has_no_invoice_data(facts: OrderFacts) -> bool:
    return not any(
        (
            facts.invoice_first_name,
            facts.invoice_last_name,
            facts.invoice_company_name,
            facts.invoice_street,
            facts.invoice_postal_code,
            facts.invoice_city,
            facts.invoice_country_code,
            facts.invoice_tax_id,
        )
    )


def _qualifies_paid_and_shipped(facts: OrderFacts) -> bool:
    if facts.status not in SHIPPED_STATUSES:
        return False
    if facts.currency != "PLN" or facts.amount <= ZERO:
        return False
    if facts.paid_amount is None or facts.paid_amount < facts.amount:
        return False
    return _has_no_invoice_data(facts) or _is_named_personal_invoice(facts)


def classify(facts: OrderFacts) -> Classification:
    """The approved rules, in the ported tool's own priority order, else manual review."""
    if _is_complete_company_invoice(facts):
        return Classification(
            category=SalesReportCategory.COMPANY,
            included=False,
            reason="Kompletna faktura firmowa (nazwa, ulica, kod, miasto, kraj i NIP wypełnione)",
            rule_id="INV-001",
            overridable=False,
        )
    if _is_cancelled_or_suspended_unpaid(facts):
        return Classification(
            category=SalesReportCategory.OUT_OF_SCOPE,
            included=False,
            reason="Anulowane lub zawieszone u marketplace'u, a sprzedaż nie została w pełni opłacona",
            rule_id="SEL-001",
            overridable=True,
        )
    if _qualifies_paid_and_shipped(facts):
        return Classification(
            category=SalesReportCategory.RETAIL,
            included=True,
            reason="Opłacone w całości, wysłane, w PLN, bez faktury firmowej",
            rule_id="PAY-001",
            overridable=True,
        )
    return Classification(
        category=SalesReportCategory.MANUAL_REVIEW,
        included=False,
        reason="Żadna zatwierdzona reguła nie kwalifikuje ani nie wyklucza tego zamówienia wprost",
        rule_id="REV-001",
        overridable=True,
    )


class SalesReportService:
    def __init__(self, db: Session):
        self.db = db

    def _overrides(self, source: OrderSource | None) -> dict[tuple[OrderSource, str], SalesReportOverride]:
        stmt = select(SalesReportOverride)
        if source is not None:
            stmt = stmt.where(SalesReportOverride.source == source)
        return {(row.source, row.order_external_id): row for row in self.db.execute(stmt).scalars()}

    def from_orders(self, date_from: date, date_to: date, source: OrderSource | None = None) -> SalesReportList:
        """Classify Anvero's own imported orders placed in the period; no CSV involved."""
        period_start = datetime.combine(date_from, time.min)
        period_end = datetime.combine(date_to, time.max)

        stmt = (
            select(Order)
            .options(selectinload(Order.addresses))
            .where(Order.ordered_at >= period_start, Order.ordered_at <= period_end, Order.deleted_at.is_(None))
        )
        if source is not None:
            stmt = stmt.where(Order.source == source)
        orders = self.db.execute(stmt).scalars().all()

        overrides = self._overrides(source)

        items: list[SalesReportRow] = []
        for order in orders:
            invoice = order.address(AddressType.INVOICE)
            facts = OrderFacts(
                source=order.source,
                order_external_id=order.external_id,
                ordered_at=order.ordered_at,
                amount=order.total_amount,
                currency=order.currency,
                buyer_login=order.customer_login,
                status=order.status,
                marketplace_status_label=order.marketplace_status_label,
                paid_amount=order.paid_amount,
                invoice_first_name=invoice.first_name if invoice else None,
                invoice_last_name=invoice.last_name if invoice else None,
                invoice_company_name=invoice.company_name if invoice else None,
                invoice_street=invoice.street if invoice else None,
                invoice_postal_code=invoice.postal_code if invoice else None,
                invoice_city=invoice.city if invoice else None,
                invoice_country_code=invoice.country_code if invoice else None,
                invoice_tax_id=invoice.tax_id if invoice else None,
            )
            result = classify(facts)

            # the automatic category and rule id stay on the row even after an override: the
            # operator's decision only flips `included`, so the row still says what the rules
            # themselves found, with the override as an addition, not a replacement
            override = overrides.get((order.source, order.external_id))
            category, included, reason, rule_id, overridden = result.category, result.included, result.reason, result.rule_id, False
            if override is not None and result.overridable:
                included = override.included
                reason = override.note or ("Ręcznie uwzględnione mimo klasyfikacji" if included else "Ręcznie wykluczone mimo klasyfikacji")
                overridden = True

            items.append(
                SalesReportRow(
                    order_id=order.id,
                    order_label=format_order_number(order.order_number),
                    source=order.source,
                    order_external_id=order.external_id,
                    ordered_at=order.ordered_at,
                    buyer_login=order.customer_login,
                    amount=order.total_amount,
                    currency=order.currency,
                    category=category,
                    included=included,
                    reason=reason,
                    rule_id=rule_id,
                    overridden=overridden,
                    override_note=override.note if override is not None else None,
                )
            )

        items.sort(key=lambda row: row.ordered_at, reverse=True)
        summary = SalesReportSummary(
            total=len(items),
            retail=sum(1 for r in items if r.category is SalesReportCategory.RETAIL),
            company=sum(1 for r in items if r.category is SalesReportCategory.COMPANY),
            out_of_scope=sum(1 for r in items if r.category is SalesReportCategory.OUT_OF_SCOPE),
            manual_review=sum(1 for r in items if r.category is SalesReportCategory.MANUAL_REVIEW),
        )
        return SalesReportList(date_from=date_from, date_to=date_to, summary=summary, items=items)

    def set_override(self, source: OrderSource, order_external_id: str, included: bool, note: str | None, user_id: int | None) -> None:
        existing = self.db.execute(
            select(SalesReportOverride).where(
                SalesReportOverride.source == source, SalesReportOverride.order_external_id == order_external_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.included = included
            existing.note = note
            existing.created_by_user_id = user_id
        else:
            self.db.add(
                SalesReportOverride(
                    source=source, order_external_id=order_external_id, included=included, note=note, created_by_user_id=user_id
                )
            )
        self.db.commit()

    def clear_override(self, source: OrderSource, order_external_id: str) -> None:
        existing = self.db.execute(
            select(SalesReportOverride).where(
                SalesReportOverride.source == source, SalesReportOverride.order_external_id == order_external_id
            )
        ).scalar_one_or_none()
        if existing is not None:
            self.db.delete(existing)
            self.db.commit()
