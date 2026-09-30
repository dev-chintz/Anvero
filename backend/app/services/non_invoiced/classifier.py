"""Which category an order falls in for the non-invoiced sales record (docs/NON_INVOICED_SALES.md,
section 4a), and why.

A pure function of what is known about the order: `classify(facts)` reads nothing and writes
nothing, so every rule is tested case by case (tests/services/test_non_invoiced_classifier.py) and
the whole record can be classified again whenever the rules change. `facts_from_order` gathers
those facts from a stored order and its payment operations.

The exemption checked is poz. 41 of the annex to the regulation of 2024-12-17 (Dz.U. 2024 poz.
1902, as amended by Dz.U. 2026 poz. 420): a delivery of goods by mail order (post or courier),
paid in full through a bank, the post or a credit union to the seller's account, with records
showing which sale each payment was for and whom (the buyer's data, address included). A payment
through a payment operator that ends on the seller's bank account counts as through a bank
(interpretation 0112-KDIL3.4012.238.2025.1.MC). The rules run in the order below; the first that
applies decides.
"""

import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from app.models.order import (
    AddressType,
    Order,
    OrderPaymentKind,
    OrderSource,
    OrderStatus,
    PaymentOperation,
    PaymentType,
)

# Bumped whenever a rule changes, and kept on every classified row, so that a record made under
# older rules can be told apart (the exemptions hold until 2027-12-31 at most). /2: Erli's sales are
# classified by the same rules as Allegro's (stage 7).
RULESET = "poz41-2024/2"

# the payment operators through which a payment reaches the seller's bank account: Allegro's
# (PayU, Przelewy24, Allegro Finance), and Erli, which collects through PayU and pays out to the
# seller's bank account itself (app/integrations/erli/payments.py)
OPERATORS = frozenset({"PAYU", "P24", "AF", "ERLI"})
# the marketplaces the rules know how to read
SOURCES = frozenset({OrderSource.ALLEGRO, OrderSource.ERLI})
# the payment types that are neither cash nor deferred
BANK_PAYMENT_TYPES = frozenset({PaymentType.ONLINE, PaymentType.BANK_TRANSFER})
# the operation that is a buyer's payment arriving at the operator
CONTRIBUTION = "CONTRIBUTION"
SURCHARGE = "SURCHARGE"
HOME_COUNTRY = "PL"


class Category(str, enum.Enum):
    # poz. 41: in the report
    EXEMPT_MAIL_ORDER = "EXEMPT_MAIL_ORDER"
    # a private buyer who asked for an invoice: the invoice documents the sale
    PRIVATE_INVOICED = "PRIVATE_INVOICED"
    # a company: outside the cash register obligation
    BUSINESS = "BUSINESS"
    # should have gone through the cash register
    NEEDS_REGISTER = "NEEDS_REGISTER"
    # the rules cannot decide; a person must
    TO_REVIEW = "TO_REVIEW"
    # never a sale: never paid
    NOT_A_SALE = "NOT_A_SALE"


class Reason(str, enum.Enum):
    E41 = "E41"
    NOT_PAID = "NOT_PAID"
    COMPANY = "COMPANY"
    CASH_PART = "CASH_PART"
    PERSONAL_COLLECTION = "PERSONAL_COLLECTION"
    EXCLUDED_GOODS = "EXCLUDED_GOODS"
    PRIVATE_INVOICE = "PRIVATE_INVOICE"
    SOURCE_NOT_SUPPORTED = "SOURCE_NOT_SUPPORTED"
    CANCELLED_AFTER_PAYMENT = "CANCELLED_AFTER_PAYMENT"
    FOREIGN_DELIVERY = "FOREIGN_DELIVERY"
    NO_DELIVERY_METHOD = "NO_DELIVERY_METHOD"
    NOT_VIA_OPERATOR = "NOT_VIA_OPERATOR"
    UNDERPAID = "UNDERPAID"
    MISSING_BUYER_DATA = "MISSING_BUYER_DATA"
    NO_PAYMENT_ID = "NO_PAYMENT_ID"
    NO_CONTRIBUTION = "NO_CONTRIBUTION"
    SURCHARGE_UNTRACED = "SURCHARGE_UNTRACED"


