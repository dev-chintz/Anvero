"""Updates from Settings, for an administrator (`API.md`, "Updates")."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import require_admin
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.updates import UpdateHistoryEntry, UpdateStatus
from app.services import update_history, updates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/updates", tags=["Updates"], dependencies=[Depends(require_admin)])


def _status(db: Session, state: updates.UpdateState) -> UpdateStatus:
    updater = updates.updater_status()
    update_history.resolve_pending(db, state.current, updater)
    return UpdateStatus(
        current=updates.short(state.current),
        latest=updates.short(state.latest),
        available=state.available,
        behind=state.behind,
        changes=[asdict(change) for change in state.changes],
        checked_at=state.checked_at,
        error=state.error,
        can_update=updates.updater_configured() and state.current is not None,
        updater=updater,
        history=[
            UpdateHistoryEntry(
                id=row.id,
                from_commit=updates.short(row.from_commit),
                to_commit=updates.short(row.to_commit),
                started_at=row.started_at,
                finished_at=row.finished_at,
                result=row.result,
                via=row.via,
                started_by=row.started_by_email,
                detail=row.detail,
            )
            for row in update_history.history(db)
        ],
    )


@router.get("", response_model=UpdateStatus)
def get_updates(refresh: bool = False, db: Session = Depends(get_db)):
    """What the last check found; with `refresh=true`, check GitHub now."""
    state = updates.check_now() if refresh else updates.current_state()
    return _status(db, state)


@router.post("", response_model=UpdateStatus, status_code=status.HTTP_202_ACCEPTED)
def start_update(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ask the updater to install the newest published version. The backend
    goes away while its container is recreated; `GET /health` names the commit
    running once it is back, and the new backend closes the history's entry."""
    state = updates.current_state()
    if not state.available:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No newer version is published")
    try:
        updates.start_update()
    except updates.UpdateError as exc:
        update_history.record_refused(db, state.current, state.latest, current_user.id, str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    update_history.record_start(db, state.current, state.latest, current_user.id)
    logger.info("Update to %s started by user %s", updates.short(state.latest), current_user.id)
    return _status(db, state)
