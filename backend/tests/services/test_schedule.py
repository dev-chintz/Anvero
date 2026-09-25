"""The backend's own schedule: one interval for every channel, kept in the
database, and one backend at a time doing the work."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.integration import IntegrationCredential
from app.models.marketplace_write import AppSetting
from app.services import allegro_settings, schedule
from app.services.allegro_sync import ScheduleState

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


@pytest.fixture
def db_factory(session, monkeypatch):
    """`plan` and the loop open their own sessions; give them the test database."""
    factory = sessionmaker(bind=session.get_bind())
    monkeypatch.setattr(schedule, "SessionLocal", factory)
    monkeypatch.setattr(settings, "allegro_import_interval_minutes", 15)
    return factory


def _job(last_at=None, run=lambda: None):
    return schedule.Job("test", ScheduleState(), run, last_at)


class TestInterval:
    def test_it_is_the_default_from_the_environment_until_one_is_saved(self, session, monkeypatch):
        monkeypatch.setattr(settings, "allegro_import_interval_minutes", 15)

        assert schedule.get_interval(session) == 15

    def test_the_saved_one_wins_and_zero_means_off(self, session):
        schedule.set_interval(session, 30, None)
        assert schedule.get_interval(session) == 30

        schedule.set_interval(session, 0, None)
        assert schedule.get_interval(session) == 0

    @pytest.mark.parametrize("minutes", [1, 4, 1441])
    def test_a_value_under_five_minutes_or_beyond_a_day_is_refused(self, session, minutes):
        with pytest.raises(ValueError):
            schedule.set_interval(session, minutes, None)

    def test_a_saved_value_that_is_not_a_number_falls_back_to_the_default(self, session):
        session.add(AppSetting(key=schedule.INTERVAL_KEY, value="often"))
        session.commit()

        assert schedule.get_interval(session) == settings.allegro_import_interval_minutes


class TestLease:
    def test_the_first_backend_holds_it_and_a_second_is_kept_out(self, session):
        assert schedule.hold_lease(session, "a", NOW) is True
        assert schedule.hold_lease(session, "b", NOW + timedelta(seconds=30)) is False

    def test_the_holder_renews_it_and_so_keeps_it(self, session):
        schedule.hold_lease(session, "a", NOW)

        assert schedule.hold_lease(session, "a", NOW + timedelta(minutes=1)) is True
        # a minute after the renewal it is still a's
        assert schedule.hold_lease(session, "b", NOW + timedelta(minutes=2)) is False

    def test_another_takes_over_when_it_was_not_renewed_for_two_minutes(self, session):
        schedule.hold_lease(session, "a", NOW)

        assert schedule.hold_lease(session, "b", NOW + schedule.LEASE_TTL) is True
        assert schedule.hold_lease(session, "a", NOW + schedule.LEASE_TTL) is False

    def test_giving_it_up_lets_another_take_it_at_once(self, session):
        schedule.hold_lease(session, "a", NOW)

        schedule.release_lease(session, "a")

        assert schedule.hold_lease(session, "b", NOW + timedelta(seconds=1)) is True

    def test_giving_it_up_does_not_take_it_from_the_one_that_holds_it(self, session):
        schedule.hold_lease(session, "a", NOW)

        schedule.release_lease(session, "b")

        assert schedule.hold_lease(session, "b", NOW + timedelta(seconds=1)) is False


class TestPlan:
    def test_with_the_interval_off_nothing_runs_and_no_lease_is_taken(self, session, db_factory):
        schedule.set_interval(session, 0, None)
        job = _job()

        due = schedule.plan([job], "a", NOW)

        assert due == []
        assert job.state.running is False
        assert job.state.standby is False
        assert schedule.hold_lease(session, "b", NOW) is True

    def test_the_first_run_is_one_interval_after_start(self, db_factory):
        job = _job()

        due = schedule.plan([job], "a", NOW)

        assert due == []
        assert job.state.running is True
        assert job.state.interval_minutes == 15
        assert job.state.started_at == NOW
        assert job.state.next_run_at == NOW + timedelta(minutes=15)

    def test_it_is_due_when_the_interval_has_passed(self, db_factory):
        job = _job()
        schedule.plan([job], "a", NOW)

        assert schedule.plan([job], "a", NOW + timedelta(minutes=14)) == []
        assert schedule.plan([job], "a", NOW + timedelta(minutes=15)) == [job]

    def test_a_backend_that_was_off_catches_up_a_minute_after_it_starts(self, db_factory):
        job = _job(last_at=lambda _db: NOW - timedelta(hours=3))

        due = schedule.plan([job], "a", NOW)

        assert due == []
        assert job.state.next_run_at == NOW + schedule.CATCH_UP

    def test_an_import_by_hand_a_moment_ago_postpones_the_first_run(self, db_factory):
        job = _job(last_at=lambda _db: NOW - timedelta(minutes=4))

        schedule.plan([job], "a", NOW)

        assert job.state.next_run_at == NOW + timedelta(minutes=11)

    def test_a_shorter_interval_takes_effect_at_once(self, session, db_factory):
        job = _job()
        schedule.plan([job], "a", NOW)
        schedule.set_interval(session, 5, None)

        schedule.plan([job], "a", NOW + timedelta(seconds=30))

        assert job.state.next_run_at == NOW + timedelta(seconds=30, minutes=5)

    def test_another_backend_holding_the_lease_puts_this_one_on_standby(self, session, db_factory):
        schedule.hold_lease(session, "other", NOW)
        job = _job()

        due = schedule.plan([job], "a", NOW + timedelta(seconds=30))

        assert due == []
        assert job.state.standby is True
        assert job.state.running is False
        assert job.state.next_run_at is None

    def test_it_takes_over_when_the_other_backend_goes_quiet(self, session, db_factory):
        schedule.hold_lease(session, "other", NOW)
        job = _job()
        schedule.plan([job], "a", NOW + timedelta(seconds=30))
        assert job.state.standby is True

        schedule.plan([job], "a", NOW + schedule.LEASE_TTL)

        assert job.state.standby is False
        assert job.state.running is True


def _run_for_forty_minutes(job, holder="a"):
    """Run the loop with a clock that moves a minute per round, until 40 minutes."""
    clock_now = [NOW]

    async def sleep(_seconds):
        clock_now[0] += timedelta(minutes=1)
        if clock_now[0] > NOW + timedelta(minutes=40):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(schedule.run_jobs([job], holder, sleep, lambda: clock_now[0]))
    return clock_now[0]


class TestRunJobs:
    def test_it_runs_a_job_each_interval_and_gives_the_lease_up_when_cancelled(self, db_factory):
        calls = []
        job = _job(run=lambda: calls.append(1))

        end = _run_for_forty_minutes(job)

        # at 15 and at 30 minutes
        assert len(calls) == 2
        assert job.state.last_run_at is not None
        assert job.state.running is False
        db = db_factory()
        try:
            assert schedule.hold_lease(db, "b", end) is True
        finally:
            db.close()

    def test_a_job_that_fails_does_not_end_the_schedule(self, db_factory):
        calls = []

        def run():
            calls.append(1)
            raise RuntimeError("boom")

        _run_for_forty_minutes(_job(run=run))

        assert len(calls) == 2


class TestErliRun:
    def test_it_does_nothing_without_a_key(self, db_factory, monkeypatch):
        monkeypatch.setattr(settings, "erli_api_key", "")
        called = []
        monkeypatch.setattr(schedule, "run_import", lambda *a, **k: called.append(1))

        schedule._scheduled_erli_run()

        assert called == []

    def test_it_imports_from_erli_when_a_key_is_set(self, db_factory, monkeypatch):
        monkeypatch.setattr(settings, "erli_api_key", "key")
        called = []

        class _Result:
            created = 1
            updated = 2

        def fake(db, factory, provider):
            called.append(provider)
            return _Result()

        monkeypatch.setattr(schedule, "run_import", fake)

        schedule._scheduled_erli_run()

        assert called == ["ERLI"]

    def test_a_failure_is_swallowed(self, db_factory, monkeypatch):
        monkeypatch.setattr(settings, "erli_api_key", "key")

        def fake(db, factory, provider):
            raise RuntimeError("boom")

        monkeypatch.setattr(schedule, "run_import", fake)

        schedule._scheduled_erli_run()


class TestLastAt:
    def test_it_reads_when_a_channel_last_imported(self, session):
        session.add(
            IntegrationCredential(
                provider=allegro_settings.PROVIDER,
                refresh_token="t",
                seed_fingerprint="f",
                last_import_at=NOW,
            )
        )
        session.commit()

        last = schedule._import_last_at(allegro_settings.PROVIDER)(session)

        assert last == NOW

    def test_it_is_nothing_for_a_channel_that_never_imported(self, session):
        assert schedule._import_last_at("ERLI")(session) is None
