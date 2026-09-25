"""What the backend does by itself: import orders and read buyer messages every
so often.

One interval serves every channel (Allegro orders, Erli orders, Allegro
messages). It is kept in `app_settings`, so an operator changes it in
Integrations and it takes effect within half a minute, without a restart; until
one is saved, `ALLEGRO_IMPORT_INTERVAL_MINUTES` from the environment (15 unless
set) applies. 0 switches everything off.

Any number of backends may share a database, and laptops do: Allegro rotates
its refresh token on every use, so two backends importing on their own would
invalidate each other's token. So they take turns. Whichever holds the lease, a
row in `app_settings` it renews every half minute, runs the jobs; the others
wait, and one of them takes over when the lease has not been renewed for two
minutes (its machine was shut, or its backend stopped).
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.base import IntegrationError
from app.models.marketplace_write import AppSetting
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.services import allegro_settings, erli_import, erli_settings
from app.services.allegro_sync import (
    ImportAlreadyRunning,
    ScheduleState,
    _scheduled_run,
    run_import,
    schedule_state,
)
from app.services.message_sync import _scheduled_message_run, message_schedule_state

logger = logging.getLogger(__name__)

INTERVAL_KEY = "import_interval_minutes"
LEASE_KEY = "scheduler_lease"

# Allegro limits how often it may be asked, so nothing shorter than this
MIN_INTERVAL = 5
MAX_INTERVAL = 1440

# how often the loop looks at the clock, the interval and the lease
TICK_SECONDS = 30
LEASE_TTL = timedelta(minutes=2)
# a backend that finds its imports overdue (it was off) catches up this soon
CATCH_UP = timedelta(minutes=1)

erli_schedule_state = ScheduleState()


def get_interval(db: Session) -> int:
    """Minutes between automatic runs: the one saved in Integrations, else the
    environment's default. 0 means none."""
    setting = db.get(AppSetting, INTERVAL_KEY)
    if setting is not None:
        try:
            return max(0, int(setting.value))
        except ValueError:
            logger.warning("Ignoring the import interval %r: not a number", setting.value)
    return settings.allegro_import_interval_minutes


def set_interval(db: Session, minutes: int, user_id: int | None) -> int:
    if minutes != 0 and not MIN_INTERVAL <= minutes <= MAX_INTERVAL:
        raise ValueError(f"The interval is 0 (off) or {MIN_INTERVAL} to {MAX_INTERVAL} minutes")
    setting = db.get(AppSetting, INTERVAL_KEY)
    if setting is None:
        setting = AppSetting(key=INTERVAL_KEY)
        db.add(setting)
    setting.value = str(minutes)
    setting.updated_by_user_id = user_id
    db.commit()
    logger.info("Import interval set to %d minutes by user %s", minutes, user_id)
    return minutes


def _lease_value(holder: str, now: datetime) -> str:
    return json.dumps({"holder": holder, "at": now.isoformat()})


def hold_lease(db: Session, holder: str, now: datetime) -> bool:
    """Take the lease, or renew it when already held by `holder`; false when
    another backend holds it. The write is conditional on the row still being
    what was read, so two backends taking it at the same moment cannot both win."""
    value = _lease_value(holder, now)
    row = db.get(AppSetting, LEASE_KEY)
    if row is None:
        db.add(AppSetting(key=LEASE_KEY, value=value))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return False
        return True
    try:
        current = json.loads(row.value)
        at = datetime.fromisoformat(current["at"])
        mine = current["holder"] == holder
    except (ValueError, KeyError, TypeError):
        mine, at = False, None
    if not mine and at is not None and now - at < LEASE_TTL:
        return False
    result = db.execute(
        update(AppSetting)
        .where(AppSetting.key == LEASE_KEY, AppSetting.value == row.value)
        .values(value=value)
    )
    db.commit()
    return result.rowcount == 1


def release_lease(db: Session, holder: str) -> None:
    """Give the lease up, so another backend need not wait out the two minutes."""
    row = db.get(AppSetting, LEASE_KEY)
    if row is None:
        return
    expired = _lease_value(holder, datetime(1970, 1, 1, tzinfo=UTC))
    db.execute(
        update(AppSetting)
        .where(AppSetting.key == LEASE_KEY, AppSetting.value.like(f'%"{holder}"%'))
        .values(value=expired)
    )
    db.commit()


