"""Parcel locker shipments made at InPost from Anvero, and their labels.

Making a shipment costs money under the seller's InPost contract and sends a real
parcel on its way, so it goes through MarketplaceWriter (safe mode holds it back like
any other write) and an order has at most one shipment that is not cancelled. InPost
buys asynchronously: `create` waits a few seconds for the tracking number, and a
shipment still without one is settled by `refresh`. Once InPost has a number it is
put on the order as an ordinary shipment, which also sends it to Allegro through
OrderWrites (safe mode again), so the buyer can follow the parcel.

Built from InPost's documentation and tested on fakes; nothing has been made for real
(docs/INTEGRATIONS.md, "InPost").
"""

import logging
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.order_number import format_order_number
from app.integrations.base import IntegrationError
from app.integrations.inpost.client import InpostClient
from app.models.inpost_shipment import InpostShipment
from app.models.marketplace_write import WriteOutcome
from app.models.order import AddressType, Order, OrderStatus, PaymentType
from app.services.inpost_settings import build_inpost_client, get_settings
from app.services.marketplace_writes import MarketplaceWriter, WriteResult
from app.services.order_writes import OrderWrites

logger = logging.getLogger(__name__)

# how long `create` waits for InPost to buy the shipment before leaving it for `refresh`
SETTLE_ATTEMPTS = 8
SETTLE_INTERVAL_SECONDS = 1.0

SERVICE = "inpost_locker_standard"

# InPost's words for a shipment that is no more
_CANCELLED = frozenset({"cancelled", "canceled"})

# orders for which a parcel is still to be made
_OPEN_STATUSES = (OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.READY_FOR_SHIPMENT)

ClientFactory = Callable[[], InpostClient]


class InpostRefused(Exception):
    """A parcel cannot be made for this order as things stand; the message says why,
    for the operator."""


@dataclass(frozen=True)
class BulkOutcome:
    """What became of one order in a batch."""

    order: Order
    # created, held_back (safe mode), refused (Anvero would not ask) or failed (InPost said no)
    outcome: str
    message: str | None = None
    shipment: InpostShipment | None = None


@dataclass(frozen=True)
class CreateOutcome:
    shipment: InpostShipment | None
    write: WriteResult
    # the tracking number as it went to Allegro, once there was one
    tracking_write: WriteResult | None = None


def _digits(phone: str | None) -> str:
    """A Polish mobile number as InPost wants it: nine digits, no country code."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("48"):
        digits = digits[2:]
    return digits


def _delivery_address(order: Order):
    return next((a for a in order.addresses if a.type is AddressType.DELIVERY), None)


def receiver_of(order: Order) -> dict[str, str]:
    """Who the parcel is for, from the order's delivery address and the buyer."""
    address = _delivery_address(order)
    first = (address.first_name if address else None) or order.customer_first_name or ""
    last = (address.last_name if address else None) or order.customer_last_name or ""
    phone = _digits((address.phone if address else None) or order.customer_phone)
    return {
        "first_name": first.strip(),
        "last_name": last.strip(),
        "email": (order.customer_email or "").strip(),
        "phone": phone,
    }


def buyer_name(order: Order) -> str | None:
    receiver = receiver_of(order)
    name = f"{receiver['first_name']} {receiver['last_name']}".strip()
    return name or order.customer_login or order.customer_email


def is_inpost_locker(order: Order) -> bool:
    """A delivery to an InPost locker, by the method's name and a locker to take it to."""
    method = (order.delivery_method or "").lower()
    return "inpost" in method and bool(order.pickup_point_id)


