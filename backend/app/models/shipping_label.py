import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.courier_pickup import CourierPickup
from app.models.order import Order
from app.models.user import User


class LabelStatus(str, enum.Enum):
    # asked for; Allegro has not said yet whether the shipment exists
    PENDING = "PENDING"
    # the shipment exists and its label can be printed
    CREATED = "CREATED"
    # Allegro refused it; `error` says why
    FAILED = "FAILED"
    # cancelled after it was created
    CANCELLED = "CANCELLED"


class ShippingLabel(Base):
    """A shipment bought through "Wysyłam z Allegro", with its label.

    Kept apart from `order_shipments`, which an import replaces: this is what
    Anvero bought, identified by Allegro's shipment-management ids, and is
    needed afterwards to print the label again or cancel the shipment.
    """

    __tablename__ = "shipping_labels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # the id Anvero gave the create command; Allegro answers under it
    command_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Allegro's id for the shipment once it exists
    shipment_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[LabelStatus] = mapped_column(
        Enum(LabelStatus, native_enum=False, length=16), nullable=False
    )
    delivery_method_id: Mapped[str] = mapped_column(String(255), nullable=False)

    carrier_id: Mapped[str | None] = mapped_column(String(64))
    waybill: Mapped[str | None] = mapped_column(String(255))

    # the parcel as declared: centimetres and kilograms
    length_cm: Mapped[Decimal] = mapped_column(Numeric(8, 1), nullable=False)
    width_cm: Mapped[Decimal] = mapped_column(Numeric(8, 1), nullable=False)
    height_cm: Mapped[Decimal] = mapped_column(Numeric(8, 1), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)

    # Allegro's reason for refusing it, or for a failed cancellation
    error: Mapped[str | None] = mapped_column(Text)

    # when its label was last fetched for printing; null until it has been,
    # which is what puts it on the Labels page's "to print" list
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # the courier ordered to collect it; null until one is (and again if
    # that order was refused)
    pickup_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courier_pickups.id", ondelete="SET NULL"), index=True, nullable=True
    )

    created_by: Mapped["User | None"] = relationship()
    order: Mapped["Order"] = relationship()
    pickup: Mapped["CourierPickup | None"] = relationship()
