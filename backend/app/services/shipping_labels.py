"""Buying shipments through "Wysyłam z Allegro", and printing their labels.

Buying costs the seller money, so it goes through MarketplaceWriter (safe mode
holds it back like any other write) and an order has at most one label that
is being bought or is bought: a second needs the first cancelled or refused.
Allegro creates a shipment asynchronously; `buy` waits a few seconds for it,
and a label still pending after that is settled by `refresh`.

Built from Allegro's documentation and tested on fakes; nothing has been
bought for real (docs/INTEGRATIONS.md, "Labels through Wysyłam z Allegro").
"""

import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.order_number import format_order_number
from app.integrations.allegro.client import AllegroClient
from app.integrations.base import IntegrationError
from app.models.marketplace_write import WriteOutcome
from app.models.order import AddressType, Order, OrderSource, PaymentType
from app.models.shipping_label import LabelStatus, ShippingLabel
from app.schemas.shipping import PackageSize, ShippingSender
from app.services.allegro_import import build_allegro_client
from app.services.marketplace_writes import MarketplaceWriter, WriteResult
from app.services.order_writes import ALLEGRO_CARRIERS, OrderWrites, _with_import_lock
from app.services.shipping_settings import get_shipping_settings

logger = logging.getLogger(__name__)

# how long `buy` waits for Allegro to create the shipment before leaving it
# pending for `refresh`
SETTLE_ATTEMPTS = 8
SETTLE_INTERVAL_SECONDS = 1.0

_ACTIVE = (LabelStatus.PENDING, LabelStatus.CREATED)

ClientFactory = Callable[[], AllegroClient]


class LabelRefused(Exception):
    """The label cannot be bought for this order as things stand; the message
    says why, for the operator."""


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _measure(value, unit: str) -> dict[str, Any]:
    return {"value": float(value), "unit": unit}


def shipment_input(
    order: Order, delivery_method_id: str, sender: ShippingSender, package: PackageSize
) -> dict[str, Any]:
    """The `input` of Allegro's create command for this order's parcel."""
    address = order.address(AddressType.DELIVERY)
    if address is None:
        raise LabelRefused("The order has no delivery address")
    name = " ".join(p for p in (address.first_name, address.last_name) if p) or address.company_name
    receiver: dict[str, Any] = {
        "name": name,
        "company": address.company_name,
        "street": address.street,
        "postalCode": address.postal_code,
        "city": address.city,
        "countryCode": address.country_code or "PL",
        "email": order.customer_email,
        "phone": address.phone or order.customer_phone,
    }
    if order.pickup_point_id:
        receiver["point"] = order.pickup_point_id
    return {
        "deliveryMethodId": delivery_method_id,
        "sender": {
            "name": sender.name,
            "company": sender.company,
            "street": sender.street,
            "postalCode": sender.postal_code,
            "city": sender.city,
            "countryCode": sender.country_code,
            "email": sender.email,
            "phone": sender.phone,
        },
        "receiver": {k: v for k, v in receiver.items() if v},
        "referenceNumber": format_order_number(order.order_number),
        "packages": [
            {
                "type": "PACKAGE",
                "length": _measure(package.length_cm, "CENTIMETER"),
                "width": _measure(package.width_cm, "CENTIMETER"),
                "height": _measure(package.height_cm, "CENTIMETER"),
                "weight": _measure(package.weight_kg, "KILOGRAMS"),
            }
        ],
        "labelFormat": "PDF",
    }


def _carrier_and_waybill(shipment: dict[str, Any]) -> tuple[str | None, str | None]:
    """Read the carrier and waybill from Allegro's shipment, in either of the
    shapes its documentation suggests (unconfirmed until a real one is seen)."""
    carrier = shipment.get("carrier")
    carrier_id = _text(carrier) or _text(_obj(carrier).get("id")) or _text(shipment.get("carrierId"))
    waybill = _text(shipment.get("waybill"))
    packages = shipment.get("packages")
    if not waybill and isinstance(packages, list) and packages:
        waybill = _text(_obj(packages[0]).get("waybill"))
    return carrier_id, waybill