# what each reason means, in the owner's language, for the screen and the exports
REASON_TEXT = {
    Reason.E41: "Sprzedaż wysyłkowa opłacona w całości przez operatora płatności (poz. 41)",
    Reason.NOT_PAID: "Nieopłacone",
    Reason.COMPANY: "Zakup firmy (faktura z NIP)",
    Reason.CASH_PART: "Część zapłaty gotówką (pobranie lub płatność przy odbiorze)",
    Reason.PERSONAL_COLLECTION: "Odbiór osobisty, nie wysyłka",
    Reason.EXCLUDED_GOODS: "Towar wyłączony ze zwolnienia (§ 4 rozporządzenia)",
    Reason.PRIVATE_INVOICE: "Osoba prywatna poprosiła o fakturę",
    Reason.SOURCE_NOT_SUPPORTED: "Kanał jeszcze nieobsługiwany w zestawieniu",
    Reason.CANCELLED_AFTER_PAYMENT: "Anulowane po zapłacie",
    Reason.FOREIGN_DELIVERY: "Wysyłka za granicę",
    Reason.NO_DELIVERY_METHOD: "Brak sposobu dostawy",
    Reason.NOT_VIA_OPERATOR: "Zapłata nie przez operatora płatności na rachunek",
    Reason.UNDERPAID: "Zapłacono mniej niż wartość zamówienia",
    Reason.MISSING_BUYER_DATA: "Brak imienia, nazwiska lub adresu kupującego",
    Reason.NO_PAYMENT_ID: "Brak identyfikatora płatności (zamówienie do ponownego odczytu)",
    Reason.NO_CONTRIBUTION: "Nie znaleziono wpłaty u operatora płatności",
    Reason.SURCHARGE_UNTRACED: "Nie znaleziono wpłaty dopłaty u operatora płatności",
}


@dataclass(frozen=True)
class ExtraPaymentFacts:
    kind: OrderPaymentKind
    external_id: str | None
    paid_amount: Decimal | None


@dataclass(frozen=True)
class SaleFacts:
    """What the rules look at, independent of where it was read from."""

    source: OrderSource
    status: OrderStatus
    cancelled_on_marketplace: bool
    total_amount: Decimal
    payment_type: PaymentType | None
    payment_provider: str | None
    paid_amount: Decimal | None
    paid: bool
    payment_id: str | None
    extra_payments: tuple[ExtraPaymentFacts, ...] = ()
    invoice_required: bool = False
    invoice_is_company: bool | None = None
    invoice_tax_id: str | None = None
    delivery_method: str | None = None
    delivery_country_code: str | None = None
    buyer_first_name: str | None = None
    buyer_last_name: str | None = None
    buyer_has_address: bool = False
    # the operations found for the order's payment id (and its surcharges)
    contribution_found: bool = False
    surcharge_ids_found: frozenset[str] = field(default_factory=frozenset)
    has_excluded_goods: bool = False


@dataclass(frozen=True)
class Classification:
    category: Category
    reason: Reason
    ruleset: str = RULESET

    @property
    def in_report(self) -> bool:
        return self.category is Category.EXEMPT_MAIL_ORDER

    @property
    def text(self) -> str:
        return REASON_TEXT[self.reason]


def _is_personal_collection(method: str | None) -> bool:
    # Allegro's own methods for it are named "Odbiór osobisty" (with or without "po
    # przedpłacie"); no courier or locker method carries the words
    return method is not None and "odbiór osobisty" in method.casefold()


def _paid_in_full(facts: SaleFacts) -> bool:
    paid = facts.paid_amount or Decimal("0")
    paid += sum(
        (p.paid_amount or Decimal("0")) for p in facts.extra_payments if p.kind is OrderPaymentKind.SURCHARGE
    )
    return paid >= facts.total_amount


