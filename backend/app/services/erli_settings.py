"""Which Erli API key Anvero uses.

The key is entered in Settings and kept in `app_settings` (no table of its own,
like safe mode and the shipping settings); when none was entered, `ERLI_API_KEY`
from the environment applies, as before. It is stored as plain text, the same
as Allegro's client secret, and is never sent back to the browser: Settings
only learns its source and its last four characters.

Erli's key does not rotate, so unlike Allegro's token nothing changes it
behind the owner's back; entering it once serves every machine on the shared
database.
"""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import settings as env
from app.integrations.erli.client import ErliClient
from app.models.marketplace_write import AppSetting

KEY = "erli_api_key"

# how much of the key is shown, to tell one key from another
HINT_LENGTH = 4


@dataclass(frozen=True)
class ErliKey:
    value: str
    source: Literal["settings", "environment", "none"]

    @property
    def hint(self) -> str | None:
        return f"…{self.value[-HINT_LENGTH:]}" if self.value else None


def resolve_key(db: Session) -> ErliKey:
    setting = db.get(AppSetting, KEY)
    if setting is not None and setting.value:
        return ErliKey(setting.value, "settings")
    if env.erli_api_key:
        return ErliKey(env.erli_api_key, "environment")
    return ErliKey("", "none")


def build_erli_client(db: Session) -> ErliClient:
    return ErliClient(api_key=resolve_key(db).value)


def save_key(db: Session, api_key: str, user_id: int | None) -> None:
    setting = db.get(AppSetting, KEY)
    if setting is None:
        setting = AppSetting(key=KEY)
        db.add(setting)
    setting.value = api_key
    setting.updated_by_user_id = user_id
    db.commit()


def clear_key(db: Session) -> None:
    """Forget the key entered in Settings; the environment's, if any, applies."""
    setting = db.get(AppSetting, KEY)
    if setting is not None:
        db.delete(setting)
        db.commit()


def check_key(api_key: str) -> None:
    """Ask Erli for one order, to learn whether it accepts the key.

    A read, so safe mode does not apply. Raises IntegrationAuthError when Erli
    refuses the key and IntegrationUnavailable when it cannot be asked.
    """
    ErliClient(api_key=api_key).search_orders(limit=1)
