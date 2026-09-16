"""HTTP client for the Allegro REST API.

Reading a seller's orders requires a token issued in a user context, so this
client refreshes a long-lived refresh token obtained once by hand rather than
using the client-credentials flow, which only reaches public data.
"""

import logging
import time
from typing import Any

import httpx2

from app.core.config import settings
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)

logger = logging.getLogger(__name__)

# the API refuses requests that do not pin a version
ACCEPT_HEADER = "application/vnd.allegro.public.v1+json"

# refresh slightly early so a token cannot expire mid-request
TOKEN_EXPIRY_MARGIN_SECONDS = 60

REQUEST_TIMEOUT_SECONDS = 30.0

MAX_PAGE_SIZE = 100


class AllegroClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        api_url: str | None = None,
        auth_url: str | None = None,
        http_client: httpx2.Client | None = None,
    ):
        self._client_id = client_id if client_id is not None else settings.allegro_client_id
        self._client_secret = (
            client_secret if client_secret is not None else settings.allegro_client_secret
        )
        self._refresh_token = (
            refresh_token if refresh_token is not None else settings.allegro_refresh_token
        )
        self._api_url = (api_url or settings.allegro_api_url).rstrip("/")
        self._auth_url = (auth_url or settings.allegro_auth_url).rstrip("/")
        self._http = http_client or httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS)

        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret and self._refresh_token)

    def _require_configuration(self) -> None:
        if not self.is_configured:
            raise IntegrationNotConfigured(
                "Allegro credentials are missing; set ALLEGRO_CLIENT_ID, "
                "ALLEGRO_CLIENT_SECRET and ALLEGRO_REFRESH_TOKEN"
            )

    def _access_token_value(self) -> str:
        if self._access_token and time.monotonic() < self._expires_at:
            return self._access_token

        self._require_configuration()
        try:
            response = self._http.post(
                f"{self._auth_url}/token",
                auth=httpx2.BasicAuth(self._client_id, self._client_secret),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
            )
        except httpx2.RequestError as exc:
            raise IntegrationUnavailable(f"Allegro token endpoint unreachable: {exc}") from exc

        if response.status_code in (400, 401):
            # the refresh token expires; recovering needs a human to authorize
            # the application again, so say that rather than just "401"
            raise IntegrationAuthError(
                "Allegro rejected the refresh token; the application needs "
                "authorizing again"
            )
        if response.status_code >= 400:
            raise IntegrationUnavailable(
                f"Allegro token endpoint returned {response.status_code}"
            )

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise IntegrationAuthError("Allegro returned no access_token")

        self._access_token = token
        self._expires_at = (
            time.monotonic()
            + float(payload.get("expires_in", 0))
            - TOKEN_EXPIRY_MARGIN_SECONDS
        )
        return token

    def fetch_checkout_forms(
        self, limit: int = MAX_PAGE_SIZE, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return one page of raw checkout forms.

        The payload stays raw on purpose: translating it is the mapper's job,
        so nothing outside this package depends on Allegro's field names.
        """
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")

        token = self._access_token_value()
        try:
            response = self._http.get(
                f"{self._api_url}/order/checkout-forms",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": ACCEPT_HEADER,
                },
                params={"limit": limit, "offset": offset},
            )
        except httpx2.RequestError as exc:
            raise IntegrationUnavailable(f"Allegro API unreachable: {exc}") from exc

        if response.status_code == 401:
            # drop the cached token so the next call re-authenticates
            self._access_token = None
            raise IntegrationAuthError("Allegro rejected the access token")
        if response.status_code == 403:
            raise IntegrationAuthError(
                "Allegro denied access to orders; the application likely lacks "
                "the allegro:api:orders:read scope"
            )
        if response.status_code >= 400:
            raise IntegrationUnavailable(
                f"Allegro API returned {response.status_code} for checkout-forms"
            )

        return response.json().get("checkoutForms", [])
