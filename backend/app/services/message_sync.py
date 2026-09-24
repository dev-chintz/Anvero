"""Reading Allegro's Message Center into Anvero's own inbox.

Threads are read newest activity first and compared against what is already
stored; a thread whose last message and read flag have not moved is left
alone, so a sync with nothing new to show costs one page of thread summaries
and nothing else. Runs under the same lock as an order import
(app.services.allegro_sync.import_lock): both refresh the same rotating
token, and two refreshes at once would invalidate one of them.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.integrations.allegro.messaging import AllegroMessagingAdapter
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.message_repository import MessageRepository
from app.schemas.types import _as_utc
from app.services import allegro_settings
from app.services.allegro_import import build_allegro_client
from app.services.allegro_sync import ImportAlreadyRunning, import_lock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MessageSyncResult:
    threads_synced: int
    messages_added: int


class MessageSyncService:
    def __init__(
        self,
        repository: MessageRepository,
        adapter: AllegroMessagingAdapter,
        seller_login: str | None,
    ):
        self.repository = repository
        self.adapter = adapter
        self.seller_login = seller_login

    def sync(self) -> MessageSyncResult:
        threads_synced = 0
        messages_added = 0
        for page in self.adapter.iter_thread_pages():
            page_has_news = False
            for data in page:
                existing = self.repository.get_thread_by_external_id(
                    self.adapter.source, data.external_id
                )
                if self._up_to_date(existing, data):
                    continue
                page_has_news = True
                thread = self.repository.upsert_thread(self.adapter.source, data)
                threads_synced += 1
                messages = self.adapter.fetch_thread_messages(
                    data.external_id, self.seller_login
                )
                messages_added += self.repository.add_messages(thread, messages)
            if not page_has_news:
                # threads sort newest activity first, so a page with nothing
                # new means every later page is stale too
                break
        logger.info(
            "Allegro messages synced: %d threads touched, %d new messages",
            threads_synced,
            messages_added,
        )
        return MessageSyncResult(threads_synced, messages_added)

    @staticmethod
    def _up_to_date(existing, data) -> bool:
        if existing is None or data.last_message_at is None or existing.last_message_at is None:
            return False
        return (
            _as_utc(existing.last_message_at) >= data.last_message_at
            and existing.read == data.read
        )


def build_message_sync_service(db: Session) -> MessageSyncService:
    client = build_allegro_client(db)
    credential = IntegrationCredentialRepository(db).get(allegro_settings.PROVIDER)
    seller_login = credential.account_login if credential else None
    return MessageSyncService(MessageRepository(db), AllegroMessagingAdapter(client), seller_login)


def run_message_sync(db: Session) -> MessageSyncResult:
    """Run one sync, sharing the import lock so it never races a token refresh.

    Raises ImportAlreadyRunning without waiting if an order import or another
    message sync is under way.
    """
    if not import_lock.acquire(blocking=False):
        raise ImportAlreadyRunning
    try:
        return build_message_sync_service(db).sync()
    finally:
        import_lock.release()
