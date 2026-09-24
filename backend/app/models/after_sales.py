import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.models.order import OrderSource


class CaseKind(str, enum.Enum):
    # the buyer sent goods back (Allegro's customer returns)
    RETURN = "RETURN"
    # a formal claim (reklamacja): warranty or complaint, with a deadline
    CLAIM = "CLAIM"
    # a discussion about a problem with an order, without a formal deadline
    DISPUTE = "DISPUTE"


class CaseAction(str, enum.Enum):
    NONE = "NONE"
    # the seller has to decide: refund or reject a return, accept or reject a claim
    DECIDE = "DECIDE"
    # the buyer wrote last in a dispute and is waiting for an answer
    REPLY = "REPLY"
    # the buyer was refunded; the sales commission can still be claimed back
    RECOVER_COMMISSION = "RECOVER_COMMISSION"


class AfterSalesCase(Base):
    """A return, claim or dispute on a marketplace, and what it asks of the seller.

    Read from the marketplace and replaced on each sync, as an order's details
    are: the marketplace owns every field. `action` and `due_at` are worked out
    when it is stored (see app.services.after_sales): a claim's deadline comes
    from the marketplace, a return's from the rules there. The order is named
    by the marketplace's id and not linked by a foreign key, like a message
    thread's, since the order may not have been imported.
    """

    __tablename__ = "after_sales_cases"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_after_sales_cases_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source: Mapped[OrderSource] = mapped_column(
        Enum(OrderSource, native_enum=False, length=32), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[CaseKind] = mapped_column(
        Enum(CaseKind, native_enum=False, length=16), nullable=False
    )

    # the marketplace's own status, in its own words (CLAIM_SUBMITTED, DELIVERED...)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    # false once the process is over on the marketplace's side (a refunded
    # return is over, though its commission may still be claimed: see `action`)
    is_open: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    action: Mapped[CaseAction] = mapped_column(
        Enum(CaseAction, native_enum=False, length=32), nullable=False, index=True
    )
    # the moment the action has to be taken by; null when there is none
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # the number Allegro prints on a claim (like 12/2026); null for the rest
    reference_number: Mapped[str | None] = mapped_column(String(64))
    order_external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    buyer_login: Mapped[str | None] = mapped_column(String(255))
    buyer_email: Mapped[str | None] = mapped_column(String(255))

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # the marketplace's reason code (NOT_AS_DESCRIBED, DAMAGED...), worded by the interface
    reason: Mapped[str | None] = mapped_column(String(64))
    # what it is about: the goods returned, or the buyer's own description
    summary: Mapped[str | None] = mapped_column(String(500))
    # the buyer's comment, or the solution a claim asks for
    detail: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