def classify(facts: SaleFacts) -> Classification:
    """The category and reason for one order: the first rule that applies decides."""

    def result(category: Category, reason: Reason) -> Classification:
        return Classification(category, reason)

    # 1. never paid: never a sale, whatever else is true of it
    if not facts.paid:
        return result(Category.NOT_A_SALE, Reason.NOT_PAID)

    # 2. a company: outside the obligation (the marketplace's own word first; for an order that
    #    does not say, a tax id on the invoice address)
    is_company = facts.invoice_is_company
    if is_company is None:
        is_company = bool(facts.invoice_tax_id)
    if is_company:
        return result(Category.BUSINESS, Reason.COMPANY)

    # 3. what should have gone through the cash register
    has_cash = facts.payment_type is PaymentType.CASH_ON_DELIVERY or (facts.payment_provider or "").upper() == "OFFLINE"
    has_cash = has_cash or any(
        p.kind is OrderPaymentKind.CASH_ON_DELIVERY and (p.paid_amount or Decimal("0")) > 0 for p in facts.extra_payments
    )
    if has_cash:
        return result(Category.NEEDS_REGISTER, Reason.CASH_PART)
    if _is_personal_collection(facts.delivery_method):
        return result(Category.NEEDS_REGISTER, Reason.PERSONAL_COLLECTION)
    if facts.has_excluded_goods:
        return result(Category.NEEDS_REGISTER, Reason.EXCLUDED_GOODS)

    # 4. a private buyer who asked for an invoice: the invoice documents it (the accountant,
    #    2026-09-30), so it stays out of the report and is listed apart
    if facts.invoice_required:
        return result(Category.PRIVATE_INVOICED, Reason.PRIVATE_INVOICE)

    # 5. what the rules cannot decide
    if facts.source not in SOURCES:
        return result(Category.TO_REVIEW, Reason.SOURCE_NOT_SUPPORTED)
    if facts.status is OrderStatus.CANCELLED or facts.cancelled_on_marketplace:
        return result(Category.TO_REVIEW, Reason.CANCELLED_AFTER_PAYMENT)
    if facts.delivery_country_code and facts.delivery_country_code.upper() != HOME_COUNTRY:
        return result(Category.TO_REVIEW, Reason.FOREIGN_DELIVERY)
    if not facts.delivery_method:
        return result(Category.TO_REVIEW, Reason.NO_DELIVERY_METHOD)
    if facts.payment_type not in BANK_PAYMENT_TYPES or (facts.payment_provider or "").upper() not in OPERATORS:
        return result(Category.TO_REVIEW, Reason.NOT_VIA_OPERATOR)
    if not _paid_in_full(facts):
        return result(Category.TO_REVIEW, Reason.UNDERPAID)
    if not (facts.buyer_first_name and facts.buyer_last_name and facts.buyer_has_address):
        return result(Category.TO_REVIEW, Reason.MISSING_BUYER_DATA)
    if not facts.payment_id:
        return result(Category.TO_REVIEW, Reason.NO_PAYMENT_ID)
    if not facts.contribution_found:
        return result(Category.TO_REVIEW, Reason.NO_CONTRIBUTION)
    for payment in facts.extra_payments:
        if payment.kind is OrderPaymentKind.SURCHARGE and payment.external_id not in facts.surcharge_ids_found:
            return result(Category.TO_REVIEW, Reason.SURCHARGE_UNTRACED)

    # 6. poz. 41
    return result(Category.EXEMPT_MAIL_ORDER, Reason.E41)


def buyer_address(order: Order):
    """The buyer's own address: Allegro names it apart (`buyer.address`); Erli names no buyer apart
    from the delivery address (INTEGRATIONS.md, "Erli"), so for Erli that is the buyer's."""
    address = order.address(AddressType.BUYER)
    if address is None and order.source is OrderSource.ERLI:
        address = order.address(AddressType.DELIVERY)
    return address


def facts_from_order(
    order: Order,
    operations: Iterable[PaymentOperation] = (),
    excluded_offer_ids: frozenset[str] = frozenset(),
) -> SaleFacts:
    """The facts `classify` needs, from a stored order, the payment operations that name its
    payment or surcharges, and the offers flagged as excluded goods (§ 4)."""
    operations = list(operations)
    contribution_found = bool(order.payment_id) and any(
        op.type == CONTRIBUTION and op.payment_id == order.payment_id for op in operations
    )
    # a surcharge's operation may name it by the surcharge's own id or by its payment's id
    surcharge_ids_found = frozenset(
        value for op in operations if op.type == SURCHARGE for value in (op.surcharge_id, op.payment_id) if value
    )
    buyer = buyer_address(order)
    invoice_address = order.address(AddressType.INVOICE)
    return SaleFacts(
        source=order.source,
        status=order.status,
        cancelled_on_marketplace=order.marketplace_cancelled_at is not None,
        total_amount=order.total_amount,
        payment_type=order.payment_type,
        payment_provider=order.payment_provider,
        paid_amount=order.paid_amount,
        paid=order.paid_at is not None and (order.paid_amount or Decimal("0")) > 0,
        payment_id=order.payment_id,
        extra_payments=tuple(
            ExtraPaymentFacts(p.kind, p.external_id, p.paid_amount) for p in order.extra_payments
        ),
        invoice_required=order.invoice_required,
        invoice_is_company=order.invoice_is_company,
        invoice_tax_id=invoice_address.tax_id if invoice_address is not None else None,
        delivery_method=order.delivery_method,
        delivery_country_code=order.delivery_country_code,
        buyer_first_name=order.customer_first_name,
        buyer_last_name=order.customer_last_name,
        buyer_has_address=bool(buyer is not None and buyer.street and buyer.city and buyer.postal_code),
        contribution_found=contribution_found,
        surcharge_ids_found=surcharge_ids_found,
        has_excluded_goods=any(item.offer_id in excluded_offer_ids for item in order.items if item.offer_id),
    )
