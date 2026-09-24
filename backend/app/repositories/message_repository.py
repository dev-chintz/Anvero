import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message, MessageDirection, MessageThread
from app.models.order import OrderSource
from app.schemas.message import SyncedMessage, SyncedThread

# how much of the newest message is kept on the thread for the inbox list
LAST_MESSAGE_EXCERPT_LENGTH = 500


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_thread(self, thread_id: uuid.UUID) -> MessageThread | None:
        return self.db.get(MessageThread, thread_id)

    def get_thread_by_external_id(
        self, source: OrderSource, external_id: str
    ) -> MessageThread | None:
        return self.db.scalar(
            select(MessageThread).where(
                MessageThread.source == source, MessageThread.external_id == external_id
            )
        )

    def upsert_thread(self, source: OrderSource, data: SyncedThread) -> MessageThread:
        """Create or update a thread's own fields; its messages are separate.

        The marketplace owns these fields, like an order's details: a thread
        already stored has them replaced, never merged. `aside` is never
        touched here - it is local to Anvero.
        """
        thread = self.get_thread_by_external_id(source, data.external_id)
        if thread is None:
            thread = MessageThread(source=source, external_id=data.external_id)
            self.db.add(thread)
        thread.interlocutor_login = data.interlocutor_login
        if data.order_external_id:
            thread.order_external_id = data.order_external_id
        thread.read = data.read
        if data.last_message_at is not None:
            thread.last_message_at = self._to_db_datetime(data.last_message_at)
        self.db.commit()
        self.db.refresh(thread)
        return thread

    def add_messages(self, thread: MessageThread, messages: list[SyncedMessage]) -> int:
        """Store the messages not stored yet; returns how many were new.

        A message never changes once the marketplace has it, so one already
        stored (matched by its external id) is left alone, and reading an
        overlapping page twice adds nothing.
        """
        known_ids = {
            m.external_id
            for m in thread.messages
            if m.external_id is not None
        }
        added = 0
        newest: SyncedMessage | None = None
        for data in messages:
            if data.external_id is not None and data.external_id in known_ids:
                continue
            self.db.add(
                Message(
                    thread_id=thread.id,
                    external_id=data.external_id,
                    direction=data.direction,
                    author_login=data.author_login,
                    text=data.text,
                    sent_at=self._to_db_datetime(data.sent_at),
                )
            )
            added += 1
            if newest is None or data.sent_at >= newest.sent_at:
                newest = data
        if newest is not None:
            thread.last_message_text = newest.text[:LAST_MESSAGE_EXCERPT_LENGTH]
        self.db.commit()
        self.db.refresh(thread)
        return added

    def list_threads(
        self,
        source: OrderSource | None = None,
        aside: bool | None = None,
        unread_only: bool = False,
        limit: int = 200,
    ) -> list[MessageThread]:
        """Newest activity first; threads with no message yet sort last."""
        query = select(MessageThread)
        if source is not None:
            query = query.where(MessageThread.source == source)
        if aside is not None:
            query = query.where(MessageThread.aside == aside)
        if unread_only:
            query = query.where(MessageThread.read.is_(False))
        query = query.order_by(
            MessageThread.last_message_at.desc().nullslast(), MessageThread.id
        ).limit(limit)
        return list(self.db.scalars(query))

    def set_aside(self, thread: MessageThread, aside: bool) -> MessageThread:
        thread.aside = aside
        self.db.commit()
        self.db.refresh(thread)
        return thread

    def add_reply(
        self,
        thread: MessageThread,
        text: str,
        external_id: str | None,
        author_login: str | None,
        sent_at: datetime,
    ) -> Message:
        """Record a reply written in Anvero, whatever became of sending it.

        Stored whether safe mode held it back or Allegro refused it - the
        operator's action in Anvero is real either way, same as a tracking
        number typed in stays on the order even if Allegro does not take it
        (order_writes.py). The thread is marked read: replying to it is
        acting on it.
        """
        message = Message(
            thread_id=thread.id,
            external_id=external_id,
            direction=MessageDirection.OUT,
            author_login=author_login,
            text=text,
            sent_at=self._to_db_datetime(sent_at),
            created_in_anvero=True,
        )
        self.db.add(message)
        thread.last_message_at = self._to_db_datetime(sent_at)
        thread.last_message_text = text[:LAST_MESSAGE_EXCERPT_LENGTH]
        thread.read = True
        self.db.commit()
        self.db.refresh(thread)
        return message

    def _to_db_datetime(self, value: datetime) -> datetime:
        """Match the bind parameter to how the backend stores timestamps.

        SQLite has no timezone-aware type and stores naive UTC, so an aware
        parameter would render with an offset and never compare equal.
        """
        if self.db.get_bind().dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value
