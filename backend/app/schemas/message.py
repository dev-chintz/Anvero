import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.message import MessageDirection
from app.models.order import OrderSource
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.types import UtcDateTime

REPLY_MAX_LENGTH = 4000


class MessageRead(BaseModel):
    id: uuid.UUID
    direction: MessageDirection
    author_login: str | None
    text: str
    sent_at: UtcDateTime
    # a reply written in Anvero, as opposed to read from the marketplace
    created_in_anvero: bool

    model_config = ConfigDict(from_attributes=True)


class ThreadRead(BaseModel):
    id: uuid.UUID
    source: OrderSource
    interlocutor_login: str | None
    # the marketplace's order id the thread names, if any - not a link to an
    # Anvero order, since the order may not exist here, or may have arrived
    # under a different id
    order_external_id: str | None
    last_message_at: UtcDateTime | None
    last_message_text: str | None
    read: bool
    aside: bool

    model_config = ConfigDict(from_attributes=True)


class ThreadDetailRead(ThreadRead):
    messages: list[MessageRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ThreadReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=REPLY_MAX_LENGTH)


class ThreadReplyResult(BaseModel):
    """A reply after it was written, and what became of sending it.

    `marketplace_write` says whether it was sent, held back by safe mode, or
    refused, and why - the same shape an order status change reports.
    """

    thread: ThreadDetailRead
    marketplace_write: MarketplaceWriteRead


class ThreadAsideUpdate(BaseModel):
    aside: bool


class MessageSyncResult(BaseModel):
    threads_synced: int
    messages_added: int


# --- what an adapter's mapper produces, before storage ----------------------


class SyncedThread(BaseModel):
    """One thread as an adapter reads it, before it is stored."""

    external_id: str = Field(min_length=1, max_length=255)
    interlocutor_login: str | None = Field(default=None, max_length=255)
    order_external_id: str | None = Field(default=None, max_length=255)
    last_message_at: UtcDateTime | None = None
    read: bool = True


class SyncedMessage(BaseModel):
    """One message as an adapter reads it, before it is stored."""

    external_id: str | None = Field(default=None, max_length=255)
    direction: MessageDirection
    author_login: str | None = Field(default=None, max_length=255)
    text: str = Field(min_length=1)
    sent_at: UtcDateTime
