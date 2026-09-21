"""Which Allegro application Anvero talks to, and connecting a seller to it.

Two things live here that the Settings page drives:

- the application's own credentials (client id, secret, User-Agent, and which
  environment it is registered in), from a row in `integration_settings` when
  someone entered them in Settings, else from the environment as before;
- connecting a seller account by the OAuth device flow: Allegro gives a link,
  the seller confirms it in their own browser, and this side polls until the
  token arrives. See docs/INTEGRATIONS.md.
"""

import secrets
import threading
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings as env
from app.integrations.allegro.authorization import (
    AllegroDeviceAuthorizer,
    DeviceAuthorization,
)
from app.integrations.allegro.client import AllegroClient
from app.integrations.base import IntegrationNotConfigured
from app.models.order import OrderSource
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.integration_settings_repository import (
    IntegrationSettingsRepository,
)
from app.services.refresh_token_store import DatabaseRefreshTokenStore, _fingerprint

PROVIDER = OrderSource.ALLEGRO.value

ENVIRONMENTS = {
    "production": (
        "https://api.allegro.pl",
        "https://allegro.pl/auth/oauth",
    ),
    "sandbox": (
        "https://api.allegro.pl.allegrosandbox.pl",
        "https://allegro.pl.allegrosandbox.pl/auth/oauth",
    ),
}

# Allegro asks for this much extra patience when it answers slow_down
SLOW_DOWN_STEP_SECONDS = 5


@dataclass(frozen=True)
class AllegroApplication:
    """The application's credentials as they apply right now."""

    client_id: str
    client_secret: str
    user_agent: str
    api_url: str
    auth_url: str
    # a refresh token seeded from the environment; only meaningful while the
    # credentials also come from there, since a token belongs to one application
    seed_refresh_token: str
    environment: str
    # "settings" (entered in Settings) or "environment" (.env)
    source: str

    @property
    def is_complete(self) -> bool:
        return bool(self.client_id and self.client_secret and self.user_agent)


def resolve_application(db: Session) -> AllegroApplication:
    stored = IntegrationSettingsRepository(db).get(PROVIDER)
    if stored is not None:
        api_url, auth_url = ENVIRONMENTS[stored.environment]
        return AllegroApplication(
            client_id=stored.client_id,
            client_secret=stored.client_secret,
            user_agent=stored.user_agent,
            api_url=api_url,
            auth_url=auth_url,
            seed_refresh_token="",
            environment=stored.environment,
            source="settings",
        )
    return AllegroApplication(
        client_id=env.allegro_client_id,
        client_secret=env.allegro_client_secret,
        user_agent=env.allegro_user_agent,
        api_url=env.allegro_api_url,
        auth_url=env.allegro_auth_url,
        seed_refresh_token=env.allegro_refresh_token,
        environment="sandbox" if "allegrosandbox" in env.allegro_api_url else "production",
        source="environment",
    )


def build_client(db: Session) -> AllegroClient:
    """An AllegroClient wired to the application in force and the stored token."""
    app = resolve_application(db)
    token_store = DatabaseRefreshTokenStore(
        IntegrationCredentialRepository(db),
        provider=PROVIDER,
        configured_token=app.seed_refresh_token,
    )
    return AllegroClient(
        client_id=app.client_id,
        client_secret=app.client_secret,
        user_agent=app.user_agent,
        api_url=app.api_url,
        auth_url=app.auth_url,
        token_store=token_store,
    )


def save_application(
    db: Session,
    client_id: str,
    client_secret: str | None,
    user_agent: str,
    environment: str,
) -> None:
    """Store the application's credentials; a blank secret keeps the stored one.

    A token belongs to one application in one environment, so changing the
    client id or the environment disconnects the account: what it was granted
    is worthless to the new application, and using it would only fail. That
    holds whether the previous credentials came from Settings or from `.env`.
    """
    if environment not in ENVIRONMENTS:
        raise ValueError("environment must be 'sandbox' or 'production'")

    previous = resolve_application(db)
    secret = client_secret or (previous.client_secret if previous.source == "settings" else "")
    if not secret:
        raise ValueError("a client secret is required the first time")

    changed_application = previous.is_complete and (
        previous.client_id != client_id or previous.environment != environment
    )

    IntegrationSettingsRepository(db).save(PROVIDER, client_id, secret, user_agent, environment)
    if changed_application:
        IntegrationCredentialRepository(db).disconnect(PROVIDER)