def refusal(order: Order, existing: list[InpostShipment]) -> str | None:
    """Why a parcel is not made for this order, in words for the operator; None if it can be."""
    if order.deleted_at is not None:
        return "The order is deleted; restore it first"
    if order.status is OrderStatus.CANCELLED or order.marketplace_cancelled_at is not None:
        return "The order is cancelled"
    if order.payment_type == PaymentType.CASH_ON_DELIVERY:
        return "Cash on delivery is not supported: the business does not ship it"
    if not is_inpost_locker(order):
        return "This is not a delivery to an InPost parcel locker (a courier delivery cannot be made here yet)"
    if any(s.status not in _CANCELLED for s in existing):
        return "The order already has an InPost shipment; cancel it before making another"
    if order.shipments:
        numbers = ", ".join(s.waybill for s in order.shipments)
        return f"The order already has a tracking number ({numbers}), made elsewhere"
    receiver = receiver_of(order)
    missing = [
        label
        for label, value in (
            ("first name", receiver["first_name"]),
            ("last name", receiver["last_name"]),
            ("e-mail", receiver["email"]),
            ("phone number", receiver["phone"]),
        )
        if not value
    ]
    if missing:
        return f"The order lacks the receiver's {', '.join(missing)}"
    if len(receiver["phone"]) != 9:
        return f"The phone number {receiver['phone']} is not a nine-digit Polish number, which InPost needs"
    return None


def shipment_input(order: Order, template: str) -> dict[str, Any]:
    """The body of the request to make one locker shipment (ShipX's simplified mode:
    a service and a size, no dimensions)."""
    return {
        "receiver": receiver_of(order),
        "parcels": {"template": template},
        "service": SERVICE,
        "custom_attributes": {"target_point": order.pickup_point_id},
        "reference": format_order_number(order.order_number),
    }


