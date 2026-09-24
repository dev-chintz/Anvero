"""Noting how an import ended, whichever marketplace and whoever started it.

The button, the schedule and both import scripts go through `run_and_record`,
so the status page and Settings see every import, not only some of them.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.integrations.base import IntegrationNotConfigured
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.services.order_import_service import ImportResult

# a failure note is shown to the operator, so it stays short
MAX_ERROR_LENGTH = 500


def run_and_record(db: Session, provider: str, run: Callable[[], ImportResult]) -> ImportResult:
    """Run one import and note on the provider's row how it ended.

    "Not configured" is not noted: nothing ran. Any other error is noted (when
    there is a row to note it on) and re-raised.
    """
    try:
        result = run()
    except IntegrationNotConfigured:
        raise
    except Exception as exc:
        # a failed statement leaves the session unusable until rolled back
        db.rollback()
        IntegrationCredentialRepository(db).record_import(
            provider,
            datetime.now(UTC),
            error=(str(exc) or type(exc).__name__)[:MAX_ERROR_LENGTH],
        )
        raise
    IntegrationCredentialRepository(db).record_import(
        provider,
        datetime.now(UTC),
        created=result.created,
        updated=result.updated,
    )
    return result
