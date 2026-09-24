import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.order import OrderSource
from app.models.user import User


class AppSetting(Base):
    """One application-wide setting an operator changes in the interface.

    Key and value as text, so a new setting needs no migration. Who changed it
    last, and when, is kept beside it: switching safe mode off sends real
    messages to real buyers, and it should be clear who did.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by: Mapped["User | None"] = relationship()


class WriteOutcome(str, enum.Enum):
    # safe mode was on: recorded, and nothing sent
    DRY_RUN = "DRY_RUN"
    SENT = "SENT"
    FAILED = "FAILED"


class MarketplaceWrite(Base):
    """One change Anvero made, or would have made, on a marketplace.

    Every write goes through app/services/marketplace_writes.py, which records
    it here whether it was sent or held back by safe mode, so there is one
    place to see what Anvero has told Allegro or Erli, and what it would have.
    Append-only.
    """

    __tablename__ = "marketplace_writes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, native_enum=False, length=32), nullable=False
    )
    # the order it concerns, if any; kept when the order is deleted, since
    # what was sent to a marketplace stays sent
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # what kind of change, e.g. "fulfillment_status"
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # what was, or would have been, sent: JSON, as the marketplace would get it
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[WriteOutcome] = mapped_column(
        Enum(WriteOutcome, native_enum=False, length=16), nullable=False
    )
    # the marketplace's answer when sent, or the error when it failed
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User | None"] = relationship()

    @property
    def user_email(self) -> str | None:
        return self.user.email if self.user is not None else None
