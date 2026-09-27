"""The non-invoiced sales report: ported from a standalone tool (`docs/RITEVO.md`'s sibling,
`temp/`, kept out of this repository) that classified an Allegro CSV export for accounting.

Only its two APPROVED business decisions are implemented, exactly as it registered them
(`temp/sales-report-v2/BUSINESS_DECISIONS.md`, BD-001/BD-015 and BD-002):

- A complete company invoice (name, street, postal code, city, country and tax id all present)
  excludes an order as `COMPANY`. This is checked first and is never open to a manual override,
  the same as in the ported tool ("Priorytet 1 jest automatyczny").
- An order the marketplace shows cancelled or suspended, and that was never paid in full,
  excludes as `OUT_OF_SCOPE`.
- Everything else is `MANUAL_REVIEW`. The ported tool's code also has a third path, qualifying a
  paid, sent, uninvoiced-or-personally-invoiced order as `RETAIL` on its own — but that path has
  no entry in its own `BUSINESS_DECISIONS.md` register, so it is a leftover of the tool's first
  version, not an approved rule, and is deliberately left out here (`docs/DECISIONS.md`).

A row's `included`/`category` can be overridden by an operator (`SalesReportOverride`), except a
`COMPANY` row from the first rule.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.order_number import format_order_number
from app.models.order import AddressType, Order, OrderSource
from app.models.sales_report import SalesReportOverride
from app.schemas.sales_report import (
    SalesReportCategory,
    SalesReportList,
    SalesReportRow,
    SalesReportSummary,
)

# what a completed sale, for the second rule, must at least clear
ZERO = Decimal("0.00")


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
    # the marketplace's own status word, unmapped (Anvero's own five statuses collapse
    # distinctions this rule needs, e.g. Allegro's SUSPENDED)
    marketplace_status_label: str | None
    paid_amount: Decimal | None
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


def classify(facts: OrderFacts) -> Classification:
    """The two approved rules, in the ported tool's own priority order, else manual review."""
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
                marketplace_status_label=order.marketplace_status_label,
                paid_amount=order.paid_amount,
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
