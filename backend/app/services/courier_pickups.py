"""Ordering a courier through Wysyłam z Allegro to collect bought parcels.

Allegro first proposes when a courier could come for the chosen parcels on a
given day; ordering one of those slots is a write through MarketplaceWriter
(safe mode holds it back), asynchronous like buying a shipment. One pickup
serves one carrier's parcels, and a parcel is in at most one pickup that is
pending or ordered.

Built from Allegro's documentation and tested on fakes; no courier has been
ordered for real (docs/INTEGRATIONS.md, "Courier pickup").
"""

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.allegro.client import AllegroClient
from app.integrations.base import IntegrationError
from app.models.courier_pickup import CourierPickup, PickupStatus
from app.models.marketplace_write import WriteOutcome
from app.models.order import OrderSource
from app.models.shipping_label import LabelStatus, ShippingLabel
from app.services.allegro_import import build_allegro_client
from app.services.marketplace_writes import MarketplaceWriter, WriteResult
from app.services.order_writes import _with_import_lock
from app.services.shipping_labels import (
    SETTLE_ATTEMPTS,
    SETTLE_INTERVAL_SECONDS,
    LabelRefused,
    _errors,
    _obj,
    _text,
)

# parcels in one pickup; the documentation names no limit
MAX_PARCELS_PER_PICKUP = 50

_STANDING = (PickupStatus.PENDING, PickupStatus.ORDERED)

ClientFactory = Callable[[], AllegroClient]


@dataclass(frozen=True)
class PickupOption:
    """One slot Allegro proposes: its id, and how to show it."""

    id: str
    label: str


def proposal_options(payload: dict[str, Any]) -> list[PickupOption]:
    """Allegro's pickup proposals as a flat list of slots.

    Read defensively, since no real answer has been seen: groups under
    `proposals`, each with its own `proposals`, each either a slot itself
    (`proposalId` or `id`, with `name` or a date) or holding slots in
    `proposalItems` (`id`, `name`).
    """
    options: list[PickupOption] = []
    seen: set[str] = set()

    def add(option_id: str | None, label: str | None) -> None:
        if option_id and option_id not in seen:
            seen.add(option_id)
            options.append(PickupOption(option_id, label or option_id))

    groups = payload.get("proposals")
    for group in groups if isinstance(groups, list) else []:
        inner = _obj(group).get("proposals")
        for proposal in inner if isinstance(inner, list) else [group]:
            proposal = _obj(proposal)
            name = _text(proposal.get("name")) or _text(proposal.get("date"))
            items = proposal.get("proposalItems")
            if isinstance(items, list) and items:
                for item in items:
                    item = _obj(item)
                    item_name = _text(item.get("name"))
                    label = " ".join(p for p in (name, item_name) if p)
                    add(_text(item.get("id")), label)
            else:
                add(_text(proposal.get("proposalId")) or _text(proposal.get("id")), name)
    return options


def business_today() -> date:
    return datetime.now(ZoneInfo(settings.business_timezone)).date()


