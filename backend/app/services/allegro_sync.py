"""Running an Allegro import, by hand or on a schedule, one at a time.

Both the button and the schedule go through `run_import`, so they share one
lock and both leave a note of how they ended for Settings and the orders page
to show.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.integrations.base import IntegrationError
from app.services import allegro_settings
from app.services.allegro_import import (
    build_allegro_client,
    build_allegro_import_service,
)
from app.services.import_outcome import run_and_record
from app.services.order_import_service import ImportResult, OrderImportService

logger = logging.getLogger(__name__)

# Allegro rotates the refresh token on every use, so two imports running at
# once would both refresh it and the second refresh invalidates the token the
# first request is still using. Non-blocking: a second click fails fast with
# 409 instead of queueing behind the first import.
import_lock = threading.Lock()


class ImportAlreadyRunning(Exception):
    """Another import holds the lock."""


@dataclass
class ScheduleState:
    """What this process's import schedule is doing, for the status page.

    Kept in memory: the schedule lives in one process, so only that process
    can say whether it is running. After a restart it starts empty again.
    """

    interval_minutes: int = 0
    # the scheduler loop is alive in this process
    running: bool = False
    started_at: datetime | None = None
    # when the next scheduled import is due
    next_run_at: datetime | None = None
    # when the last scheduled run finished, whatever it did (it may have
    # skipped: no account connected, or another import was running)
    last_run_at: datetime | None = None
    # another backend holds the schedule's lease, so this one is waiting its
    # turn rather than stopped
    standby: bool = False


schedule_state = ScheduleState()


def run_import(
    db: Session,
    service_factory: Callable[[], OrderImportService] | None = None,
    provider: str = allegro_settings.PROVIDER,
) -> ImportResult:
    """Run one sync and note how it ended, on `provider`'s row (Erli's import
    passes its own; the lock is the same, so imports never overlap).

    Raises ImportAlreadyRunning without waiting if another import is under way;
    any error the import itself raises is noted (when there is an account to
    note it on) and re-raised.
    """
    if not import_lock.acquire(blocking=False):
        raise ImportAlreadyRunning
    factory = service_factory or (lambda: build_allegro_import_service(db))
    try:
        return run_and_record(db, provider, lambda: factory().sync_orders())
    finally:
        import_lock.release()


def _scheduled_run() -> None:
    """One scheduled import, on its own session. Never raises."""
    db = SessionLocal()
    try:
        if not build_allegro_client(db).is_configured:
            # nothing connected yet (or disconnected since): not an error
            return
        result = run_import(db)
        logger.info(
            "Scheduled Allegro import: %d new, %d updated", result.created, result.updated
        )
    except ImportAlreadyRunning:
        logger.info("Scheduled Allegro import skipped: another import is running")
    except IntegrationError as exc:
        logger.warning("Scheduled Allegro import failed: %s", exc)
    except Exception:
        logger.exception("Scheduled Allegro import failed")
    finally:
        db.close()
