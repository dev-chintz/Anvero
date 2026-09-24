"""Translation from an Erli order into the Anvero domain shape.

Field names follow Erli's OpenAPI description of `Order` (POST
/orders/_search, GET /orders/{id}); none has been seen in a real response
yet. Nothing here leaks outside the erli package: callers receive OrderCreate.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.integrations.base import IntegrationError
from app.integrations.mapping import build, obj, text
from app.models.order import OrderSource, OrderStatus, PaymentType
from app.schemas.order import (
    BUYER_MESSAGE_MAX_LENGTH,
    Address,
    Customer,
    Delivery,
    Invoice,
    OrderCreate,
    OrderItemCreate,
    Payment,
    PickupPoint,
    ShipmentCreate,
)

logger = logging.getLogger(__name__)

# Erli's own `status` covers buying: pending (not paid yet), purchased (paid,
# or cash on delivery), cancelled, returned. Handling is in two other fields:
# the parcel's `deliveryTracking.status`, and `sellerStatus`, which the seller
# sets. The most specific that says anything wins, parcel first.
_TRACKING_TO_STATUS = {
    "preparing": OrderStatus.CONFIRMED,
    "readyToSend": OrderStatus.READY_FOR_SHIPMENT,
    "waitingForCourier": OrderStatus.READY_FOR_SHIPMENT,
    "sent": OrderStatus.SHIPPED,
    "readyToPickup": OrderStatus.SHIPPED,
    "pickupTimeExpired": OrderStatus.SHIPPED,
    "deliveryUnsuccessful": OrderStatus.SHIPPED,
    "redirected": OrderStatus.SHIPPED,
    "delivered": OrderStatus.DELIVERED,
    # the parcel came back; Anvero has no status for that, so the label keeps it
    "returned": OrderStatus.DELIVERED,
}

_SELLER_STATUS_TO_STATUS = {
    "created": OrderStatus.NEW,
    "readyToProcess": OrderStatus.NEW,
    "inProgress": OrderStatus.CONFIRMED,
    "sent": OrderStatus.SHIPPED,
    "readyToPickup": OrderStatus.SHIPPED,
    "returningToSender": OrderStatus.SHIPPED,
    "received": OrderStatus.DELIVERED,
    "returned": OrderStatus.DELIVERED,
    "canceled": OrderStatus.CANCELLED,
}

# the carrier's position in Anvero's tracking codes (DATABASE.md)
_TRACKING_CODES = {
    "sent": "IN_TRANSIT",
    "redirected": "IN_TRANSIT",
    "readyToPickup": "AVAILABLE_FOR_PICKUP",
    "pickupTimeExpired": "ISSUE",
    "deliveryUnsuccessful": "ISSUE",
    "delivered": "DELIVERED",
    "returned": "RETURNED",
}

# An order is sometimes returned before Erli has assigned the buyer's proxy
# email. Anvero requires one, and skipping the order would hide it until it
# next changes, so it gets a stand-in on a subdomain that receives no mail;
# the next import that sees the real address replaces it.
NO_EMAIL_DOMAIN = "no-email-yet.erli.pl"


class OrderMappingError(IntegrationError):
    """An Erli order could not be expressed as an Anvero order."""


def _grosze(value: Any) -> Decimal | None:
    """An Erli amount, in grosze (integer), as złoty."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return Decimal(value) / 100


def _moment(raw: Any) -> datetime | None:
    value = text(raw)
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(UTC)


def _street(address: dict[str, Any]) -> str | None:
    """The street line: Erli's own `address` line, else built from its parts."""
    line = text(address.get("address"))
    if line:
        return line
    street = text(address.get("street"))
    number = text(address.get("buildingNumber"))
    flat = text(address.get("flatNumber"))
    if not street:
        return None
    house = f"{number}/{flat}" if number and flat else number
    return f"{street} {house}" if house else street


def map_status(order: dict[str, Any]) -> tuple[OrderStatus, str | None]:
    """Anvero's status, and Erli's own word it was read from (the label)."""
    status = text(order.get("status"))
    if status == "cancelled":
        return OrderStatus.CANCELLED, status
    if status == "returned":
        # the goods went out and came back: past handling, whatever the
        # seller's own status still says, so it cannot fall back into the
        # to-make queue; Anvero has no "returned", the label keeps it
        return OrderStatus.DELIVERED, status
    tracking = text(obj(order.get("deliveryTracking")).get("status"))
    if tracking in _TRACKING_TO_STATUS:
        return _TRACKING_TO_STATUS[tracking], tracking
    seller_status = text(order.get("sellerStatus"))
    if seller_status in _SELLER_STATUS_TO_STATUS:
        return _SELLER_STATUS_TO_STATUS[seller_status], seller_status
    # unpaid, just paid, or something new: all of it is still work to do
    return OrderStatus.NEW, status


def _payment(order: dict[str, Any], total: Decimal) -> Payment:
    """Paid, owed after delivery, or known to be unpaid.

    Erli collects the money itself; its payment status says whether it has.
    """
    delivery = obj(order.get("delivery"))
    if delivery.get("cod") is True:
        return Payment(type=PaymentType.CASH_ON_DELIVERY)
    paid = text(obj(order.get("payment")).get("status")) == "COMPLETED" or text(
        order.get("status")
    ) in ("purchased", "returned")
    return Payment(
        type=PaymentType.ONLINE,
        provider="ERLI",
        paid_amount=total if paid else Decimal("0.00"),
        paid_at=_moment(order.get("purchasedAt")) if paid else None,
    )