def _errors(command: dict[str, Any]) -> str:
    errors = command.get("errors")
    if isinstance(errors, list):
        texts = [
            _text(_obj(e).get("userMessage")) or _text(_obj(e).get("message")) or _text(_obj(e).get("code"))
            for e in errors
        ]
        joined = "; ".join(t for t in texts if t)
        if joined:
            return joined[:1000]
    return "Allegro refused the shipment without saying why"


class ShippingLabels:
    def __init__(
        self,
        db: Session,
        client_factory: ClientFactory | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.db = db
        self.writer = MarketplaceWriter(db)
        self._client_factory = client_factory or (lambda: build_allegro_client(db))
        self._sleep = sleep

    def for_order(self, order: Order) -> list[ShippingLabel]:
        return list(
            self.db.scalars(
                select(ShippingLabel)
                .where(ShippingLabel.order_id == order.id)
                .order_by(ShippingLabel.created_at.desc())
            )
        )

    def get(self, order: Order, label_id: uuid.UUID) -> ShippingLabel | None:
        label = self.db.get(ShippingLabel, label_id)
        return label if label is not None and label.order_id == order.id else None

    def buy(
        self, order: Order, package: PackageSize, user_id: int | None
    ) -> tuple[ShippingLabel | None, WriteResult]:
        """Buy the order's shipment; the label, or None when nothing was bought.

        Raises LabelRefused when it cannot be asked for at all. Allegro's own
        refusal comes back as a FAILED write, or a FAILED label.
        """
        if order.source is not OrderSource.ALLEGRO:
            raise LabelRefused("Labels through Wysyłam z Allegro are for Allegro orders only")
        if order.payment_type == PaymentType.CASH_ON_DELIVERY:
            raise LabelRefused("Cash on delivery is not supported yet; buy this label on Allegro")
        if any(label.status in _ACTIVE for label in self.for_order(order)):
            raise LabelRefused("The order already has a label; cancel it before buying another")
        sender = get_shipping_settings(self.db).sender
        if sender is None:
            raise LabelRefused("Enter the sender's address in Settings first")

        client = self._client_factory()
        command_id = str(uuid.uuid4())

        # the delivery method is read from Allegro as it stands now: it is
        # what decides the carrier and the price, and orders imported earlier
        # do not carry its id
        def delivery_method_id() -> str:
            form = client.fetch_checkout_form(order.external_id)
            method = _text(_obj(_obj(form.get("delivery")).get("method")).get("id"))
            if method is None:
                raise LabelRefused("Allegro gives no delivery method for this order")
            return method

        method_id = _with_import_lock(delivery_method_id)
        payload = shipment_input(order, method_id, sender, package)

        result = self.writer.write(
            OrderSource.ALLEGRO,
            "shipment_label",
            {"commandId": command_id, "input": payload},
            lambda: _with_import_lock(lambda: client.create_shipment(command_id, payload)),
            order_id=order.id,
            user_id=user_id,
            raise_errors=False,
        )
        self.db.refresh(order)
        if result.outcome is not WriteOutcome.SENT:
            return None, result

        label = ShippingLabel(
            order_id=order.id,
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            command_id=command_id,
            status=LabelStatus.PENDING,
            delivery_method_id=method_id,
            length_cm=package.length_cm,
            width_cm=package.width_cm,
            height_cm=package.height_cm,
            weight_kg=package.weight_kg,
        )
        self.db.add(label)
        self.db.commit()
        self._settle(order, label, client, SETTLE_ATTEMPTS, user_id)
        return label, result

    def refresh(self, order: Order, label: ShippingLabel, user_id: int | None) -> ShippingLabel:
        """Ask Allegro once more about a label still pending."""
        if label.status is LabelStatus.PENDING:
            self._settle(order, label, self._client_factory(), 1, user_id)
        return label

    def _settle(
        self,
        order: Order,
        label: ShippingLabel,
        client: AllegroClient,
        attempts: int,
        user_id: int | None,
    ) -> None:
        def poll() -> None:
            for attempt in range(attempts):
                if attempt:
                    self._sleep(SETTLE_INTERVAL_SECONDS)
                command = client.shipment_command(label.command_id)
                status = command.get("status")
                if status == "SUCCESS":
                    label.shipment_id = _text(command.get("shipmentId"))
                    if label.shipment_id:
                        label.carrier_id, label.waybill = _carrier_and_waybill(
                            client.fetch_shipment(label.shipment_id)
                        )
                    label.status = LabelStatus.CREATED
                    label.error = None
                    return
                if status == "ERROR":
                    label.status = LabelStatus.FAILED
                    label.error = _errors(command)
                    return

        try:
            _with_import_lock(poll)
        except IntegrationError as exc:
            # the shipment may well exist: stay pending, and say why unknown
            label.error = f"Not confirmed yet: {exc}"[:1000]
        self.db.commit()

        if label.status is LabelStatus.CREATED and label.waybill:
            self._tell_the_buyer(order, label, user_id)

    def _tell_the_buyer(self, order: Order, label: ShippingLabel, user_id: int | None) -> None:
        """Put the waybill on the order, which also sends it to Allegro.

        Whether Allegro links a Wysyłam z Allegro shipment to the order by
        itself is unconfirmed; if it does, it may refuse this as a duplicate,
        which is recorded and harmless.
        """
        carrier = label.carrier_id if label.carrier_id in ALLEGRO_CARRIERS else "OTHER"
        name = None if carrier != "OTHER" else (label.carrier_id or "Wysyłam z Allegro")
        OrderWrites(self.db, self._client_factory).add_shipment(
            order, carrier, name, label.waybill, user_id
        )

    def cancel(
        self, order: Order, label: ShippingLabel, user_id: int | None
    ) -> WriteResult:
        """Cancel a bought shipment; Allegro refunds it if not yet handed over."""
        if label.status is not LabelStatus.CREATED or not label.shipment_id:
            raise LabelRefused("Only a created shipment can be cancelled")
        client = self._client_factory()
        command_id = str(uuid.uuid4())
        shipment_id = label.shipment_id
        result = self.writer.write(
            OrderSource.ALLEGRO,
            "shipment_cancel",
            {"commandId": command_id, "input": {"shipmentId": shipment_id}},
            lambda: _with_import_lock(lambda: client.cancel_shipment(command_id, shipment_id)),
            order_id=order.id,
            user_id=user_id,
            raise_errors=False,
        )
        self.db.refresh(label)
        if result.outcome is not WriteOutcome.SENT:
            return result

        def poll() -> None:
            for attempt in range(SETTLE_ATTEMPTS):
                if attempt:
                    self._sleep(SETTLE_INTERVAL_SECONDS)
                command = client.cancel_command(command_id)
                if command.get("status") == "SUCCESS":
                    label.status = LabelStatus.CANCELLED
                    label.error = None
                    return
                if command.get("status") == "ERROR":
                    label.error = f"Not cancelled: {_errors(command)}"[:1000]
                    return
            label.error = "Cancellation asked for, not confirmed yet: check on Allegro"

        try:
            _with_import_lock(poll)
        except IntegrationError as exc:
            label.error = f"Cancellation asked for, not confirmed: {exc}"[:1000]
        self.db.commit()
        return result

    def pdf(self, label: ShippingLabel) -> bytes:
        if label.status is not LabelStatus.CREATED or not label.shipment_id:
            raise LabelRefused("There is no label to print yet")
        client = self._client_factory()
        shipment_id = label.shipment_id
        return _with_import_lock(lambda: client.fetch_label([shipment_id], "A6"))
