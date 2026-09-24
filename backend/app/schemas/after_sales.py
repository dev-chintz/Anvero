import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.after_sales import CaseAction, CaseKind
from app.models.order import OrderSource
from app.schemas.types import UtcDateTime


class SyncedCase(BaseModel):
    """One return, claim or dispute as an adapter reads it, before the rules
    say what it asks of the seller and by when."""

    kind: CaseKind
    external_id: str = Field(min_length=1, max_length=255)
    status: str = Field(min_length=1, max_length=64)
    is_open: bool = True
    opened_at: UtcDateTime
    reference_number: str | None = Field(default=None, max_length=64)
    order_external_id: str | None = Field(default=None, max_length=255)
    buyer_login: str | None = Field(default=None, max_length=255)
    buyer_email: str | None = Field(default=None, max_length=255)
    reason: str | None = Field(default=None, max_length=64)
    summary: str | None = Field(default=None, max_length=500)
    detail: str | None = Field(default=None, max_length=500)
    # the deadline the marketplace itself gives a claim; null for the rest
    marketplace_due_at: UtcDateTime | None = None
    # who wrote a dispute's last message (NEW, SELLER_REPLIED, BUYER_REPLIED,
    # ALLEGRO_ADVISOR_REPLIED); null when the marketplace gives none
    last_message_status: str | None = None


class CaseRead(BaseModel):
    id: uuid.UUID
    source: OrderSource
    kind: CaseKind
    status: str
    is_open: bool
    action: CaseAction
    due_at: UtcDateTime | None
    # the deadline has passed while the seller still has to act
    overdue: bool = False
    reference_number: str | None
    buyer_login: str | None
    buyer_email: str | None
    opened_at: UtcDateTime
    reason: str | None
    summary: str | None
    detail: str | None
    # the Anvero order this belongs to, when it has been imported
    order_external_id: str | None
    order_id: uuid.UUID | None = None
    order_label: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CaseList(BaseModel):
    items: list[CaseRead]
    total: int


class AfterSalesSummary(BaseModel):
    """How many cases wait for the seller, for the badges that lead to the queue."""

    # every case whose action is not NONE
    needs_action: int
    # of those, deadline passed
    overdue: int
    # of those, deadline within the next three days and not passed
    due_soon: int


class AfterSalesSyncResult(BaseModel):
    returns: int
    claims: int
    disputes: int
