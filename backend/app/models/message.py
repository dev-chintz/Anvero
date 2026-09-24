import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.order import OrderSource


class MessageDirection(str, enum.Enum):
    # from the buyer
    IN = "IN"
    # from the seller, whether sent through Anvero or the marketplace's own
    # panel; which one is `created_in_anvero`
    OUT = "OUT"


class MessageThread(Base):
    """One buyer-seller conversation on a marketplace's Message Center.

    Kept by the marketplace's own id, like billing_entries. Unlike an order's
    items or shipments, a thread's messages are not wholly replaced on sync:
    only what is new is added, since a message once sent is never edited or
    withdrawn on the marketplace's side either.
    """

    __tablename__ = "message_threads"
    __table_args__ = (
        UniqueConstraint(
            "source", "external_id", name="uq_message_threads_source_external_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, native_enum=False, length=32), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # the buyer's login on the marketplace; the only name a thread carries
    interlocutor_login: Mapped[str | None] = mapped_column(String(255))

    # the marketplace's id of the order a message in this thread named, if
    # any. Not a foreign key, like billing_entries.order_external_id: the
    # order may not exist in Anvero yet, or the thread may name none.
    order_external_id: Mapped[str | None] = mapped_column(String(255), index=True)

    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # cached from the newest message, so the inbox list needs no join to show it
    last_message_text: Mapped[str | None] = mapped_column(String(500))

    # the marketplace's own read flag, mirrored at the last sync; Anvero does
    # not write it back, so reading a thread here does not mark it read there
    read: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )

    # set by an operator to come back to later; local to Anvero, never synced
    aside: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="Message.sent_at",
    )


class Message(Base):
    """One message in a thread, read from the marketplace or sent from Anvero."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "external_id", name="uq_messages_thread_id_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # the marketplace's own id; null for a reply sent from Anvero that safe
    # mode held back or that the marketplace refused - same idea as
    # order_shipments.external_id before an import confirms it
    external_id: Mapped[str | None] = mapped_column(String(255))

    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, native_enum=False, length=8), nullable=False
    )
    # who the marketplace says wrote it; null when unreadable
    author_login: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # a reply written in Anvero, as opposed to one read from the marketplace
    # (which includes the seller's own past replies sent from its own panel)
    created_in_anvero: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    thread: Mapped["MessageThread"] = relationship(back_populates="messages")
