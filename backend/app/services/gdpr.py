"""The data controller's details, kept for the GDPR page and the notice to buyers (docs/GDPR.md).

One row of `app_settings` holds them as a JSON object: the application has one owner, who is the
controller, and what the notice needs of them is a handful of lines of text.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.models.marketplace_write import AppSetting
from app.schemas.gdpr import (
    ControllerRead,
    ControllerWrite,
    GdprOverview,
    RetentionRead,
)
from app.services import retention

logger = logging.getLogger(__name__)

CONTROLLER_KEY = "gdpr_controller"


def get_controller(db: Session) -> ControllerRead:
    row = db.get(AppSetting, CONTROLLER_KEY)
    if row is None:
        return ControllerRead()
    try:
        details = ControllerWrite.model_validate(json.loads(row.value))
    except (ValueError, TypeError):
        logger.warning("The saved controller details are not readable; shown as none")
        return ControllerRead()
    return ControllerRead(**details.model_dump(), updated_at=row.updated_at)


def set_controller(db: Session, details: ControllerWrite, user_id: int | None) -> ControllerRead:
    value = details.model_dump_json()
    row = db.get(AppSetting, CONTROLLER_KEY)
    if row is None:
        row = AppSetting(key=CONTROLLER_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    row.updated_by_user_id = user_id
    db.commit()
    db.refresh(row)
    logger.info("Controller details saved by user %s", user_id)
    return get_controller(db)


def overview(db: Session) -> GdprOverview:
    return GdprOverview(
        controller=get_controller(db),
        retention=RetentionRead(
            orders_years=retention.ORDER_RETENTION_YEARS, contacts_years=retention.CONTACT_RETENTION_YEARS
        ),
    )
