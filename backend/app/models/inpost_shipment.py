import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.order import Order
from app.models.user import User


class InpostShipment(Base):
    """A parcel locker shipment made through InPost's own API, with its label.

    Kept apart from `order_shipments`, which an import replaces: this is what Anvero
    made at InPost, known by InPost's id, and is what is needed afterwards to
    print its label again or cancel it. Its tracking number is also put on the
    order as an ordinary shipment once InPost has given one.
    """

    __tablename__ = "inpost_shipments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # InPost's id for the shipment (a number, kept as text)
    inpost_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    # InPost's own word for where it is: created, offer_selected, confirmed, ...,
    # cancelled. The label can be printed from `confirmed` on.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # null until InPost has bought the shipment, which it does a moment after it is made
    tracking_number: Mapped[str | None] = mapped_column(String(64))

    # what was asked for: the locker (its code, e.g. KRA010) and the size
    target_point: Mapped[str] = mapped_column(String(32), nullable=False)
    template: Mapped[str] = mapped_column(String(16), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))

    # InPost's reason for a shipment it could not buy, or for a cancellation that failed
    error: Mapped[str | None] = mapped_column(Text)

    # when its label was last fetched for printing; null until it has been, which is
    # what puts it on the list of labels to print
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped["User | None"] = relationship()
    order: Mapped["Order"] = relationship()
