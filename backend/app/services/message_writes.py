"""Replying to a buyer from Anvero.

Goes through MarketplaceWriter, like a status or a tracking number: with safe
mode on the reply is recorded as what would have been sent, and nothing
reaches the buyer. Only Allegro is wired; Erli has no messaging endpoint in
its public API (INTEGRATIONS.md, "Buyer messages").
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.integrations.allegro.client import AllegroClient
from app.integrations.base import IntegrationUnavailable
from app.models.message import Message, MessageThread
from app.models.order import OrderSource
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.message_repository import MessageRepository
from app.services import allegro_settings
from app.services.allegro_import import build_allegro_client
from app.services.allegro_sync import import_lock
from app.services.marketplace_writes import MarketplaceWriter, WriteResult

logger = logging.getLogger(__name__)

# shares the import lock's timeout: a reply also refreshes the rotating token
WRITE_LOCK_TIMEOUT_SECONDS = 60

ClientFactory = Callable[[], AllegroClient]


class MessageWrites:
    def __init__(self, db: Session, client_factory: ClientFactory | None = None):
        self.db = db
        self.repository = MessageRepository(db)
        self.writer = MarketplaceWriter(db)
        self._client_factory = client_factory or (lambda: build_allegro_client(db))

    def reply(
        self, thread: MessageThread, text: str, user_id: int | None
    ) -> tuple[Message, WriteResult]:
        """Record the reply in Anvero and send it, unless safe mode holds it back.

        The message is kept in Anvero whatever becomes of sending it - the
        operator wrote it, and marketplace_writes holds the true outcome
        (order_writes.py does the same for a tracking number).
        """
        if thread.source is not OrderSource.ALLEGRO:
            raise ValueError(f"{thread.source.value} has no messaging endpoint yet")

        seller_login = self._seller_login()
        sent_at = datetime.now(UTC)

        def send():
            client = self._client_factory()
            if not import_lock.acquire(timeout=WRITE_LOCK_TIMEOUT_SECONDS):
                raise IntegrationUnavailable(
                    "An Allegro import or message sync is running; the reply "
                    "was not sent, try again in a minute"
                )
            try:
                return client.reply_to_thread(thread.external_id, text)
            finally:
                import_lock.release()

        result = self.writer.write(
            OrderSource.ALLEGRO,
            "message_reply",
            {"threadExternalId": thread.external_id, "text": text},
            send,
            order_id=None,
            user_id=user_id,
            raise_errors=False,
        )
        # the writer rolled back on a failed send, which expires objects
        # loaded before it (order_writes.py does the same)
        self.db.refresh(thread)
        answer = result.response if isinstance(result.response, dict) else {}
        external_id = answer.get("id") if isinstance(answer.get("id"), str) else None
        message = self.repository.add_reply(thread, text, external_id, seller_login, sent_at)
        return message, result

    def _seller_login(self) -> str | None:
        credential = IntegrationCredentialRepository(self.db).get(allegro_settings.PROVIDER)
        return credential.account_login if credential else None
