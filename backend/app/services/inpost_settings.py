"""Which InPost token, organization and environment Anvero uses.

Entered in Settings and kept in `app_settings` (no table of its own, like safe mode
and Erli's key). The token is plain text, as Allegro's client secret and Erli's
key are, and is never sent back to the browser: Settings only learns its last four
characters. InPost's tokens do not rotate, so entering it once serves every machine
on the shared database.

The sandbox is a separate service with its own tokens: nothing made there is sent or
billed, which is where a first try belongs.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.integrations.inpost.client import ENVIRONMENTS, TEMPLATES, InpostClient
from app.models.marketplace_write import AppSetting

TOKEN_KEY = "inpost_api_token"
ORGANIZATION_KEY = "inpost_organization_id"
ENVIRONMENT_KEY = "inpost_environment"
TEMPLATE_KEY = "inpost_default_template"

DEFAULT_ENVIRONMENT = "sandbox"
DEFAULT_TEMPLATE = "small"

# how much of the token is shown, to tell one token from another
HINT_LENGTH = 4


@dataclass(frozen=True)
class InpostSettings:
    token: str
    organization_id: str
    environment: str
    default_template: str

    @property
    def configured(self) -> bool:
        return bool(self.token and self.organization_id)

    @property
    def token_hint(self) -> str | None:
        return f"…{self.token[-HINT_LENGTH:]}" if self.token else None


def _get(db: Session, key: str) -> str:
    setting = db.get(AppSetting, key)
    return setting.value if setting is not None and setting.value else ""


def _set(db: Session, key: str, value: str, user_id: int | None) -> None:
    setting = db.get(AppSetting, key)
    if setting is None:
        setting = AppSetting(key=key)
        db.add(setting)
    setting.value = value
    setting.updated_by_user_id = user_id


def get_settings(db: Session) -> InpostSettings:
    environment = _get(db, ENVIRONMENT_KEY)
    template = _get(db, TEMPLATE_KEY)
    return InpostSettings(
        token=_get(db, TOKEN_KEY),
        organization_id=_get(db, ORGANIZATION_KEY),
        environment=environment if environment in ENVIRONMENTS else DEFAULT_ENVIRONMENT,
        default_template=template if template in TEMPLATES else DEFAULT_TEMPLATE,
    )


def build_inpost_client(db: Session) -> InpostClient:
    settings = get_settings(db)
    return InpostClient(
        token=settings.token,
        organization_id=settings.organization_id,
        environment=settings.environment,
    )


def check(token: str, organization_id: str, environment: str) -> dict:
    """Ask InPost for the organization, to learn that the token and its id go together.

    A read, so safe mode does not apply. Raises IntegrationAuthError when InPost
    refuses the token and IntegrationUnavailable when it cannot be asked.
    """
    return InpostClient(token, organization_id, environment).get_organization()


def save_settings(
    db: Session,
    token: str,
    organization_id: str,
    environment: str,
    default_template: str,
    user_id: int | None,
) -> None:
    _set(db, TOKEN_KEY, token, user_id)
    _set(db, ORGANIZATION_KEY, organization_id, user_id)
    _set(db, ENVIRONMENT_KEY, environment, user_id)
    _set(db, TEMPLATE_KEY, default_template, user_id)
    db.commit()


def save_template(db: Session, default_template: str, user_id: int | None) -> None:
    """Change only the size offered by default: no token is asked for."""
    _set(db, TEMPLATE_KEY, default_template, user_id)
    db.commit()


def clear_settings(db: Session) -> None:
    """Forget the token and the organization; the environment and size stay."""
    for key in (TOKEN_KEY, ORGANIZATION_KEY):
        setting = db.get(AppSetting, key)
        if setting is not None:
            db.delete(setting)
    db.commit()
