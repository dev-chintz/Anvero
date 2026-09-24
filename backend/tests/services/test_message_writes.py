"""Replying to a buyer from Anvero, through safe mode."""

import pytest

from app.integrations.base import IntegrationAuthError
from app.models.marketplace_write import MarketplaceWrite, WriteOutcome
from app.models.message import MessageDirection
from app.models.order import OrderSource
from app.repositories.message_repository import MessageRepository
from app.schemas.message import SyncedThread
from app.services.marketplace_writes import set_safe_mode
from app.services.message_writes import MessageWrites

# `session` comes from tests/conftest.py


class FakeAllegro:
    def __init__(self, error=None, message_id="M-new"):
        self.replies = []
        self.error = error
        self.message_id = message_id

    def reply_to_thread(self, thread_id, text):
        if self.error:
            raise self.error
        self.replies.append((thread_id, text))
        return {"id": self.message_id}


def _thread(session, source=OrderSource.ALLEGRO):
    thread = MessageRepository(session).upsert_thread(
        source, SyncedThread(external_id="T1", interlocutor_login="buyer1")
    )
    return thread


def test_in_safe_mode_the_reply_is_only_recorded(session):
    allegro = FakeAllegro()
    thread = _thread(session)

    message, result = MessageWrites(session, client_factory=lambda: allegro).reply(
        thread, "Dziękuję!", None
    )

    assert result.outcome is WriteOutcome.DRY_RUN
    assert allegro.replies == []
    assert message.direction is MessageDirection.OUT
    assert message.created_in_anvero is True
    assert message.external_id is None
    assert thread.last_message_text == "Dziękuję!"
    assert thread.read is True


def test_with_safe_mode_off_allegro_is_told_and_the_message_gets_its_id(session):
    set_safe_mode(session, False, None)
    allegro = FakeAllegro(message_id="M-42")
    thread = _thread(session)

    message, result = MessageWrites(session, client_factory=lambda: allegro).reply(
        thread, "W drodze do Ciebie", None
    )

    assert result.outcome is WriteOutcome.SENT
    assert allegro.replies == [("T1", "W drodze do Ciebie")]
    assert message.external_id == "M-42"
    (record,) = session.query(MarketplaceWrite).all()
    assert record.action == "message_reply"


def test_a_refused_reply_is_kept_in_anvero_and_marked_failed(session):
    set_safe_mode(session, False, None)
    allegro = FakeAllegro(error=IntegrationAuthError("no scope"))
    thread = _thread(session)

    message, result = MessageWrites(session, client_factory=lambda: allegro).reply(
        thread, "hello", None
    )

    assert result.outcome is WriteOutcome.FAILED
    assert message.external_id is None
    assert message.text == "hello"


def test_erli_has_no_messaging_endpoint_yet(session):
    thread = _thread(session, source=OrderSource.ERLI)

    with pytest.raises(ValueError, match="ERLI"):
        MessageWrites(session, client_factory=lambda: FakeAllegro()).reply(thread, "hi", None)
