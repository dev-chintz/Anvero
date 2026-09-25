"""The status page's verdicts, from what Anvero holds; nothing reaches a
marketplace."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.models.integration import IntegrationCredential, IntegrationSettings
from app.services import allegro_settings, app_status, erli_import
from app.services.allegro_sync import ScheduleState

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_schedules_configured(monkeypatch):
    """The verdicts depend on whether a schedule is switched on, and that comes
    from the machine's own `.env`: these tests start from none, and the ones about
    a schedule set it themselves."""
    monkeypatch.setattr(settings, "allegro_import_interval_minutes", 0)


def _application(session):
    session.add(
        IntegrationSettings(
            provider=allegro_settings.PROVIDER,
            client_id="id",
            client_secret="secret",
            user_agent="Anvero/1.0",
            environment="sandbox",
        )
    )
    session.commit()


def _credential(session, provider=allegro_settings.PROVIDER, **fields):
    credential = IntegrationCredential(
        provider=provider, refresh_token="t", seed_fingerprint="f", **fields
    )
    session.add(credential)
    session.commit()
    return credential


def _allegro(session, state=None):
    return app_status.allegro_health(session, NOW, state or ScheduleState())


def test_nothing_set_up_is_off_not_an_error(session):
    health = _allegro(session)

    assert health.state == "off"
    assert health.problems == []


def test_an_application_without_an_account_is_a_warning(session):
    _application(session)

    health = _allegro(session)

    assert health.state == "warning"
    assert health.problems == ["not_connected"]


def test_a_connected_account_that_imported_is_ok_and_its_token_lasts_three_months(session):
    _application(session)
    issued = NOW - timedelta(days=1)
    _credential(
        session,
        token_issued_at=issued,
        account_login="seller",
        last_import_at=NOW - timedelta(minutes=5),
        last_import_created=2,
        last_import_updated=1,
    )

    health = _allegro(session)

    assert health.state == "ok"
    assert health.account_login == "seller"
    assert health.token_expires_at == issued + timedelta(days=90)
    assert (health.last_import.created, health.last_import.updated) == (2, 1)


@pytest.mark.parametrize(
    ("age", "problem", "state"),
    [(timedelta(days=80), "token_expiring", "warning"), (timedelta(days=91), "token_expired", "error")],
)
def test_an_old_token_is_flagged(session, age, problem, state):
    _application(session)
    _credential(session, token_issued_at=NOW - age, last_import_at=NOW)

    health = _allegro(session)

    assert health.problems == [problem]
    assert health.state == state


def test_an_account_that_never_imported_is_unproven(session):
    _application(session)
    _credential(session, token_issued_at=NOW)

    health = _allegro(session)

    assert health.state == "warning"
    assert health.problems == ["never_imported"]


def test_a_failed_last_import_is_an_error_with_its_message(session):
    _application(session)
    _credential(
        session, token_issued_at=NOW, last_import_at=NOW, last_import_error="token rejected"
    )

    health = _allegro(session)

    assert health.state == "error"
    assert health.problems == ["last_import_failed"]
    assert health.last_import.error == "token rejected"


def test_a_running_schedule_with_recent_imports_is_ok(session):
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW - timedelta(minutes=20))
    state = ScheduleState(
        interval_minutes=15, running=True, started_at=NOW - timedelta(hours=5)
    )

    health = _allegro(session, state)

    assert health.state == "ok"
    assert health.schedule.running is True
    assert health.schedule.interval_minutes == 15


def test_a_schedule_that_has_not_imported_for_three_intervals_is_overdue(session):
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW - timedelta(minutes=50))
    state = ScheduleState(
        interval_minutes=15, running=True, started_at=NOW - timedelta(hours=5)
    )

    assert _allegro(session, state).problems == ["import_overdue"]


def test_a_backend_just_restarted_is_not_overdue(session):
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW - timedelta(days=2))
    state = ScheduleState(
        interval_minutes=15, running=True, started_at=NOW - timedelta(minutes=10)
    )

    assert _allegro(session, state).problems == []


def test_a_schedule_configured_but_not_running_here_is_flagged(session, monkeypatch):
    monkeypatch.setattr(settings, "allegro_import_interval_minutes", 15)
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW)

    health = _allegro(session)

    # one interval serves both loops, so both are missing
    assert health.problems == ["schedule_stopped", "message_schedule_stopped"]
    assert health.schedule.interval_minutes == 15
    assert health.schedule.running is False


def test_a_schedule_waiting_for_another_backend_is_not_a_problem(session, monkeypatch):
    monkeypatch.setattr(settings, "allegro_import_interval_minutes", 15)
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW)
    waiting = ScheduleState(interval_minutes=15, standby=True)

    health = app_status.allegro_health(session, NOW, waiting, ScheduleState(standby=True))

    assert health.problems == []
    assert health.schedule.standby is True


def test_the_interval_saved_in_integrations_is_the_one_reported(session):
    from app.services.schedule import set_interval

    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW)
    set_interval(session, 30, None)

    health = app_status.allegro_health(session, NOW, ScheduleState(), ScheduleState())

    assert health.schedule.interval_minutes == 30
    assert health.message_schedule.interval_minutes == 30


def test_erli_with_a_key_reports_its_schedule(session, monkeypatch):
    monkeypatch.setattr(settings, "erli_api_key", "key")
    monkeypatch.setattr(settings, "allegro_import_interval_minutes", 15)
    _credential(session, provider=erli_import.PROVIDER, last_import_at=NOW)

    health = app_status.erli_health(session)

    assert health.schedule is not None
    assert health.schedule.interval_minutes == 15


def test_erli_without_a_key_is_off(session, monkeypatch):
    monkeypatch.setattr(settings, "erli_api_key", "")

    health = app_status.erli_health(session)

    assert health.state == "off"
    assert health.schedule is None


def test_erli_with_a_key_but_no_import_yet_is_unproven(session, monkeypatch):
    monkeypatch.setattr(settings, "erli_api_key", "key")

    health = app_status.erli_health(session)

    assert health.state == "warning"
    assert health.problems == ["never_imported"]


def test_erli_with_a_key_shows_its_last_import(session, monkeypatch):
    monkeypatch.setattr(settings, "erli_api_key", "key")
    _credential(
        session, provider=erli_import.PROVIDER, last_import_at=NOW, last_import_error="refused"
    )

    health = app_status.erli_health(session)

    assert health.state == "error"
    assert health.last_import.error == "refused"


def test_the_whole_status_carries_safe_mode_and_the_version(session):
    status = app_status.app_status(session, NOW)

    assert status.safe_mode is True
    assert status.version == settings.app_version
    assert status.checked_at == NOW


def test_the_message_schedule_is_reported_beside_the_import_schedule(session):
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW)
    messages = ScheduleState(interval_minutes=5, running=True, started_at=NOW)

    health = app_status.allegro_health(session, NOW, ScheduleState(), messages)

    assert health.problems == []
    assert health.message_schedule.running is True
    assert health.message_schedule.interval_minutes == 5
    assert health.schedule.interval_minutes == 0


def test_a_message_schedule_configured_but_not_running_here_is_flagged(session, monkeypatch):
    monkeypatch.setattr(settings, "allegro_import_interval_minutes", 5)
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW)

    health = app_status.allegro_health(session, NOW, ScheduleState(), ScheduleState())

    assert "message_schedule_stopped" in health.problems
    assert health.message_schedule.interval_minutes == 5


def test_a_message_schedule_that_is_off_is_not_a_problem(session):
    _application(session)
    _credential(session, token_issued_at=NOW, last_import_at=NOW)

    health = app_status.allegro_health(session, NOW, ScheduleState(), ScheduleState())

    assert health.problems == []
    assert health.message_schedule.interval_minutes == 0
