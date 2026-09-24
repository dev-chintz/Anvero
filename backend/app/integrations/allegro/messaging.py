"""Allegro's Message Center: reading threads and their messages, and replying.

Kept apart from adapter.py, which is the MarketplaceAdapter protocol for
orders: messages are a resource of their own, read on their own schedule, not
part of an order import. See INTEGRATIONS.md, "Buyer messages", for what is
confirmed and what is read from memory.
"""

import logging
from collections.abc import Iterator

from app.integrations.allegro.client import MAX_PAGE_SIZE, AllegroClient
from app.integrations.allegro.mapper import map_message, map_thread
from app.integrations.base import IntegrationUnavailable
from app.models.order import OrderSource
from app.schemas.message import SyncedMessage, SyncedThread

logger = logging.getLogger(__name__)

# a safety stop, not a limit anyone should meet in one sync
MAX_PAGES = 500


class AllegroMessagingAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, client: AllegroClient | None = None):
        self._client = client or AllegroClient()

    @property
    def is_configured(self) -> bool:
        return self._client.is_configured

    def iter_thread_pages(self) -> Iterator[list[SyncedThread]]:
        """Yield every page of threads, assumed newest activity first.

        A caller that only wants what changed can stop reading pages as soon
        as one comes back with nothing newer than what it already has - it
        need not call this again to get the rest. Running out of pages is an
        error, like every other pager here, so a caller never mistakes a
        partial read for a complete one.
        """
        for page in range(MAX_PAGES):
            raw = self._client.fetch_threads(MAX_PAGE_SIZE, page * MAX_PAGE_SIZE)
            threads = []
            for item in raw:
                thread = map_thread(item)
                if thread is None:
                    logger.warning("Skipping an Allegro message thread that could not be mapped")
                else:
                    threads.append(thread)
            yield threads
            if len(raw) < MAX_PAGE_SIZE:
                return
        raise IntegrationUnavailable(
            f"Allegro returned more than {MAX_PAGES * MAX_PAGE_SIZE} message threads; "
            "narrow what is read and try again"
        )

    def fetch_thread_messages(
        self, thread_external_id: str, seller_login: str | None
    ) -> list[SyncedMessage]:
        """Every message of one thread, oldest first as Allegro lists them."""
        messages: list[SyncedMessage] = []
        for page in range(MAX_PAGES):
            raw = self._client.fetch_thread_messages(
                thread_external_id, MAX_PAGE_SIZE, page * MAX_PAGE_SIZE
            )
            for item in raw:
                message = map_message(item, seller_login)
                if message is None:
                    logger.warning(
                        "Skipping a message of Allegro thread %s that could not be mapped",
                        thread_external_id,
                    )
                else:
                    messages.append(message)
            if len(raw) < MAX_PAGE_SIZE:
                return messages
        raise IntegrationUnavailable(
            f"Allegro thread {thread_external_id} has more than "
            f"{MAX_PAGES * MAX_PAGE_SIZE} messages; narrow what is read and try again"
        )

    def reply(self, thread_external_id: str, text: str) -> dict | None:
        return self._client.reply_to_thread(thread_external_id, text)
