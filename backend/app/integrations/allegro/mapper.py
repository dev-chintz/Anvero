"""Translation from Allegro's checkout form into the Anvero domain shape.

Field names follow GET /order/checkout-forms. Nothing here leaks outside the
allegro package: callers receive OrderCreate.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.integrations.base import IntegrationError
from app.models.order import OrderSource, OrderStatus
from app.schemas.order import OrderCreate

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
    for item in checkout_form.get("lineItems") or []:
        raw = (item or {}).get("boughtAt")
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


def map_status(checkout_form: dict[str, Any]) -> OrderStatus:
    if checkout_form.get("status") == "CANCELLED":
        return OrderStatus.CANCELLED

    fulfillment = checkout_form.get("fulfillment") or {}
    mapped = _FULFILLMENT_TO_STATUS.get(fulfillment.get("status"))
    if mapped is not None:
        return mapped

    # an unknown value is better treated as new work than silently dropped
    return _CHECKOUT_STATUS_TO_STATUS.get(
        checkout_form.get("status"), OrderStatus.NEW
    )


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

    email = (checkout_form.get("buyer") or {}).get("email")
    if not email:
        raise OrderMappingError(f"order {external_id} has no buyer email")

    # summary.totalToPay is the value of the whole order: line item prices are
    # per unit and exclude delivery, so they cannot be used as a total
    total = (checkout_form.get("summary") or {}).get("totalToPay") or {}
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
            customer_email=email,
            total_amount=total_amount,
            currency=currency,
            ordered_at=map_ordered_at(checkout_form),
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
