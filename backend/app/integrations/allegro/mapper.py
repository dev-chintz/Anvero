"""Translation from Allegro's checkout form into the Anvero domain shape.

Field names follow GET /order/checkout-forms. Nothing here leaks outside the
allegro package: callers receive OrderCreate.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.core.text import clean_marketplace_text
from app.integrations.base import IntegrationError
from app.integrations.mapping import build as _build
from app.integrations.mapping import obj as _obj
from app.integrations.mapping import text as _text
from app.models.message import MessageDirection
from app.models.order import OrderPaymentKind, OrderSource, OrderStatus, PaymentType
from app.schemas.message import SyncedMessage, SyncedThread
from app.schemas.order import (
    BUYER_MESSAGE_MAX_LENGTH,
    SELLER_NOTE_MAX_LENGTH,
    Address,
    BillingEntryCreate,
    Customer,
    Delivery,
    ExtraPayment,
    Invoice,
    OrderCreate,
    OrderDetails,
    OrderItemCreate,
    Payment,
    PaymentOperationCreate,
    PayoutCreate,
    PickupPoint,
    ShipmentCreate,
)

# Allegro tracks two axes. `status` covers the buying process and
# `fulfillment.status` covers physical handling, so the single Anvero status
# is derived from both. A cancelled order is cancelled whatever its parcel is
# doing, so that check comes first.
_FULFILLMENT_TO_STATUS = {
    "NEW": OrderStatus.NEW,
    "PROCESSING": OrderStatus.CONFIRMED,
    # packed but not yet handed to the carrier
    "READY_FOR_SHIPMENT": OrderStatus.READY_FOR_SHIPMENT,
    "SENT": OrderStatus.SHIPPED,
    # already at the pickup point, so it has travelled even though nobody has
    # collected it yet
    "READY_FOR_PICKUP": OrderStatus.SHIPPED,
    "PICKED_UP": OrderStatus.DELIVERED,
}

# used when fulfillment is absent, which happens before handling starts
_CHECKOUT_STATUS_TO_STATUS = {
    "BOUGHT": OrderStatus.NEW,
    "FILLED_IN": OrderStatus.NEW,
    "READY_FOR_PROCESSING": OrderStatus.CONFIRMED,
    "CANCELLED": OrderStatus.CANCELLED,
}


logger = logging.getLogger(__name__)


class OrderMappingError(IntegrationError):
    """A checkout form could not be expressed as an Anvero order."""


def map_ordered_at(checkout_form: dict[str, Any]) -> datetime | None:
    """When the buyer placed the order, in UTC.

    A checkout form has no single purchase timestamp; each line item carries
    `boughtAt`, and the earliest is when the order was placed. Returns None
    when there is none to read, so the order is still imported and dated at
    import time — a wrong date is recoverable, a lost order is not.
    """
    external_id = checkout_form.get("id")
    moments = []
    line_items = checkout_form.get("lineItems")
    for item in line_items if isinstance(line_items, list) else []:
        # a non-object item used to raise AttributeError, which is not a
        # mapping error, so it escaped the per-order skip and lost the page
        raw = _obj(item).get("boughtAt")
        if not raw:
            continue
        try:
            moment = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            logger.warning("Order %s has an unreadable boughtAt: %r", external_id, raw)
            continue
        if moment.tzinfo is None:
            # Allegro sends "Z"; a zone-less value is read as UTC, not local
            moment = moment.replace(tzinfo=UTC)
        moments.append(moment.astimezone(UTC))

    if not moments:
        logger.warning(
            "Order %s has no purchase time; it will be dated at import", external_id
        )
        return None
    return min(moments)


def map_status_label(checkout_form: dict[str, Any]) -> str | None:
    """Allegro's own status, kept as it comes for the operator to read.

    The mapping to an Anvero status loses detail — PROCESSING and
    READY_FOR_SHIPMENT both become CONFIRMED — and the operator comparing
    Anvero with the Allegro panel needs the distinction. Stored as the raw
    value rather than a translation, which would need maintaining and would
    drift from what Allegro shows.
    """
    if checkout_form.get("status") == "CANCELLED":
        return "CANCELLED"

    fulfillment = _obj(checkout_form.get("fulfillment"))
    label = fulfillment.get("status") or checkout_form.get("status")
    if not isinstance(label, str) or not label.strip():
        return None
    return label.strip()[:64]


def map_status(checkout_form: dict[str, Any]) -> OrderStatus:
    if checkout_form.get("status") == "CANCELLED":
        return OrderStatus.CANCELLED

    fulfillment = _obj(checkout_form.get("fulfillment"))
    mapped = _FULFILLMENT_TO_STATUS.get(fulfillment.get("status"))
    if mapped is not None:
        return mapped

    # an unknown value is better treated as new work than silently dropped
    return _CHECKOUT_STATUS_TO_STATUS.get(
        checkout_form.get("status"), OrderStatus.NEW
    )


_PAYMENT_TYPES = {
    "ONLINE": PaymentType.ONLINE,
    "CASH_ON_DELIVERY": PaymentType.CASH_ON_DELIVERY,
    "WIRE_TRANSFER": PaymentType.BANK_TRANSFER,
    # the Polish split payment mechanism (MPP) is a form of bank transfer
    "SPLIT_PAYMENT": PaymentType.BANK_TRANSFER,
    "EXTENDED_TERM": PaymentType.DEFERRED,
}


def _amount(price: Any) -> Decimal | None:
    raw = _obj(price).get("amount")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None


def _address(external_id: Any, part: str, fields: dict[str, Any]) -> Address | None:
    if not any(value is not None for value in fields.values()):
        return None
    return _build(Address, external_id, part, fields)


def _tax_id(company: dict[str, Any]) -> str | None:
    # `ids` replaces the deprecated `taxId`; each id carries its own type
    # (PL_NIP, VAT_EU, ...), and the first is the one the buyer gave
    ids = company.get("ids")
    for company_id in ids if isinstance(ids, list) else []:
        value = _text(_obj(company_id).get("value"))
        if value:
            return value
    return _text(company.get("taxId"))


def map_shipment(order_id: Any, raw: dict[str, Any]) -> ShipmentCreate | None:
    """One entry of GET /order/checkout-forms/{id}/shipments, or None without a waybill."""
    return _build(
        ShipmentCreate,
        order_id,
        "shipment",
        {
            "external_id": _text(raw.get("id")),
            "carrier_id": _text(raw.get("carrierId")),
            "carrier_name": _text(raw.get("carrierName")),
            "waybill": _text(raw.get("waybill")),
            "shipped_at": _text(raw.get("createdAt")),
        },
    )


def _moment(raw: Any) -> datetime | None:
    """An Allegro timestamp as an aware UTC datetime, or None if unreadable."""
    text = _text(raw)
    if text is None:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(UTC)


# "Pobranie opłat z wpływów": Allegro taking its fees out of the proceeds
SETTLEMENT_TYPES = frozenset({"PAD"})


def map_billing_entry(raw: dict[str, Any]) -> BillingEntryCreate | None:
    """One item of GET /billing/billing-entries, or None if it cannot be used.

    Without an id, a type, an amount or a time there is nothing to keep; the
    order and offer are optional, since only some types name them.
    """
    entry_type = _obj(raw.get("type"))
    value = _obj(raw.get("value"))
    occurred_at = _moment(raw.get("occurredAt"))
    entry_id = _text(raw.get("id"))
    if entry_id is None or occurred_at is None:
        return None
    return _build(
        BillingEntryCreate,
        entry_id,
        "billing entry",
        {
            "source": OrderSource.ALLEGRO,
            "external_id": entry_id,
            "occurred_at": occurred_at,
            "type_id": _text(entry_type.get("id")),
            "type_name": _text(entry_type.get("name")),
            "amount": _text(value.get("amount")),
            "currency": _text(value.get("currency")),
            "order_external_id": _text(_obj(raw.get("order")).get("id")),
            "offer_id": _text(_obj(raw.get("offer")).get("id")),
            "offer_name": _text(_obj(raw.get("offer")).get("name")),
            "is_settlement": _text(entry_type.get("id")) in SETTLEMENT_TYPES,
        },
    )


# a payout to the seller's bank, and its cancelling, which gives the money back
PAYOUT_TYPES = {"PAYOUT": 1, "PAYOUT_CANCEL": -1}


def map_payout_operation(raw: dict[str, Any]) -> PayoutCreate | None:
    """A payout (or its cancelling) from GET /payments/payment-operations, or None.

    Only `PAYOUT` and `PAYOUT_CANCEL` are payouts; other operations of the
    group are not. A payout is stored by `payout.id`, positive; its cancelling
    by the same id marked `:cancel`, negative, so the two cancel out.
    """
    sign = PAYOUT_TYPES.get(_text(raw.get("type")) or "")
    payout_id = _text(_obj(raw.get("payout")).get("id"))
    paid_at = _moment(raw.get("occurredAt"))
    value = _obj(raw.get("value"))
    try:
        amount = abs(Decimal(_text(value.get("amount")) or ""))
    except InvalidOperation:
        return None
    if sign is None or payout_id is None or paid_at is None:
        return None
    return _build(
        PayoutCreate,
        payout_id,
        "payout",
        {
            "source": OrderSource.ALLEGRO,
            "external_id": payout_id if sign > 0 else f"{payout_id}:cancel",
            "paid_at": paid_at,
            "amount": amount * sign,
            "currency": _text(value.get("currency")) or "PLN",
            "operator": _text(_obj(raw.get("wallet")).get("paymentOperator")),
        },
    )


def map_payment_operation(raw: dict[str, Any]) -> PaymentOperationCreate | None:
    """Any operation of GET /payments/payment-operations, or None when it lacks what makes one.

    Allegro gives an operation no id, so it is kept by a fingerprint: a hash of its type, group,
    time, wallet (operator, type and the balance after it), value and what it concerns (payment,
    payout, surcharge). Reading the same operation again gives the same fingerprint; two different
    ones would have to agree on all of it, the wallet's balance after them included.
    """
    kind = _text(raw.get("type"))
    group = _text(raw.get("group"))
    occurred = _text(raw.get("occurredAt"))
    occurred_at = _moment(occurred)
    value = _obj(raw.get("value"))
    wallet = _obj(raw.get("wallet"))
    balance = _obj(wallet.get("balance"))
    try:
        amount = Decimal(_text(value.get("amount")) or "")
    except InvalidOperation:
        return None
    if kind is None or group is None or occurred_at is None:
        return None
    payment_id = _text(_obj(raw.get("payment")).get("id"))
    payout_id = _text(_obj(raw.get("payout")).get("id"))
    surcharge_id = _text(_obj(raw.get("surcharge")).get("id"))
    wallet_balance = _amount(wallet.get("balance")) if balance else None
    identity = [
        kind, group, occurred, _text(wallet.get("paymentOperator")), _text(wallet.get("type")),
        _text(balance.get("amount")), _text(value.get("amount")), _text(value.get("currency")),
        payment_id, payout_id, surcharge_id,
    ]
    fingerprint = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return _build(
        PaymentOperationCreate,
        payment_id or payout_id or kind,
        "payment operation",
        {
            "source": OrderSource.ALLEGRO,
            "fingerprint": fingerprint,
            "type": kind,
            "group": group,
            "occurred_at": occurred_at,
            "amount": amount,
            "currency": _text(value.get("currency")) or "PLN",
            "wallet_operator": _text(wallet.get("paymentOperator")),
            "wallet_type": _text(wallet.get("type")),
            "wallet_balance": wallet_balance,
            "payment_id": payment_id,
            "payout_id": payout_id,
            "surcharge_id": surcharge_id,
            "marketplace_id": _text(raw.get("marketplaceId")),
        },
    )


def map_tracking(raw: dict[str, Any]) -> tuple[str, datetime | None] | None:
    """The latest tracking status code, and when it was reported, of one waybill.

    `raw` is an item of the tracking response's `waybills`. None when the
    carrier has reported nothing, which is the case for carriers Allegro
    cannot follow.
    """
    details = _obj(raw.get("trackingDetails"))
    statuses = [_obj(s) for s in details.get("statuses") or [] if isinstance(s, dict)]
    statuses = [s for s in statuses if _text(s.get("code"))]
    if not statuses:
        return None
    # ISO timestamps in one format sort as text; an entry without a time sorts first
    latest = max(statuses, key=lambda s: _text(s.get("occurredAt")) or "")
    code = _text(latest.get("code"))
    assert code is not None
    return code[:32], _moment(latest.get("occurredAt")) or _moment(details.get("updatedAt"))


def _extra_payments(external_id: Any, checkout_form: dict[str, Any]) -> list[ExtraPayment]:
    """The order's surcharges and the cash collected on its delivery, each as a payment.

    A surcharge has the main payment's shape (`id`, `type`, `provider`, `paidAmount`,
    `finishedAt`); a cash payment `paymentId`, `paidAmount` and `paidAt`. One that cannot be read
    is left out and logged, like any other detail.
    """
    payments: list[ExtraPayment] = []
    surcharges = checkout_form.get("surcharges")
    for index, raw in enumerate(surcharges if isinstance(surcharges, list) else []):
        raw = _obj(raw)
        raw_type = _text(raw.get("type"))
        paid = _obj(raw.get("paidAmount"))
        payment = _build(
            ExtraPayment,
            external_id,
            f"surcharge {index + 1}",
            {
                "kind": OrderPaymentKind.SURCHARGE,
                "external_id": _text(raw.get("id")),
                "payment_type": _PAYMENT_TYPES.get(raw_type, PaymentType.OTHER) if raw_type else None,
                "provider": _text(raw.get("provider")),
                "paid_amount": _amount(raw.get("paidAmount")),
                "currency": _text(paid.get("currency")),
                "paid_at": _text(raw.get("finishedAt")),
            },
        )
        if payment is not None:
            payments.append(payment)
    cod = checkout_form.get("codBookedPayments")
    for index, raw in enumerate(cod if isinstance(cod, list) else []):
        raw = _obj(raw)
        paid = _obj(raw.get("paidAmount"))
        payment = _build(
            ExtraPayment,
            external_id,
            f"cash on delivery payment {index + 1}",
            {
                "kind": OrderPaymentKind.CASH_ON_DELIVERY,
                "external_id": _text(raw.get("paymentId")),
                "payment_type": PaymentType.CASH_ON_DELIVERY,
                "paid_amount": _amount(raw.get("paidAmount")),
                "currency": _text(paid.get("currency")),
                "paid_at": _text(raw.get("paidAt")),
            },
        )
        if payment is not None:
            payments.append(payment)
    return payments


def map_details(checkout_form: dict[str, Any]) -> OrderDetails:
    """Buyer, line items, delivery, payment and invoice of a checkout form.

    Never raises: unlike the fields map_checkout_form requires, a detail that
    cannot be read is left out and logged, and the order is still imported.
    """
    external_id = checkout_form.get("id")

    buyer = _obj(checkout_form.get("buyer"))
    customer = _build(
        Customer,
        external_id,
        "buyer",
        {
            "login": _text(buyer.get("login")),
            "first_name": _text(buyer.get("firstName")),
            "last_name": _text(buyer.get("lastName")),
            "company_name": _text(buyer.get("companyName")),
            "phone": _text(buyer.get("phoneNumber")),
            "address": _address(
                external_id,
                "buyer address",
                {
                    "first_name": _text(buyer.get("firstName")),
                    "last_name": _text(buyer.get("lastName")),
                    "company_name": _text(buyer.get("companyName")),
                    "street": _text(_obj(buyer.get("address")).get("street")),
                    "postal_code": _text(_obj(buyer.get("address")).get("postCode")),
                    "city": _text(_obj(buyer.get("address")).get("city")),
                    "country_code": _text(_obj(buyer.get("address")).get("countryCode")),
                },
            ),
        },
    )

    items = []
    line_items = checkout_form.get("lineItems")
    for index, line_item in enumerate(line_items if isinstance(line_items, list) else []):
        line_item = _obj(line_item)
        offer = _obj(line_item.get("offer"))
        item = _build(
            OrderItemCreate,
            external_id,
            f"line item {index + 1}",
            {
                "external_id": _text(line_item.get("id")),
                "offer_id": _text(offer.get("id")),
                "sku": _text(_obj(offer.get("external")).get("id")),
                "name": _text(offer.get("name")),
                "quantity": line_item.get("quantity"),
                # `price` is what the buyer pays per unit; `originalPrice` is
                # before discounts
                "unit_price": _amount(line_item.get("price")),
                "tax_rate": _text(_obj(line_item.get("tax")).get("rate")),
                "tax_subject": _text(_obj(line_item.get("tax")).get("subject")),
                "tax_exemption": _text(_obj(line_item.get("tax")).get("exemption")),
            },
        )
        if item is not None:
            items.append(item)

    delivery = _obj(checkout_form.get("delivery"))
    delivery_address = _obj(delivery.get("address"))
    pickup = delivery.get("pickupPoint")
    pickup_point = None
    if isinstance(pickup, dict):
        pickup_address = _obj(pickup.get("address"))
        pickup_point = _build(
            PickupPoint,
            external_id,
            "pickup point",
            {
                "id": _text(pickup.get("id")),
                "name": _text(pickup.get("name")),
                "address": _address(
                    external_id,
                    "pickup point address",
                    {
                        "street": _text(pickup_address.get("street")),
                        "postal_code": _text(pickup_address.get("zipCode")),
                        "city": _text(pickup_address.get("city")),
                        "country_code": _text(pickup_address.get("countryCode")),
                    },
                ),
            },
        )
    delivery_details = _build(
        Delivery,
        external_id,
        "delivery",
        {
            "method": _text(_obj(delivery.get("method")).get("name")),
            "method_id": _text(_obj(delivery.get("method")).get("id")),
            "cost": _amount(delivery.get("cost")),
            "smart": delivery.get("smart") is True,
            "address": _address(
                external_id,
                "delivery address",
                {
                    "first_name": _text(delivery_address.get("firstName")),
                    "last_name": _text(delivery_address.get("lastName")),
                    "company_name": _text(delivery_address.get("companyName")),
                    "street": _text(delivery_address.get("street")),
                    "postal_code": _text(delivery_address.get("zipCode")),
                    "city": _text(delivery_address.get("city")),
                    "country_code": _text(delivery_address.get("countryCode")),
                    "phone": _text(delivery_address.get("phoneNumber")),
                },
            ),
            "pickup_point": pickup_point,
        },
    )

    payment = _obj(checkout_form.get("payment"))
    raw_payment_type = _text(payment.get("type"))
    payment_details = _build(
        Payment,
        external_id,
        "payment",
        {
            # a type Allegro adds later is still a payment, not a missing one
            "type": (
                _PAYMENT_TYPES.get(raw_payment_type, PaymentType.OTHER)
                if raw_payment_type
                else None
            ),
            "id": _text(payment.get("id")),
            "provider": _text(payment.get("provider")),
            "paid_amount": _amount(payment.get("paidAmount")),
            "paid_at": _text(payment.get("finishedAt")),
        },
    )
    extra_payments = _extra_payments(external_id, checkout_form)

    invoice = _obj(checkout_form.get("invoice"))
    invoice_address = _obj(invoice.get("address"))
    company = _obj(invoice_address.get("company"))
    person = _obj(invoice_address.get("naturalPerson"))
    invoice_details = Invoice(
        required=invoice.get("required") is True,
        # "Setting the value to null indicates a private purchase, while any other value
        # indicates a corporate purchase" (the specification); with no invoice address at all,
        # the order says neither
        is_company=(
            isinstance(invoice_address.get("company"), dict) if isinstance(invoice.get("address"), dict) else None
        ),
        vat_payer_status=_text(company.get("vatPayerStatus")),
        address=_address(
            external_id,
            "invoice address",
            {
                "first_name": _text(person.get("firstName")),
                "last_name": _text(person.get("lastName")),
                "company_name": _text(company.get("name")),
                "street": _text(invoice_address.get("street")),
                "postal_code": _text(invoice_address.get("zipCode")),
                "city": _text(invoice_address.get("city")),
                "country_code": _text(invoice_address.get("countryCode")),
                "tax_id": _tax_id(company),
            },
        ),
    )

    return OrderDetails(
        # the end of the window the seller must dispatch in; the start is
        # when it becomes possible, which nothing here needs
        dispatch_by=_moment(_obj(_obj(delivery.get("time")).get("dispatch")).get("to")),
        customer=customer or Customer(),
        items=items,
        delivery=delivery_details or Delivery(),
        payment=payment_details or Payment(),
        extra_payments=extra_payments,
        invoice=invoice_details,
        buyer_message=_shorten(
            "buyer message",
            external_id,
            checkout_form.get("messageToSeller"),
            BUYER_MESSAGE_MAX_LENGTH,
        ),
        seller_note=_shorten(
            "seller note",
            external_id,
            _obj(checkout_form.get("note")).get("text"),
            SELLER_NOTE_MAX_LENGTH,
        ),
    )


def _shorten(field_label: str, external_id: Any, value: Any, max_length: int) -> str | None:
    text = _text(value)
    if text is not None and len(text) > max_length:
        # shortened rather than dropped: the start of a note ("please ship by
        # Friday") is worth more than nothing
        logger.warning("Order %s: %s shortened to fit", external_id, field_label)
        text = text[: max_length - 1] + "…"
    return text


def map_checkout_form(checkout_form: dict[str, Any]) -> OrderCreate:
    """Convert one checkout form into an OrderCreate.

    Raises:
        OrderMappingError: if the payload lacks something the domain model
            requires. The caller can skip that one order rather than losing
            the whole batch.
    """
    external_id = checkout_form.get("id")
    if not external_id:
        raise OrderMappingError("checkout form has no id")

    email = _obj(checkout_form.get("buyer")).get("email")
    if not email:
        raise OrderMappingError(f"order {external_id} has no buyer email")

    # summary.totalToPay is the value of the whole order: line item prices are
    # per unit and exclude delivery, so they cannot be used as a total
    total = _obj(_obj(checkout_form.get("summary")).get("totalToPay"))
    amount = total.get("amount")
    currency = total.get("currency")
    if amount is None or not currency:
        raise OrderMappingError(f"order {external_id} has no summary.totalToPay")

    try:
        total_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError) as exc:
        raise OrderMappingError(
            f"order {external_id} has an unreadable amount: {amount!r}"
        ) from exc

    if total_amount <= 0:
        raise OrderMappingError(
            f"order {external_id} has a non-positive total: {total_amount}"
        )

    try:
        return OrderCreate(
            external_id=str(external_id),
            source=OrderSource.ALLEGRO,
            status=map_status(checkout_form),
            marketplace_status_label=map_status_label(checkout_form),
            customer_email=email,
            total_amount=total_amount,
            currency=currency,
            ordered_at=map_ordered_at(checkout_form),
            marketplace_updated_at=_moment(checkout_form.get("updatedAt")),
            **dict(map_details(checkout_form)),
        )
    except ValidationError as exc:
        # the domain model's own rules (email format, two decimal places,
        # three-letter currency) are stricter than the checks above; without
        # this the error escapes the adapter's per-order skip and loses the
        # whole page. Field names only: the values include buyer emails,
        # which do not belong in logs.
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        raise OrderMappingError(
            f"order {external_id} fails validation on: {', '.join(fields)}"
        ) from exc


# --- Message Center (INTEGRATIONS.md, "Buyer messages") ---------------------
#
# developer.allegro.pl was unreachable while this was built (the sandbox
# environment's network egress blocked it), so these field names come from
# Allegro's Message Center announcement and search-indexed excerpts of the
# tutorial, not a read of the published OpenAPI specification or a real
# response. Treat every name below as unconfirmed until one of those is
# checked. Confirmed by more than one source: GET /messaging/threads returns
# `threads: [{id, read, lastMessageDateTime, interlocutor: {login, ...}}]`,
# and POST /messaging/messages takes `{recipient: {login}, order: {id}, text,
# attachments}`. Unconfirmed: the exact shape of one entry of GET
# /messaging/threads/{id}/messages - assumed here to be `{id, text, createdAt,
# author: {login}}`, by analogy with the confirmed shapes above.


def map_thread(raw: dict[str, Any]) -> SyncedThread | None:
    """One entry of GET /messaging/threads, or None without an id.

    Read leniently, like every other mapper here: an unreadable interlocutor,
    order reference or read flag costs only that field, not the thread.
    """
    thread_id = _text(raw.get("id"))
    if thread_id is None:
        return None
    interlocutor = _obj(raw.get("interlocutor"))
    read = raw.get("read")
    return _build(
        SyncedThread,
        thread_id,
        "message thread",
        {
            "external_id": thread_id,
            "interlocutor_login": _text(interlocutor.get("login")),
            "order_external_id": _text(_obj(raw.get("order")).get("id")),
            "last_message_at": _text(raw.get("lastMessageDateTime")),
            "read": read if isinstance(read, bool) else True,
        },
        label="Thread",
    )


def map_message(raw: dict[str, Any], seller_login: str | None) -> SyncedMessage | None:
    """One entry of GET /messaging/threads/{id}/messages, or None if unusable.

    Allegro says which side wrote a message: `author.isInterlocutor` is true
    for the other party (the buyer) and false for the seller, whoever sent it
    from - the API or Allegro's own Message Center. That decides IN/OUT. A
    response without the flag falls back to comparing the author's login to
    the connected seller's own (read once when the account was connected,
    `account_login`, and passed in here); without either, a message maps as
    IN.
    """
    raw_text = _text(raw.get("text"))
    # the Message Center's text is HTML-escaped (`zam&oacute;wienie`)
    text_value = clean_marketplace_text(raw_text) if raw_text is not None else None
    if not text_value:
        return None
    message_id = _text(raw.get("id"))
    author = _obj(raw.get("author"))
    author_login = _text(author.get("login"))
    is_interlocutor = author.get("isInterlocutor")
    if isinstance(is_interlocutor, bool):
        from_seller = not is_interlocutor
    else:
        from_seller = bool(seller_login) and author_login == seller_login
    direction = MessageDirection.OUT if from_seller else MessageDirection.IN
    return _build(
        SyncedMessage,
        message_id or "?",
        "message",
        {
            "external_id": message_id,
            "direction": direction,
            "author_login": author_login,
            "text": text_value,
            "sent_at": _text(raw.get("createdAt")),
        },
        label="Message",
    )
