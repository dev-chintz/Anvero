"""Translation from Allegro's checkout form into the Anvero domain shape.

Field names follow GET /order/checkout-forms. Nothing here leaks outside the
allegro package: callers receive OrderCreate.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.integrations.base import IntegrationError
from app.models.order import OrderSource, OrderStatus, PaymentType
from app.schemas.order import (
    BUYER_MESSAGE_MAX_LENGTH,
    SELLER_NOTE_MAX_LENGTH,
    Address,
    BillingEntryCreate,
    Customer,
    Delivery,
    Invoice,
    OrderCreate,
    OrderDetails,
    OrderItemCreate,
    Payment,
    PickupPoint,
    ShipmentCreate,
)

_Part = TypeVar("_Part", bound=BaseModel)

# Allegro tracks two axes. `status` covers the buying process and
# `fulfillment.status` covers physical handling, so the single Anvero status
# is derived from both. A cancelled order is cancelled whatever its parcel is
# doing, so that check comes first.
_FULFILLMENT_TO_STATUS = {
    "NEW": OrderStatus.NEW,
    "PROCESSING": OrderStatus.CONFIRMED,
    # packed but not yet handed to the carrier
    "READY_FOR_SHIPMENT": OrderStatus.CONFIRMED,
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


def _obj(value: Any) -> dict[str, Any]:
    """The value if it is a JSON object, otherwise an empty one.

    Details are read defensively: a malformed part costs that part, not the
    order.
    """
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    """A trimmed string, or None for anything absent, blank or not text."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    return str(value).strip() or None


def _amount(price: Any) -> Decimal | None:
    raw = _obj(price).get("amount")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None


def _build(model: type[_Part], external_id: Any, part: str, fields: dict) -> _Part | None:
    """Build one part of the details, keeping as much of it as is valid.

    An optional field that fails validation (a phone number longer than any
    real one, an unreadable date) is dropped and the rest kept. If a required
    field fails, such as a line item without a name, the part is dropped.
    Either way it is logged by field name only: the values are buyers'
    personal data, which do not belong in logs.
    """
    try:
        return model(**fields)
    except ValidationError as exc:
        bad = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
        required = [name for name in bad if model.model_fields[name].is_required()]
        if required:
            logger.warning(
                "Order %s: skipping %s, unreadable %s",
                external_id,
                part,
                ", ".join(required),
            )
            return None
        logger.warning(
            "Order %s: ignoring unreadable %s in %s", external_id, ", ".join(bad), part
        )
        return model(**{k: v for k, v in fields.items() if k not in bad})


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
            "cost": _amount(delivery.get("cost")),
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
            "provider": _text(payment.get("provider")),
            "paid_amount": _amount(payment.get("paidAmount")),
            "paid_at": _text(payment.get("finishedAt")),
        },
    )

    invoice = _obj(checkout_form.get("invoice"))
    invoice_address = _obj(invoice.get("address"))
    company = _obj(invoice_address.get("company"))
    person = _obj(invoice_address.get("naturalPerson"))
    invoice_details = Invoice(
        required=invoice.get("required") is True,
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
        customer=customer or Customer(),
        items=items,
        delivery=delivery_details or Delivery(),
        payment=payment_details or Payment(),
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
