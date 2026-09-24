"""Syncing Allegro's Message Center: what gets read again, and what does not."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.integrations.base import IntegrationUnavailable
from app.models.message import MessageThread
from app.models.order import OrderSource
from app.repositories.message_repository import MessageRepository
from app.schemas.message import SyncedMessage, SyncedThread
from app.services import allegro_sync, message_sync
from app.services.message_sync import (
    ImportAlreadyRunning,
    MessageSyncService,
    run_message_sync,
)

T1 = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)


def _thread(external_id="T1", last=T1, read=False, login="buyer1"):
    return SyncedThread(
        external_id=external_id, interlocutor_login=login, last_message_at=last, read=read
    )


def _message(external_id="M1", sent_at=T1, text="hi"):
    return SyncedMessage(external_id=external_id, direction="IN", text=text, sent_at=sent_at)


class FakeAdapter:
    source = OrderSource.ALLEGRO

    def __init__(self, pages, messages_by_thread=None):
        self.pages = pages
        self.messages_by_thread = messages_by_thread or {}
        self.message_fetches = []

    def iter_thread_pages(self):
        yield from self.pages

    def fetch_thread_messages(self, external_id, seller_login):
        self.message_fetches.append(external_id)
        return self.messages_by_thread.get(external_id, [])


def test_a_new_thread_is_stored_with_its_messages(session):
    adapter = FakeAdapter([[_thread("T1")]], {"T1": [_message("M1")]})

    result = MessageSyncService(MessageRepository(session), adapter, "seller1").sync()

    assert (result.threads_synced, result.messages_added) == (1, 1)
    thread = session.query(MessageThread).one()
    assert thread.external_id == "T1"
    assert len(thread.messages) == 1


def test_a_thread_unchanged_since_the_last_sync_is_not_read_again(session):
    repository = MessageRepository(session)
    adapter = FakeAdapter([[_thread("T1", last=T1, read=True)]])
    MessageSyncService(repository, adapter, "seller1").sync()
    assert adapter.message_fetches == ["T1"]

    adapter2 = FakeAdapter([[_thread("T1", last=T1, read=True)]])
    result = MessageSyncService(repository, adapter2, "seller1").sync()

    assert result.threads_synced == 0
    assert adapter2.message_fetches == []


def test_a_thread_whose_last_message_moved_is_read_again(session):
    repository = MessageRepository(session)
    MessageSyncService(repository, FakeAdapter([[_thread("T1", last=T1)]]), "seller1").sync()

    adapter2 = FakeAdapter([[_thread("T1", last=T2)]], {"T1": [_message("M2", sent_at=T2)]})
    result = MessageSyncService(repository, adapter2, "seller1").sync()

    assert result.threads_synced == 1
    assert adapter2.message_fetches == ["T1"]


def test_a_thread_whose_read_flag_moved_is_read_again(session):
    repository = MessageRepository(session)
    MessageSyncService(repository, FakeAdapter([[_thread("T1", last=T1, read=False)]]), "s").sync()

    adapter2 = FakeAdapter([[_thread("T1", last=T1, read=True)]])
    result = MessageSyncService(repository, adapter2, "s").sync()

    assert result.threads_synced == 1
    thread = session.query(MessageThread).one()
    assert thread.read is True


def test_a_page_with_nothing_new_stops_the_sync_before_the_next_page(session):
    repository = MessageRepository(session)
    MessageSyncService(repository, FakeAdapter([[_thread("T1", last=T1, read=True)]]), "s").sync()

    adapter2 = FakeAdapter(
        [[_thread("T1", last=T1, read=True)], [_thread("T2", last=T1)]],
    )
    result = MessageSyncService(repository, adapter2, "s").sync()

    assert result.threads_synced == 0
    # the second page, which would have found T2 new, is never asked for
    assert session.query(MessageThread).count() == 1


def test_a_message_already_stored_is_not_added_twice(session):
    repository = MessageRepository(session)
    MessageSyncService(
        repository, FakeAdapter([[_thread("T1", last=T1)]], {"T1": [_message("M1")]}), "s"
    ).sync()

    adapter2 = FakeAdapter(
        [[_thread("T1", last=T2)]], {"T1": [_message("M1"), _message("M2", sent_at=T2)]}
    )
    result = MessageSyncService(repository, adapter2, "s").sync()

    assert result.messages_added == 1
    thread = session.query(MessageThread).one()
    assert len(thread.messages) == 2


def test_a_second_sync_is_refused_while_one_holds_the_lock(session):
    assert allegro_sync.import_lock.acquire(blocking=False)
    try:
        with pytest.raises(ImportAlreadyRunning):
            run_message_sync(session)
    finally:
        allegro_sync.import_lock.release()


# --- the schedule -----------------------------------------------------------

class _Client:
    def __init__(self, configured):
        self.is_configured = configured


class _Session:
    closed = False

    def close(self):
        self.closed = True


def _patch_scheduled_run(monkeypatch, configured=True, sync=None):
    session = _Session()
    monkeypatch.setattr(message_sync, "SessionLocal", lambda: session)
    monkeypatch.setattr(message_sync, "build_allegro_client", lambda db: _Client(configured))
    calls = []

    def fake_sync(db):
        calls.append(db)
        if sync is not None:
            return sync()
        return message_sync.MessageSyncResult(threads_synced=2, messages_added=5)

    monkeypatch.setattr(message_sync, "run_message_sync", fake_sync)
    return session, calls


def test_a_scheduled_run_syncs_and_closes_its_session(monkeypatch):
    session, calls = _patch_scheduled_run(monkeypatch)

    message_sync._scheduled_message_run()

    assert calls == [session]
    assert session.closed


def test_a_scheduled_run_with_no_account_connected_does_nothing(monkeypatch):
    session, calls = _patch_scheduled_run(monkeypatch, configured=False)

    message_sync._scheduled_message_run()

    assert calls == []
    assert session.closed


@pytest.mark.parametrize(
    "error", [ImportAlreadyRunning(), IntegrationUnavailable("Allegro 503"), RuntimeError("boom")]
)
def test_a_scheduled_run_never_raises(monkeypatch, error):
    def fail():
        raise error

    session, _ = _patch_scheduled_run(monkeypatch, sync=fail)

    message_sync._scheduled_message_run()

    assert session.closed


def test_the_message_scheduler_does_nothing_when_the_interval_is_zero():
    # would hang the test if it looped
    asyncio.run(asyncio.wait_for(message_sync.message_scheduler(0), timeout=1))


def test_the_message_scheduler_syncs_each_interval_on_its_own_state(monkeypatch):
    state = allegro_sync.ScheduleState()
    order_state = allegro_sync.ScheduleState()
    monkeypatch.setattr(message_sync, "message_schedule_state", state)
    monkeypatch.setattr(allegro_sync, "schedule_state", order_state)
    calls = []
    real_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        if len(calls) >= 2:
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr(allegro_sync.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(message_sync, "_scheduled_message_run", lambda: calls.append(1))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(message_sync.message_scheduler(7))

    assert len(calls) == 2
    assert state.interval_minutes == 7
    assert state.running is False
    assert state.last_run_at is not None
    # the order import's own schedule is untouched
    assert order_state.interval_minutes == 0
