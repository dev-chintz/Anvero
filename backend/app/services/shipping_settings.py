"""The sender and the usual parcel, for buying labels.

Kept in `app_settings` as JSON under one key each, so they are the owner's
choice made in the interface, like safe mode, and need no table of their own.
"""

import json

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.marketplace_write import AppSetting
from app.schemas.shipping import PackageSize, ShippingSender, ShippingSettings

SENDER_KEY = "shipping_sender"
PACKAGE_KEY = "shipping_default_package"


def _read(db: Session, key: str, model):
    setting = db.get(AppSetting, key)
    if setting is None:
        return None
    try:
        return model.model_validate(json.loads(setting.value))
    except (ValueError, ValidationError):
        # a value the current code no longer reads is as good as none
        return None


def _write(db: Session, key: str, value, user_id: int | None) -> None:
    setting = db.get(AppSetting, key)
    if value is None:
        if setting is not None:
            db.delete(setting)
        return
    if setting is None:
        setting = AppSetting(key=key)
        db.add(setting)
    setting.value = value.model_dump_json()
    setting.updated_by_user_id = user_id


def get_shipping_settings(db: Session) -> ShippingSettings:
    return ShippingSettings(
        sender=_read(db, SENDER_KEY, ShippingSender),
        default_package=_read(db, PACKAGE_KEY, PackageSize),
    )


def save_shipping_settings(
    db: Session, settings: ShippingSettings, user_id: int | None
) -> ShippingSettings:
    _write(db, SENDER_KEY, settings.sender, user_id)
    _write(db, PACKAGE_KEY, settings.default_package, user_id)
    db.commit()
    return get_shipping_settings(db)