def map_order(order: dict[str, Any]) -> OrderCreate:
    """Convert one Erli order into an OrderCreate.

    Raises:
        OrderMappingError: if it lacks what an Anvero order requires (an id,
            a positive total, a currency). The caller skips that one order.
    """
    external_id = text(order.get("id"))
    if external_id is None:
        raise OrderMappingError("Erli order has no id")
    total = _grosze(order.get("totalPrice"))
    if total is None or total <= 0:
        raise OrderMappingError(f"Erli order {external_id} has no positive totalPrice")
    currency = text(order.get("currency")) or "PLN"

    user = obj(order.get("user"))
    email = text(user.get("email")) or f"order-{external_id}@{NO_EMAIL_DOMAIN}"
    delivery_address = obj(user.get("deliveryAddress"))
    invoice_address = obj(user.get("invoiceAddress"))
    delivery = obj(order.get("delivery"))
    pickup = obj(delivery.get("pickupPlace"))
    tracking = obj(order.get("deliveryTracking"))
    status, label = map_status(order)

    items = []
    raw_items = order.get("items")
    for index, raw in enumerate(raw_items if isinstance(raw_items, list) else []):
        raw = obj(raw)
        item = build(
            OrderItemCreate,
            external_id,
            f"item {index + 1}",
            {
                "external_id": text(raw.get("id")),
                # the seller's own product id on Erli, which the listing is
                "offer_id": text(raw.get("externalId")),
                "sku": text(raw.get("sku")),
                "name": text(raw.get("name")),
                "quantity": raw.get("quantity"),
                # after any rebate; unitPriceBeforeRebate is the list price
                "unit_price": _grosze(raw.get("unitPrice")),
            },
        )
        if item is not None:
            items.append(item)

    pickup_point = None
    if pickup:
        pickup_point = build(
            PickupPoint,
            external_id,
            "pickup point",
            {
                "id": text(pickup.get("externalId")) or text(pickup.get("id")),
                "name": text(pickup.get("name")) or text(pickup.get("heading")),
                "address": build(
                    Address,
                    external_id,
                    "pickup point address",
                    {
                        "street": text(pickup.get("address")),
                        "postal_code": text(pickup.get("zip")),
                        "city": text(pickup.get("city")),
                        "country_code": (text(pickup.get("country")) or "").upper() or None,
                    },
                ),
            },
        )

    shipments = None
    waybill = text(tracking.get("trackingNumber"))
    if waybill:
        shipment = build(
            ShipmentCreate,
            external_id,
            "shipment",
            {
                "carrier_id": text(tracking.get("vendor")),
                "waybill": waybill,
                "tracking_status": _TRACKING_CODES.get(text(tracking.get("status")) or ""),
            },
        )
        shipments = [shipment] if shipment is not None else None

    invoice = Invoice(
        required=bool(invoice_address),
        address=build(
            Address,
            external_id,
            "invoice address",
            {
                "first_name": text(invoice_address.get("firstName")),
                "last_name": text(invoice_address.get("lastName")),
                "company_name": text(invoice_address.get("companyName")),
                "street": _street(invoice_address),
                "postal_code": text(invoice_address.get("zip")),
                "city": text(invoice_address.get("city")),
                "country_code": (text(invoice_address.get("country")) or "").upper() or None,
                "tax_id": text(invoice_address.get("nip")),
            },
        )
        if invoice_address
        else None,
    )

    comment = text(order.get("comment"))
    if comment and len(comment) > BUYER_MESSAGE_MAX_LENGTH:
        logger.warning("Order %s: buyer message shortened to fit", external_id)
        comment = comment[: BUYER_MESSAGE_MAX_LENGTH - 1] + "…"

    try:
        return OrderCreate(
            external_id=external_id,
            source=OrderSource.ERLI,
            status=status,
            marketplace_status_label=label[:64] if label else None,
            customer_email=email,
            total_amount=total,
            currency=currency,
            ordered_at=_moment(order.get("purchasedAt")) or _moment(order.get("created")),
            marketplace_updated_at=_moment(order.get("updated")),
            # Erli names no buyer apart from the delivery address
            customer=build(
                Customer,
                external_id,
                "buyer",
                {
                    "first_name": text(delivery_address.get("firstName")),
                    "last_name": text(delivery_address.get("lastName")),
                    "company_name": text(delivery_address.get("companyName")),
                    "phone": text(delivery_address.get("phone")),
                },
            )
            or Customer(),
            items=items,
            delivery=build(
                Delivery,
                external_id,
                "delivery",
                {
                    "method": text(delivery.get("name")),
                    "cost": _grosze(delivery.get("price")),
                    "address": build(
                        Address,
                        external_id,
                        "delivery address",
                        {
                            "first_name": text(delivery_address.get("firstName")),
                            "last_name": text(delivery_address.get("lastName")),
                            "company_name": text(delivery_address.get("companyName")),
                            "street": _street(delivery_address),
                            "postal_code": text(delivery_address.get("zip")),
                            "city": text(delivery_address.get("city")),
                            "country_code": (
                                text(delivery_address.get("country")) or ""
                            ).upper()
                            or None,
                            "phone": text(delivery_address.get("phone")),
                        },
                    )
                    if delivery_address
                    else None,
                    "pickup_point": pickup_point,
                },
            )
            or Delivery(),
            payment=_payment(order, total),
            invoice=invoice,
            buyer_message=comment,
            shipments=shipments,
        )
    except ValidationError as exc:
        # field names only: the values include buyers' addresses
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        raise OrderMappingError(
            f"Erli order {external_id} fails validation on: {', '.join(fields)}"
        ) from exc