class CourierPickups:
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

    def get(self, pickup_id: uuid.UUID) -> CourierPickup | None:
        return self.db.get(CourierPickup, pickup_id)

    def _parcels(self, label_ids: list[uuid.UUID], ready_date: date) -> list[ShippingLabel]:
        """The labels asked for, checked: they can go in one pickup that day."""
        if not label_ids:
            raise LabelRefused("Choose at least one parcel")
        if len(label_ids) > MAX_PARCELS_PER_PICKUP:
            raise LabelRefused(f"At most {MAX_PARCELS_PER_PICKUP} parcels in one pickup")
        if ready_date < business_today():
            raise LabelRefused("The parcels cannot be ready on a day already past")
        found = {
            label.id: label
            for label in self.db.scalars(select(ShippingLabel).where(ShippingLabel.id.in_(label_ids)))
        }
        missing = [str(i) for i in label_ids if i not in found]
        if missing:
            raise LookupError(f"Unknown label: {', '.join(missing)}")
        labels = [found[i] for i in dict.fromkeys(label_ids)]
        if any(label.status is not LabelStatus.CREATED or not label.shipment_id for label in labels):
            raise LabelRefused("Only bought parcels can be collected")
        if any(label.pickup is not None and label.pickup.status in _STANDING for label in labels):
            raise LabelRefused("A courier is already ordered for some of these parcels")
        if len({label.carrier_id for label in labels}) > 1:
            raise LabelRefused("One pickup is for one carrier: choose parcels of one carrier")
        return labels

    def proposals(self, label_ids: list[uuid.UUID], ready_date: date) -> list[PickupOption]:
        """When a courier could come for these parcels; a read, not a write."""
        labels = self._parcels(label_ids, ready_date)
        client = self._client_factory()
        shipment_ids = [label.shipment_id for label in labels]
        payload = _with_import_lock(
            lambda: client.pickup_proposals(shipment_ids, ready_date.isoformat())
        )
        return proposal_options(payload)

    def order(
        self,
        label_ids: list[uuid.UUID],
        ready_date: date,
        proposal_id: str,
        proposal_label: str,
        user_id: int | None,
    ) -> tuple[CourierPickup | None, WriteResult]:
        """Order the courier for the chosen slot; None when nothing was ordered."""
        labels = self._parcels(label_ids, ready_date)
        client = self._client_factory()
        command_id = str(uuid.uuid4())
        shipment_ids = [label.shipment_id for label in labels]
        result = self.writer.write(
            OrderSource.ALLEGRO,
            "courier_pickup",
            {
                "commandId": command_id,
                "input": {"shipmentIds": shipment_ids, "pickupDateProposalId": proposal_id},
            },
            lambda: _with_import_lock(
                lambda: client.create_pickup(command_id, shipment_ids, proposal_id)
            ),
            user_id=user_id,
            raise_errors=False,
        )
        if result.outcome is not WriteOutcome.SENT:
            return None, result

        pickup = CourierPickup(
            created_at=datetime.now(UTC),
            created_by_user_id=user_id,
            command_id=command_id,
            status=PickupStatus.PENDING,
            carrier_id=labels[0].carrier_id,
            ready_date=ready_date,
            proposal_id=proposal_id,
            proposal_label=proposal_label[:255],
        )
        self.db.add(pickup)
        self.db.flush()
        for label in self.db.scalars(select(ShippingLabel).where(ShippingLabel.id.in_(label_ids))):
            label.pickup_id = pickup.id
        self.db.commit()
        self._settle(pickup, client, SETTLE_ATTEMPTS)
        return pickup, result

    def refresh(self, pickup: CourierPickup) -> CourierPickup:
        """Ask Allegro once more about a pickup still pending."""
        if pickup.status is PickupStatus.PENDING:
            self._settle(pickup, self._client_factory(), 1)
        return pickup

    def _settle(self, pickup: CourierPickup, client: AllegroClient, attempts: int) -> None:
        def poll() -> None:
            for attempt in range(attempts):
                if attempt:
                    self._sleep(SETTLE_INTERVAL_SECONDS)
                command = client.pickup_command(pickup.command_id)
                status = command.get("status")
                if status == "SUCCESS":
                    pickup.pickup_id = _text(command.get("pickupId"))
                    pickup.status = PickupStatus.ORDERED
                    pickup.error = None
                    return
                if status == "ERROR":
                    pickup.status = PickupStatus.FAILED
                    pickup.error = _errors(command)
                    return

        try:
            _with_import_lock(poll)
        except IntegrationError as exc:
            pickup.error = f"Not confirmed yet: {exc}"[:1000]
        if pickup.status is PickupStatus.FAILED:
            # refused: its parcels can be offered to another courier
            for label in self.db.scalars(
                select(ShippingLabel).where(ShippingLabel.pickup_id == pickup.id)
            ):
                label.pickup_id = None
        self.db.commit()
