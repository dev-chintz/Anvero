"""The update history: an update from Settings is closed by the backend it brings up."""

from datetime import UTC, datetime, timedelta

from app.models.app_update import AppUpdate
from app.services import update_history

OLD = "a" * 40
NEW = "b" * 40
# before anything the tests start "now"
T0 = datetime.now(UTC) - timedelta(days=2)


def _rows(session):
    return session.query(AppUpdate).order_by(AppUpdate.started_at).all()


def test_a_first_start_is_written_down_as_reached_outside_settings(session):
    update_history.note_running_version(session, OLD, now=T0)

    (row,) = _rows(session)
    assert (row.from_commit, row.to_commit, row.result, row.via) == (None, OLD, "ok", "outside")


def test_a_restart_on_the_same_version_writes_nothing(session):
    update_history.note_running_version(session, OLD, now=T0)
    update_history.note_running_version(session, OLD[:7], now=T0 + timedelta(hours=1))

    assert len(_rows(session)) == 1


def test_the_new_backend_closes_the_update_that_brought_it(session):
    update_history.note_running_version(session, OLD, now=T0)
    started = update_history.record_start(session, OLD, NEW, None)

    # the old backend restarting while the new one is being pulled changes nothing
    update_history.note_running_version(session, OLD)
    assert started.finished_at is None

    update_history.note_running_version(session, NEW)

    rows = _rows(session)
    assert len(rows) == 2
    assert (rows[1].from_commit, rows[1].to_commit, rows[1].result, rows[1].via) == (OLD, NEW, "ok", "settings")


def test_a_version_put_in_by_hand_follows_the_last_one(session):
    update_history.note_running_version(session, OLD, now=T0)
    update_history.note_running_version(session, NEW, now=T0 + timedelta(hours=1))

    assert (_rows(session)[1].from_commit, _rows(session)[1].via) == (OLD, "outside")


def test_an_update_the_updater_says_failed_is_closed_as_failed(session):
    row = update_history.record_start(session, OLD, NEW, None)
    updater = {
        "running": False,
        "result": "failed",
        "finished_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        "log": "$ docker compose pull\nmanifest unknown",
    }

    update_history.resolve_pending(session, OLD, updater)

    assert row.result == "failed"
    assert "manifest unknown" in row.detail


def test_an_earlier_failed_run_of_the_updater_is_not_blamed_on_this_update(session):
    row = update_history.record_start(session, OLD, NEW, None)
    earlier = {"running": False, "result": "failed", "finished_at": (T0 - timedelta(days=1)).isoformat(), "log": "old"}

    update_history.resolve_pending(session, OLD, earlier)

    assert row.finished_at is None


def test_an_update_that_never_arrives_is_failed_in_the_end(session):
    row = update_history.record_start(session, OLD, NEW, None)

    update_history.resolve_pending(session, OLD, None, now=datetime.now(UTC) + timedelta(minutes=5))
    assert row.finished_at is None

    update_history.resolve_pending(session, OLD, None, now=datetime.now(UTC) + timedelta(minutes=30))
    assert row.result == "failed"
    assert "did not start" in row.detail


def test_a_refused_start_is_kept_as_failed(session):
    update_history.record_refused(session, OLD, NEW, None, "The updater could not be reached")

    (row,) = _rows(session)
    assert (row.result, row.detail) == ("failed", "The updater could not be reached")