@dataclass(frozen=True)
class ConnectFlow:
    flow_id: str
    authorization: DeviceAuthorization
    authorizer: AllegroDeviceAuthorizer
    interval: int
    next_poll_at: float
    expires_at: float


class ConnectFlows:
    """The one sign-in in progress, held in memory.

    There is one seller account, so at most one flow matters: starting another
    replaces it. Kept in the process rather than the database because it lives
    for minutes and holds a device code that is worthless afterwards; the
    price is that a restart mid-flow means starting again, and that this
    assumes a single server process, as everything else here does (see the
    import lock in the integrations endpoint).
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._flow: ConnectFlow | None = None

    def start(self, db: Session) -> tuple[ConnectFlow, str]:
        app = resolve_application(db)
        if not app.is_complete:
            raise IntegrationNotConfigured(
                "enter the client id, client secret and User-Agent first"
            )
        authorizer = AllegroDeviceAuthorizer(
            client_id=app.client_id,
            client_secret=app.client_secret,
            auth_url=app.auth_url,
            user_agent=app.user_agent,
        )
        authorization = authorizer.start()
        now = self._clock()
        flow = ConnectFlow(
            flow_id=secrets.token_urlsafe(16),
            authorization=authorization,
            authorizer=authorizer,
            interval=authorization.interval,
            next_poll_at=now + authorization.interval,
            expires_at=now + authorization.expires_in,
        )
        with self._lock:
            self._flow = flow
        return flow, authorization.verification_uri_complete

    def poll(self, db: Session, flow_id: str) -> str | None:
        """Check once; return the connected account's login when done.

        Returns None while the seller has not confirmed yet. Asking sooner
        than Allegro's polling interval does not reach Allegro at all: the
        page polls on its own timer, and a second tab or a retry storm must
        not turn into a request storm against a third party. When the account
        is connected but its login could not be read, the result is "".
        """
        with self._lock:
            flow = self._flow
        if flow is None or flow.flow_id != flow_id:
            raise LookupError("no such sign-in in progress; start it again")

        now = self._clock()
        if now > flow.expires_at:
            self.cancel()
            raise TimeoutError("the sign-in was not confirmed in time; start it again")
        if now < flow.next_poll_at:
            return None

        try:
            result = flow.authorizer.poll_once(flow.authorization)
        except Exception:
            # declined, expired or refused: the device code is spent either way
            self.cancel()
            raise

        if result.refresh_token is None:
            interval = flow.interval + (SLOW_DOWN_STEP_SECONDS if result.slow_down else 0)
            with self._lock:
                if self._flow is flow:
                    self._flow = ConnectFlow(
                        flow_id=flow.flow_id,
                        authorization=flow.authorization,
                        authorizer=flow.authorizer,
                        interval=interval,
                        next_poll_at=self._clock() + interval,
                        expires_at=flow.expires_at,
                    )
            return None

        self.cancel()
        return _store_connection(db, result.refresh_token)

    def cancel(self) -> None:
        with self._lock:
            self._flow = None


def _store_connection(db: Session, refresh_token: str) -> str:
    """Save a newly granted token and label it with the seller's login."""
    app = resolve_application(db)
    credentials = IntegrationCredentialRepository(db)
    credentials.connect(
        PROVIDER,
        refresh_token,
        _fingerprint(app.seed_refresh_token),
        account_login=None,
    )
    # reading /me spends the token once and stores its replacement, which is
    # why it is done after the token is safely saved rather than before
    login = build_client(db).fetch_account_login()
    credentials.set_account_login(PROVIDER, login)
    return login or ""


flows = ConnectFlows()
