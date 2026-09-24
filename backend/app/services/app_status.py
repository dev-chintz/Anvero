"""The application status page: is each marketplace connected, did the last
import work, and is the schedule running.

Everything here is read from what Anvero already holds; nothing is asked of a
marketplace. Checking Allegro live would mean refreshing its token, which
rotates it and competes with imports for the lock, so the token's age and the
last import's outcome stand in for a live check (DECISIONS.md).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.erli.client import ErliClient
from app.models.integration import IntegrationCredential
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.schemas.app_status import (
    AllegroHealth,
    AppStatus,
    ErliHealth,
    HealthState,
    LastImport,
    ScheduleStatus,
)
from app.services import allegro_settings, erli_import
from app.services.allegro_sync import ScheduleState, schedule_state
from app.services.marketplace_writes import safe_mode_on

# Allegro's refresh token lives three months from its issue; every import
# issues a new one, so it runs out only when nothing imports for that long
ALLEGRO_REFRESH_TOKEN_LIFETIME = timedelta(days=90)
# warn this long before the token runs out
TOKEN_WARNING = timedelta(days=14)
# a scheduled import later than this many intervals is overdue
OVERDUE_INTERVALS = 3

# problems that stop a marketplace working; the rest are warnings
_ERRORS = {"token_expired", "last_import_failed"}


def _utc(value: datetime | None) -> datetime | None:
    # SQLite returns stored timestamps without a zone; they are UTC
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _state(problems: list[str]) -> HealthState:
    if any(p in _ERRORS for p in problems):
        return "error"
    return "warning" if problems else "ok"


def _last_import(credential: IntegrationCredential | None) -> LastImport:
    if credential is None:
        return LastImport()
    return LastImport(
        at=credential.last_import_at,
        created=credential.last_import_created,
        updated=credential.last_import_updated,
        error=credential.last_import_error,
    )


def _schedule(state: ScheduleState) -> ScheduleStatus:
    return ScheduleStatus(
        interval_minutes=state.interval_minutes or settings.allegro_import_interval_minutes,
        running=state.running,
        started_at=state.started_at,
        next_run_at=state.next_run_at,
        last_run_at=state.last_run_at,
    )


def allegro_health(db: Session, now: datetime, state: ScheduleState) -> AllegroHealth:
    application = allegro_settings.resolve_application(db)
    credential = IntegrationCredentialRepository(db).get(allegro_settings.PROVIDER)
    connected = credential is not None or bool(application.seed_refresh_token)
    schedule = _schedule(state)
    last_import = _last_import(credential)

    issued = _utc(credential.token_issued_at) if credential else None
    expires = issued + ALLEGRO_REFRESH_TOKEN_LIFETIME if issued else None

    problems: list[str] = []
    if not application.is_complete and not connected:
        return AllegroHealth(
            state="off",
            problems=[],
            application_complete=False,
            connected=False,
            environment=application.environment,
            account_login=None,
            token_issued_at=None,
            token_expires_at=None,
            last_import=last_import,
            schedule=schedule,
        )
    if not application.is_complete:
        problems.append("application_incomplete")
    if not connected:
        problems.append("not_connected")
    if expires is not None:
        if expires <= now:
            problems.append("token_expired")
        elif expires - now <= TOKEN_WARNING:
            problems.append("token_expiring")
    if last_import.error:
        problems.append("last_import_failed")
    if connected and last_import.at is None:
        problems.append("never_imported")
    if schedule.interval_minutes and not schedule.running:
        # configured to import by itself, but the loop is not alive here
        problems.append("schedule_stopped")
    if schedule.running and connected:
        # measured from the later of the last import and the schedule's start,
        # so a backend just restarted is not reported overdue
        last_at = _utc(last_import.at)
        since = max(t for t in (last_at, _utc(schedule.started_at)) if t is not None)
        if now - since > timedelta(minutes=schedule.interval_minutes * OVERDUE_INTERVALS):
            problems.append("import_overdue")

    return AllegroHealth(
        state=_state(problems),
        problems=problems,
        application_complete=application.is_complete,
        connected=connected,
        environment=application.environment,
        account_login=credential.account_login if credential else None,
        token_issued_at=issued,
        token_expires_at=expires,
        last_import=last_import,
        schedule=schedule,
    )


def erli_health(db: Session) -> ErliHealth:
    configured = ErliClient().is_configured
    credential = IntegrationCredentialRepository(db).get(erli_import.PROVIDER)
    last_import = _last_import(credential)
    problems: list[str] = []
    if configured and last_import.error:
        problems.append("last_import_failed")
    if configured and last_import.at is None:
        problems.append("never_imported")
    return ErliHealth(
        state=_state(problems) if configured else "off",
        problems=problems,
        configured=configured,
        last_import=last_import,
        schedule=None,
    )


def app_status(db: Session, now: datetime | None = None) -> AppStatus:
    now = now or datetime.now(UTC)
    return AppStatus(
        checked_at=now,
        version=settings.app_version,
        safe_mode=safe_mode_on(db),
        allegro=allegro_health(db, now, schedule_state),
        erli=erli_health(db),
    )
