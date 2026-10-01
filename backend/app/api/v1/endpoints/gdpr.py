"""The GDPR page: who the data controller is, and how long what is held is kept (docs/GDPR.md)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_admin
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.gdpr import ControllerRead, ControllerWrite, GdprOverview
from app.services import gdpr

# Anyone logged in may read it: the notice to buyers and the register are for the whole team to
# find. Only an administrator changes who the controller is.
router = APIRouter(prefix="/gdpr", tags=["GDPR"], dependencies=[Depends(get_current_user)])


@router.get("/overview", response_model=GdprOverview)
def overview(db: Session = Depends(get_db)):
    return gdpr.overview(db)


@router.put("/controller", response_model=ControllerRead)
def put_controller(
    body: ControllerWrite, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    """Save who the data controller is. Fields left blank are cleared."""
    return gdpr.set_controller(db, body, admin.id)
