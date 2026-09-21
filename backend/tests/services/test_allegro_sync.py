"""Running an import by hand or on a schedule: one at a time, and every run
leaves a note of how it ended."""

import asyncio
from dataclasses import dataclass

import pytest

from app.integrations.base import IntegrationAuthError, IntegrationNotConfigured
from app.models.integration import IntegrationCredential
from app.services import allegro_settings, allegro_sync
from app.services.allegro_sync import ImportAlreadyRunning, run_import, scheduler


@dataclass
class _Result:
    created: int = 0
    updated: int = 0
    cancellation_warnings: int = 0


class _Service:
    def __init__(self, result=None, error=None):
        self._result = result or _Result()
        self._error = error

    def sync_orders(self):
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def credential(session):
    session.add(
        IntegrationCredential(
            provider=allegro_settings.PROVIDER, refresh_token="t", seed_fingerprint="f"
        )
    )
    session.commit()
    return session.get(IntegrationCredential, allegro_settings.PROVIDER)


def test_a_successful_run_notes_when_it_finished_and_what_it_stored(session, credential):
    run_import(session, lambda: _Service(_Result(created=3, updated=2)))

    session.refresh(credential)
    assert credential.last_import_at is not None
    assert (credential.last_import_created, credential.last_import_updated) == (3, 2)
    assert credential.last_import_error is None


def test_a_failed_run_notes_the_error_and_then_a_success_clears_it(session, credential):
    with pytest.raises(IntegrationAuthError):
        run_import(session, lambda: _Service(error=IntegrationAuthError("token rejected")))

    session.refresh(credential)
    assert credential.last_import_error == "token rejected"
    assert credential.last_import_created is None

    run_import(session, lambda: _Service(_Result(created=1)))
    session.refresh(credential)
    assert credential.last_import_error is None
    assert credential.last_import_created == 1


def test_not_configured_is_not_noted_as_a_failure(session, credential):
    with pytest.raises(IntegrationNotConfigured):
        run_import(session, lambda: _Service(error=IntegrationNotConfigured("no")))

    session.refresh(credential)
    assert credential.last_import_at is None


def test_a_run_without_a_connected_account_has_nowhere_to_note_and_still_works(session):
    result = run_import(session, lambda: _Service(_Result(created=1)))

    assert result.created == 1


def test_a_second_run_is_refused_while_one_holds_the_lock(session):
    assert allegro_sync.import_lock.acquire(blocking=False)
    try:
        with pytest.raises(ImportAlreadyRunning):
            run_import(session, lambda: _Service())
    finally:
        allegro_sync.import_lock.release()


def test_the_lock_is_released_after_a_failed_run(session):
    with pytest.raises(IntegrationAuthError):
        run_import(session, lambda: _Service(error=IntegrationAuthError("x")))

    assert allegro_sync.import_lock.acquire(blocking=False)
    allegro_sync.import_lock.release()


def test_the_scheduler_does_nothing_when_the_interval_is_zero():
    # would hang the test if it looped
    asyncio.run(asyncio.wait_for(scheduler(0), timeout=1))


def test_the_scheduler_runs_an_import_each_interval(monkeypatch):
    calls = []
    real_sleep = asyncio.sleep

    async def fast_sleep(_seconds):
        if len(calls) >= 2:
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr(allegro_sync.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(allegro_sync, "_scheduled_run", lambda: calls.append(1))

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scheduler(5))

    assert len(calls) == 2
