import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.user import User


class PickupStatus(str, enum.Enum):
    # asked for; Allegro has not confirmed yet
    PENDING = "PENDING"
    # the carrier will come
    ORDERED = "ORDERED"
    # Allegro refused it; `error` says why, and its parcels are free again
    FAILED = "FAILED"


class CourierPickup(Base):
    """A courier ordered through Wysyłam z Allegro to collect bought parcels.

    Its parcels are the `shipping_labels` pointing at it; one pickup serves
    one carrier.
    """

    __tablename__ = "courier_pickups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # the id Anvero gave the create command, and Allegro's id for the pickup
    command_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pickup_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[PickupStatus] = mapped_column(
        Enum(PickupStatus, native_enum=False, length=16), nullable=False
    )
    carrier_id: Mapped[str | None] = mapped_column(String(64))
    # the day the parcels are ready, and the slot chosen from Allegro's
    # proposals, as its id and as it was shown
    ready_date: Mapped[date] = mapped_column(Date, nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(255), nullable=False)
    proposal_label: Mapped[str] = mapped_column(String(255), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped["User | None"] = relationship()
