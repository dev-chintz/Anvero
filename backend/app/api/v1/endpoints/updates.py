"""Updates from Settings, for an administrator (`API.md`, "Updates")."""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.permissions import require_admin
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.updates import UpdateStatus
from app.services import updates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/updates", tags=["Updates"], dependencies=[Depends(require_admin)])


def _status(state: updates.UpdateState) -> UpdateStatus:
    return UpdateStatus(
        current=updates.short(state.current),
        latest=updates.short(state.latest),
        available=state.available,
        behind=state.behind,
        changes=[asdict(change) for change in state.changes],
        checked_at=state.checked_at,
        error=state.error,
        can_update=updates.updater_configured() and state.current is not None,
        updater=updates.updater_status(),
    )


@router.get("", response_model=UpdateStatus)
def get_updates(refresh: bool = False):
    """What the last check found; with `refresh=true`, check GitHub now."""
    state = updates.check_now() if refresh else updates.current_state()
    return _status(state)


@router.post("", response_model=UpdateStatus, status_code=status.HTTP_202_ACCEPTED)
def start_update(current_user: User = Depends(get_current_user)):
    """Ask the updater to install the newest published version. The backend
    goes away while its container is recreated; `GET /health` names the commit
    running once it is back."""
    state = updates.current_state()
    if not state.available:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No newer version is published")
    try:
        updates.start_update()
    except updates.UpdateError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    logger.info("Update to %s started by user %s", updates.short(state.latest), current_user.id)
    return _status(state)
