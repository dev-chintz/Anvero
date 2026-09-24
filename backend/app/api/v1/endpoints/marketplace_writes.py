import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.marketplace_write import (
    MarketplaceWriteRead,
    SafeModeRead,
    SafeModeUpdate,
)
from app.services.marketplace_writes import (
    list_writes,
    safe_mode_on,
    safe_mode_setting,
    set_safe_mode,
)

router = APIRouter(tags=["Safe mode"], dependencies=[Depends(get_current_user)])


def _safe_mode(db: Session) -> SafeModeRead:
    setting = safe_mode_setting(db)
    return SafeModeRead(
        enabled=safe_mode_on(db),
        changed_at=setting.updated_at if setting else None,
        changed_by=setting.updated_by.email if setting and setting.updated_by else None,
    )


@router.get("/settings/safe-mode", response_model=SafeModeRead)
def get_safe_mode(db: Session = Depends(get_db)):
    return _safe_mode(db)


@router.put("/settings/safe-mode", response_model=SafeModeRead)
def put_safe_mode(
    payload: SafeModeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    set_safe_mode(db, payload.enabled, current_user.id)
    return _safe_mode(db)


@router.get("/marketplace-writes", response_model=list[MarketplaceWriteRead])
def get_marketplace_writes(
    order_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_writes(db, order_id=order_id, limit=limit)