def _scheduled_erli_run() -> None:
    """One scheduled Erli import, on its own session. Never raises."""
    db = SessionLocal()
    try:
        if not erli_settings.build_erli_client(db).is_configured:
            return
        result = run_import(
            db,
            lambda: erli_import.build_erli_import_service(db),
            provider=erli_import.PROVIDER,
        )
        logger.info("Scheduled Erli import: %d new, %d updated", result.created, result.updated)
    except ImportAlreadyRunning:
        logger.info("Scheduled Erli import skipped: another import is running")
    except IntegrationError as exc:
        logger.warning("Scheduled Erli import failed: %s", exc)
    except Exception:
        logger.exception("Scheduled Erli import failed")
    finally:
        db.close()


@dataclass
class Job:
    name: str
    state: ScheduleState
    run: Callable[[], None]
    # when it last ran, whoever ran it (a manual import counts), so a backend
    # that was off catches up instead of waiting a whole interval; None when
    # that is not recorded
    last_at: Callable[[Session], datetime | None] | None = None
    due: datetime | None = None


def _import_last_at(provider: str) -> Callable[[Session], datetime | None]:
    def last_at(db: Session) -> datetime | None:
        credential = IntegrationCredentialRepository(db).get(provider)
        moment = credential.last_import_at if credential else None
        if moment is None:
            return None
        # SQLite gives no zone (it is UTC); PostgreSQL gives the session's
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)

    return last_at


def default_jobs() -> list[Job]:
    return [
        Job("allegro-orders", schedule_state, _scheduled_run, _import_last_at(allegro_settings.PROVIDER)),
        Job("erli-orders", erli_schedule_state, _scheduled_erli_run, _import_last_at(erli_import.PROVIDER)),
        Job("allegro-messages", message_schedule_state, _scheduled_message_run),
    ]


def plan(jobs: list[Job], holder: str, now: datetime) -> list[Job]:
    """One look at the interval and the lease: bring each job's state up to date
    and return the jobs that are due."""
    due: list[Job] = []
    db = SessionLocal()
    try:
        interval = get_interval(db)
        active = interval > 0 and hold_lease(db, holder, now)
        step = timedelta(minutes=interval)
        for job in jobs:
            state = job.state
            state.interval_minutes = interval
            state.standby = interval > 0 and not active
            if not active:
                state.running = False
                state.next_run_at = None
                job.due = None
                continue
            if not state.running:
                state.running = True
                state.started_at = now
            if job.due is None:
                last = job.last_at(db) if job.last_at else None
                job.due = last + step if last else now + step
                if job.due < now:
                    job.due = now + CATCH_UP
            else:
                # a shorter interval takes effect at once
                job.due = min(job.due, now + step)
            state.next_run_at = job.due
            if job.due <= now:
                due.append(job)
        return due
    finally:
        db.close()


async def run_jobs(
    jobs: list[Job],
    holder: str | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """Run the jobs when they are due, until cancelled. The jobs are blocking
    (HTTP and database), so each runs in a worker thread."""
    holder = holder or uuid.uuid4().hex
    logger.info(
        "Imports scheduled every %d minutes unless Integrations says otherwise; "
        "backends sharing a database take turns",
        settings.allegro_import_interval_minutes,
    )
    try:
        while True:
            try:
                for job in await asyncio.to_thread(plan, jobs, holder, clock()):
                    job.state.next_run_at = None
                    try:
                        await asyncio.to_thread(job.run)
                    except Exception:
                        # the jobs answer for themselves; whatever slips out must not
                        # stop the others or bring this one round again in half a minute
                        logger.exception("Scheduled job %s failed", job.name)
                    now = clock()
                    job.state.last_run_at = now
                    job.due = now + timedelta(minutes=job.state.interval_minutes)
            except asyncio.CancelledError:
                raise
            except Exception:
                # a database that is briefly away must not end the schedule
                logger.exception("The scheduler could not run its jobs; trying again")
            await sleep(TICK_SECONDS)
    finally:
        for job in jobs:
            job.state.running = False
            job.state.next_run_at = None
        db = SessionLocal()
        try:
            release_lease(db, holder)
        except Exception:
            logger.warning("Could not give up the scheduler's lease", exc_info=True)
        finally:
            db.close()