class InpostShipments:
    def __init__(self, db: Session, client_factory: ClientFactory | None = None):
        self.db = db
        self._client_factory = client_factory or (lambda: build_inpost_client(db))
        self.writer = MarketplaceWriter(db)

    # ---- reading ---------------------------------------------------------------------

    def for_order(self, order: Order) -> list[InpostShipment]:
        return list(
            self.db.scalars(
                select(InpostShipment)
                .where(InpostShipment.order_id == order.id)
                .order_by(InpostShipment.created_at.desc())
            )
        )

    def get(self, order: Order, shipment_id: uuid.UUID) -> InpostShipment | None:
        shipment = self.db.get(InpostShipment, shipment_id)
        return shipment if shipment is not None and shipment.order_id == order.id else None

    def awaiting_parcel(self, limit: int = 200) -> list[Order]:
        """Orders a locker parcel could be made for now, most urgent first.

        An InPost locker delivery still to be made, with no tracking number and no
        InPost shipment that is not cancelled: what was made elsewhere (the Manager
        Paczek) is left alone.
        """
        made = select(InpostShipment.order_id).where(InpostShipment.status.notin_(_CANCELLED))
        orders = self.db.scalars(
            select(Order)
            .options(joinedload(Order.addresses))
            .where(
                Order.deleted_at.is_(None),
                Order.marketplace_cancelled_at.is_(None),
                Order.status.in_(_OPEN_STATUSES),
                Order.pickup_point_id.is_not(None),
                Order.delivery_method.ilike("%inpost%"),
                Order.id.notin_(made),
            )
            .order_by(Order.dispatch_by.asc().nullslast(), Order.ordered_at)
            .limit(limit)
        ).unique()
        return [o for o in orders if not o.shipments and o.payment_type != PaymentType.CASH_ON_DELIVERY]

    def printable(self, printed: bool | None = False, limit: int = 200) -> list[InpostShipment]:
        """Shipments that have a tracking number, oldest first, so a day's print run
        comes out in the order the parcels were made. `printed=False`: not yet
        printed; `True`: printed; `None`: every one."""
        query = (
            select(InpostShipment)
            .options(joinedload(InpostShipment.order))
            .where(InpostShipment.tracking_number.is_not(None), InpostShipment.status.notin_(_CANCELLED))
            .order_by(InpostShipment.created_at)
            .limit(limit)
        )
        if printed is False:
            query = query.where(InpostShipment.printed_at.is_(None))
        elif printed is True:
            query = query.where(InpostShipment.printed_at.is_not(None))
        return list(self.db.scalars(query))

    # ---- making one ---------------------------------------------------------------------

    def create(
        self, order: Order, template: str | None, user_id: int | None, wait: bool = True
    ) -> CreateOutcome:
        """Make the order's parcel; the shipment, or None when nothing was made.

        Raises InpostRefused when it cannot be asked for at all. InPost's own refusal
        comes back as a FAILED write.
        """
        reason = refusal(order, self.for_order(order))
        if reason is not None:
            raise InpostRefused(reason)
        settings = get_settings(self.db)
        if not settings.configured:
            raise InpostRefused("Enter the InPost token and organization in Settings first")
        size = template or settings.default_template

        payload = shipment_input(order, size)
        client = self._client_factory()
        result = self.writer.write(
            order.source,
            "inpost_shipment",
            payload,
            lambda: client.create_shipment(payload),
            order_id=order.id,
            user_id=user_id,
            raise_errors=False,
        )
        self.db.refresh(order)
        if result.outcome is not WriteOutcome.SENT:
            return CreateOutcome(None, result)

        answer = result.response if isinstance(result.response, dict) else {}
        inpost_id = answer.get("id")
        if inpost_id is None:
            # sent, but InPost's answer holds nothing to find the shipment by
            logger.error("InPost accepted a shipment for order %s but returned no id", order.id)
            return CreateOutcome(None, result)
        shipment = InpostShipment(
            order_id=order.id,
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            inpost_id=str(inpost_id),
            status=str(answer.get("status") or "created"),
            tracking_number=answer.get("tracking_number") or None,
            target_point=str(order.pickup_point_id),
            template=size,
            reference=payload["reference"],
        )
        self.db.add(shipment)
        self.db.commit()
        tracking_write = self._attach_tracking(order, shipment, user_id) if shipment.tracking_number else None
        if shipment.tracking_number is None and wait:
            tracking_write = self._settle(order, shipment, client, user_id)
        return CreateOutcome(shipment, result, tracking_write)

    def create_many(
        self, orders: list[Order], template: str | None, user_id: int | None
    ) -> list[BulkOutcome]:
        """Make a parcel for each order, then wait for InPost's numbers together.

        One order's refusal or failure leaves the others alone. The waiting is shared:
        every shipment is asked about in each round, instead of the batch waiting
        several seconds per order.
        """
        outcomes: list[BulkOutcome] = []
        pending: list[tuple[Order, InpostShipment]] = []
        for order in orders:
            try:
                made = self.create(order, template, user_id, wait=False)
            except InpostRefused as exc:
                outcomes.append(BulkOutcome(order, "refused", str(exc)))
                continue
            except IntegrationError as exc:
                outcomes.append(BulkOutcome(order, "failed", str(exc)))
                continue
            if made.shipment is None:
                held = made.write.outcome is WriteOutcome.DRY_RUN
                message = None if held else (made.write.record.detail or "InPost did not make it")
                outcomes.append(BulkOutcome(order, "held_back" if held else "failed", message))
                continue
            outcomes.append(BulkOutcome(order, "created", None, made.shipment))
            if made.shipment.tracking_number is None:
                pending.append((order, made.shipment))

        client = self._client_factory() if pending else None
        for _ in range(SETTLE_ATTEMPTS if pending else 0):
            time.sleep(SETTLE_INTERVAL_SECONDS)
            still = []
            for order, shipment in pending:
                try:
                    self._update_from(shipment, client.get_shipment(shipment.inpost_id))  # type: ignore[union-attr]
                except IntegrationError as exc:
                    logger.warning("Could not look at InPost shipment %s yet: %s", shipment.inpost_id, exc)
                    still.append((order, shipment))
                    continue
                self.db.commit()
                if shipment.tracking_number:
                    self._attach_tracking(order, shipment, user_id)
                elif shipment.status not in _CANCELLED:
                    still.append((order, shipment))
            pending = still
            if not pending:
                break
        return outcomes

    def refresh(self, order: Order, shipment: InpostShipment, user_id: int | None) -> WriteResult | None:
        """Ask InPost once more about a shipment: its status, and its number if it has one now."""
        had_number = shipment.tracking_number is not None
        self._update_from(shipment, self._client_factory().get_shipment(shipment.inpost_id))
        self.db.commit()
        if shipment.tracking_number and not had_number:
            return self._attach_tracking(order, shipment, user_id)
        return None

    def _settle(
        self, order: Order, shipment: InpostShipment, client: InpostClient, user_id: int | None
    ) -> WriteResult | None:
        for _ in range(SETTLE_ATTEMPTS):
            time.sleep(SETTLE_INTERVAL_SECONDS)
            try:
                self._update_from(shipment, client.get_shipment(shipment.inpost_id))
            except Exception as exc:  # noqa: BLE001 - a failed look leaves it for refresh
                logger.warning("Could not look at InPost shipment %s yet: %s", shipment.inpost_id, exc)
                continue
            self.db.commit()
            if shipment.tracking_number or shipment.status in _CANCELLED:
                break
        if shipment.tracking_number:
            return self._attach_tracking(order, shipment, user_id)
        return None

    @staticmethod
    def _update_from(shipment: InpostShipment, answer: dict[str, Any]) -> None:
        shipment.status = str(answer.get("status") or shipment.status)
        number = answer.get("tracking_number")
        if number:
            shipment.tracking_number = str(number)

    def _attach_tracking(
        self, order: Order, shipment: InpostShipment, user_id: int | None
    ) -> WriteResult | None:
        """Put the number on the order as a shipment and hand it to Allegro (safe mode permitting)."""
        number = shipment.tracking_number
        if not number or any(s.waybill == number for s in order.shipments):
            return None
        _, write = OrderWrites(self.db).add_shipment(order, "INPOST", None, number, user_id)
        return write

    # ---- cancelling ----------------------------------------------------------------------

    def cancel(self, order: Order, shipment: InpostShipment, user_id: int | None) -> WriteResult:
        """Cancel the shipment at InPost, which allows it until it has taken the parcel."""
        if shipment.status in _CANCELLED:
            raise InpostRefused("The shipment is already cancelled")
        client = self._client_factory()
        result = self.writer.write(
            order.source,
            "inpost_cancel",
            {"shipment": shipment.inpost_id},
            lambda: client.cancel_shipment(shipment.inpost_id),
            order_id=order.id,
            user_id=user_id,
            raise_errors=False,
        )
        self.db.refresh(order)
        self.db.refresh(shipment)
        if result.outcome is WriteOutcome.SENT:
            shipment.status = "cancelled"
            shipment.error = None
        elif result.outcome is WriteOutcome.FAILED:
            shipment.error = (result.record.detail or "InPost did not cancel it")[:1000]
        self.db.commit()
        return result

    # ---- printing --------------------------------------------------------------------------

    def pdf_many(self, shipment_ids: list[uuid.UUID]) -> bytes:
        """The labels asked for, in that order, as one A6 PDF; notes them printed."""
        if not shipment_ids:
            raise InpostRefused("Choose at least one label")
        found = {
            s.id: s
            for s in self.db.scalars(select(InpostShipment).where(InpostShipment.id.in_(shipment_ids)))
        }
        missing = [str(i) for i in shipment_ids if i not in found]
        if missing:
            raise LookupError(f"Unknown shipment: {', '.join(missing)}")
        ordered = [found[i] for i in dict.fromkeys(shipment_ids)]
        unready = [s for s in ordered if not s.tracking_number or s.status in _CANCELLED]
        if unready:
            raise InpostRefused("Only shipments InPost has bought, and not cancelled, have a label")
        content = self._client_factory().fetch_labels([s.inpost_id for s in ordered], "A6")
        # noted once the PDF is in hand: whether it reached a printer is the operator's
        # to know, and printing again is always possible
        now = datetime.now(UTC)
        for shipment in ordered:
            shipment.printed_at = now
        self.db.commit()
        return content
