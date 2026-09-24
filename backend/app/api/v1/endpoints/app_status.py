from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.app_status import AppStatus
from app.services.app_status import app_status

router = APIRouter(tags=["Status"], dependencies=[Depends(get_current_user)])


@router.get("/status", response_model=AppStatus)
def get_app_status(db: Session = Depends(get_db)):
    """Connections, the last imports and the schedule, for the status page."""
    return app_status(db)
