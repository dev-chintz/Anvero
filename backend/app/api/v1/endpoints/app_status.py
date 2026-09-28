from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_permission
from app.db.session import get_db
from app.models.user_permission import PermissionArea
from app.schemas.app_status import AppStatus
from app.services.app_status import app_status

router = APIRouter(tags=["Status"], dependencies=[require_permission(PermissionArea.INTEGRATIONS)])


@router.get("/status", response_model=AppStatus)
def get_app_status(db: Session = Depends(get_db)):
    """Connections, the last imports and the schedule, for the status page."""
    return app_status(db)
