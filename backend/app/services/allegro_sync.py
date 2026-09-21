"""Running an Allegro import, by hand or on a schedule, one at a time.

Both the button and the schedule go through `run_import`, so they share one
lock and both leave a note of how they ended for Settings and the orders page
to show.
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.services import allegro_settings
from app.services.allegro_import import (
    build_allegro_client,
    build_allegro_import_service,
)
from app.services.order_import_service import ImportResult, OrderImportService

logger = logging.getLogger(__name__)

# Allegro rotates the refresh token on every use, so two imports running at
# once would both refresh it and the second refresh invalidates the token the
# first request is still using. Non-blocking: a second click fails fast with
# 409 instead of queueing behind the first import.
import_lock = threading.Lock()

# a failure note is shown to the operator, so it stays short
_MAX_ERROR_LENGTH = 500


class ImportAlreadyRunning(Exception):
    """Another import holds the lock."""


def run_import(
    db: Session,
    service_factory: Callable[[], OrderImportService] | None = None,
) -> ImportResult:
    """Run one sync and note how it ended.

    Raises ImportAlreadyRunning without waiting if another import is under way;
    any error the import itself raises is noted (when there is an account to
    note it on) and re-raised.
    """
    if not import_lock.acquire(blocking=False):
        raise ImportAlreadyRunning
    try:
        try:
            service = (service_factory or (lambda: build_allegro_import_service(db)))()
            result = service.sync_orders()
        except IntegrationNotConfigured:
            raise
        except Exception as exc:
            # a failed statement leaves the session unusable until rolled back
            db.rollback()
            IntegrationCredentialRepository(db).record_import(
                allegro_settings.PROVIDER,
                datetime.now(UTC),
                error=(str(exc) or type(exc).__name__)[:_MAX_ERROR_LENGTH],
            )
            raise
        IntegrationCredentialRepository(db).record_import(
            allegro_settings.PROVIDER,
            datetime.now(UTC),
            created=result.created,
            updated=result.updated,
        )
        return result
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


async def scheduler(interval_minutes: int | None = None) -> None:
    """Import every `interval` minutes until cancelled; the first run is one
    interval after start, so restarting the backend does not trigger one.

    The import is blocking (HTTP and database), so it runs in a worker thread.
    """
    minutes = settings.allegro_import_interval_minutes if interval_minutes is None else interval_minutes
    if minutes <= 0:
        return
    logger.info("Allegro imports scheduled every %d minutes", minutes)
    while True:
        await asyncio.sleep(minutes * 60)
        await asyncio.to_thread(_scheduled_run)
