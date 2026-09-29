"""The history of the version the backend runs (Settings, Updates; `DECISIONS.md`,
"Update history and progress").

An update started from Settings replaces the backend that started it, so no one
process sees it from start to end. The backend that takes the button writes a
row, still open; the new backend closes it on its first start, when it finds
itself on the version the row was for. One that never arrives is closed as
failed from what the updater said about its run, or after `STALE_AFTER`.
A version reached any other way (by hand, a first start) is written by the
backend that finds itself on it, already closed.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app_update import AppUpdate

logger = logging.getLogger(__name__)

# an update not over by then has failed: pulling and recreating takes minutes
STALE_AFTER = timedelta(minutes=20)
HISTORY_SHOWN = 20
DETAIL_KEPT = 4000

VIA_SETTINGS = "settings"
VIA_OUTSIDE = "outside"
OK = "ok"
FAILED = "failed"


def _aware(moment: datetime) -> datetime:
    # SQLite gives back naive datetimes; everything here is UTC
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _same(a: str | None, b: str | None) -> bool:
    """One commit, however long either spelling is (`APP_COMMIT` may be short)."""
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _arrived(row: AppUpdate, current: str | None) -> bool:
    """The update has brought a new version up: the one asked for, or a newer one.

    The updater pulls the newest published images, not the commit the button
    named, so a version published between the last check and the press is the
    one that arrives (2026-09-29: asked for d643499, 78bd456 came up). Any
    version other than the one the update started from is its arrival.
    """
    if not current:
        return False
    return _same(row.to_commit, current) or not _same(row.from_commit, current)


def _pending(db: Session) -> list[AppUpdate]:
    return list(db.scalars(select(AppUpdate).where(AppUpdate.finished_at.is_(None))))


def _last_ok(db: Session) -> AppUpdate | None:
    return db.scalars(
        select(AppUpdate).where(AppUpdate.result == OK).order_by(AppUpdate.finished_at.desc()).limit(1)
    ).first()


def record_start(
    db: Session, from_commit: str | None, to_commit: str, user_id: int | None
) -> AppUpdate:
    """The button was pressed and the updater took it."""
    row = AppUpdate(
        from_commit=from_commit,
        to_commit=to_commit,
        started_at=datetime.now(UTC),
        started_by_user_id=user_id,
        via=VIA_SETTINGS,
    )
    db.add(row)
    db.commit()
    return row


def record_refused(
    db: Session, from_commit: str | None, to_commit: str, user_id: int | None, why: str
) -> None:
    """The button was pressed and the updater could not start: kept, so the history says so."""
    now = datetime.now(UTC)
    db.add(
        AppUpdate(
            from_commit=from_commit,
            to_commit=to_commit,
            started_at=now,
            started_by_user_id=user_id,
            finished_at=now,
            result=FAILED,
            via=VIA_SETTINGS,
            detail=why[:DETAIL_KEPT],
        )
    )
    db.commit()


def note_running_version(db: Session, current: str | None, now: datetime | None = None) -> None:
    """On start: close the update that brought this version, or write down one
    that arrived some other way."""
    if not current:
        return
    now = now or datetime.now(UTC)
    for row in _pending(db):
        if _arrived(row, current):
            # what actually runs, which may be newer than what was asked for
            row.to_commit = current
            row.finished_at, row.result = now, OK
            db.commit()
            return
    last = _last_ok(db)
    # a restart on the same version is not a change; an open update to another
    # version is still under way, or failed, and is closed by `resolve_pending`
    if last is not None and _same(last.to_commit, current):
        return
    db.add(
        AppUpdate(
            from_commit=last.to_commit if last else None,
            to_commit=current,
            started_at=now,
            finished_at=now,
            result=OK,
            via=VIA_OUTSIDE,
        )
    )
    db.commit()
    logger.info("Running %s, reached outside Settings", current[:7])


def resolve_pending(
    db: Session, current: str | None, updater: dict | None, now: datetime | None = None
) -> None:
    """Close what can be told about an open update: arrived, failed by the
    updater's own word, or never come."""
    now = now or datetime.now(UTC)
    changed = False
    for row in _pending(db):
        started = _aware(row.started_at)
        if _arrived(row, current):
            row.to_commit = current
            row.finished_at, row.result = now, OK
            changed = True
            continue
        finished = (updater or {}).get("finished_at")
        if (
            updater
            and not updater.get("running")
            and updater.get("result") == FAILED
            and finished
            and _aware(datetime.fromisoformat(finished)) >= started
        ):
            row.finished_at, row.result = now, FAILED
            row.detail = (updater.get("log") or "The updater reported a failure")[-DETAIL_KEPT:]
            changed = True
        elif now - started > STALE_AFTER:
            row.finished_at, row.result = now, FAILED
            row.detail = f"The new version did not start within {int(STALE_AFTER.total_seconds() // 60)} minutes"
            changed = True
    if changed:
        db.commit()


def history(db: Session) -> list[AppUpdate]:
    return list(
        db.scalars(select(AppUpdate).order_by(AppUpdate.started_at.desc()).limit(HISTORY_SHOWN))
    )
