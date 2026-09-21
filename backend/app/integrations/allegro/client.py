"""HTTP client for the Allegro REST API.

Reading a seller's orders requires a token issued in a user context, so this
client works from a refresh token obtained once by hand rather than the
client-credentials flow, which only reaches public data. Allegro rotates that
token on every use, so it is read from and written back to a RefreshTokenStore.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx2

from app.core.config import settings
from app.integrations.base import (
    InMemoryRefreshTokenStore,
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
    RefreshTokenStore,
)

logger = logging.getLogger(__name__)

# the API refuses requests that do not pin a version
ACCEPT_HEADER = "application/vnd.allegro.public.v1+json"

# refresh slightly early so a token cannot expire mid-request
TOKEN_EXPIRY_MARGIN_SECONDS = 60

REQUEST_TIMEOUT_SECONDS = 30.0

MAX_PAGE_SIZE = 100

# Allegro's limit for one tracking request
MAX_TRACKING_WAYBILLS = 20


def _timestamp(value: datetime) -> str:
    """Allegro's date-time format: UTC, millisecond precision, a trailing Z."""
    utc = value.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def _json_object(response: httpx2.Response, what: str) -> dict[str, Any]:
    """Decode a response that must be a JSON object.

    A proxy, captive portal or maintenance page can answer 200 with HTML.
    Letting that raise JSONDecodeError would bypass every IntegrationError
    handler and end the import in a raw traceback.
    """
    try:
        payload = response.json()
    except ValueError as exc:
        raise IntegrationUnavailable(f"{what} did not return JSON") from exc
    if not isinstance(payload, dict):
        raise IntegrationUnavailable(f"{what} returned JSON that is not an object")
    return payload


class AllegroClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        api_url: str | None = None,
        auth_url: str | None = None,
        user_agent: str | None = None,
        http_client: httpx2.Client | None = None,
        token_store: RefreshTokenStore | None = None,
    ):
        self._client_id = client_id if client_id is not None else settings.allegro_client_id
        self._client_secret = (
            client_secret if client_secret is not None else settings.allegro_client_secret
        )
        self._token_store = token_store or InMemoryRefreshTokenStore(
            refresh_token if refresh_token is not None else settings.allegro_refresh_token
        )
        self._api_url = (api_url or settings.allegro_api_url).rstrip("/")
        self._auth_url = (auth_url or settings.allegro_auth_url).rstrip("/")
        self._user_agent = (
            user_agent if user_agent is not None else settings.allegro_user_agent
        )
        self._http = http_client or httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS)

        self._access_token: str | None = None
        self._expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        # Allegro blocks the application's key over calls without its own
        # User-Agent, so none may go out until one is set
        return bool(
            self._client_id
            and self._client_secret
            and self._user_agent
            and self._token_store.current()
        )

    def _require_configuration(self) -> None:
        if not self.is_configured:
            raise IntegrationNotConfigured(
                "Allegro credentials are missing; set ALLEGRO_CLIENT_ID, "
                "ALLEGRO_CLIENT_SECRET, ALLEGRO_USER_AGENT and ALLEGRO_REFRESH_TOKEN"
            )

    def _access_token_value(self) -> str:
        if self._access_token and time.monotonic() < self._expires_at:
            return self._access_token

        self._require_configuration()
        refresh_token = self._token_store.current()
        try:
            response = self._http.post(
                f"{self._auth_url}/token",
                auth=httpx2.BasicAuth(self._client_id, self._client_secret),
                headers={"User-Agent": self._user_agent},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
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

        payload = _json_object(response, "Allegro token endpoint")
        token = payload.get("access_token")
        if not token:
            raise IntegrationAuthError("Allegro returned no access_token")

        # the token just used stops working about a minute from now; record
        # its replacement before anything else can fail, or the next run has
        # nothing valid left to start from
        rotated = payload.get("refresh_token")
        if rotated and rotated != refresh_token:
            try:
                self._token_store.save(rotated)
            except Exception as exc:
                raise IntegrationError(
                    "Allegro issued a new refresh token that could not be stored; "
                    "the previous one is now invalid, so the application needs "
                    "authorizing again"
                ) from exc

        self._access_token = token
        self._expires_at = (
            time.monotonic()
            + float(payload.get("expires_in", 0))
            - TOKEN_EXPIRY_MARGIN_SECONDS
        )
        return token

    def fetch_checkout_forms(
        self,
        limit: int = MAX_PAGE_SIZE,
        offset: int = 0,
        bought_since: datetime | None = None,
        updated_since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return one page of raw checkout forms.

        `bought_since` keeps orders with a line item bought at or after that
        time; `updated_since` keeps orders changed at or after it, which also
        covers new ones. No sort is requested, so Allegro's default applies
        (newest purchase first): a purchase time never changes, so paging by
        offset stays stable while orders are updated mid-run, and a new order
        can only push others onto the next page, repeating one, never
        skipping one.

        The payload stays raw on purpose: translating it is the mapper's job,
        so nothing outside this package depends on Allegro's field names.
        """
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if bought_since is not None:
            params["lineItems.boughtAt.gte"] = _timestamp(bought_since)
        if updated_since is not None:
            params["updatedAt.gte"] = _timestamp(updated_since)

        token = self._access_token_value()
        try:
            response = self._http.get(
                f"{self._api_url}/order/checkout-forms",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": ACCEPT_HEADER,
                    "User-Agent": self._user_agent,
                },
                params=params,
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

        forms = _json_object(response, "Allegro checkout-forms").get("checkoutForms", [])
        if not isinstance(forms, list):
            raise IntegrationUnavailable("Allegro checkout-forms is not a list")
        return forms

    def _get_object(
        self, path: str, what: str, params: list[tuple[str, str]] | None = None
    ) -> dict[str, Any]:
        """GET one Allegro resource and return its JSON object.

        Raises the IntegrationError subclass that says what went wrong, so a
        caller can tell "not allowed" (the application lacks a scope: no point
        asking again) from "unavailable" (this one failed).
        """
        token = self._access_token_value()
        try:
            response = self._http.get(
                f"{self._api_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": ACCEPT_HEADER,
                    "User-Agent": self._user_agent,
                },
                params=params,
            )
        except httpx2.RequestError as exc:
            raise IntegrationUnavailable(f"Allegro API unreachable: {exc}") from exc

        if response.status_code == 401:
            self._access_token = None
            raise IntegrationAuthError("Allegro rejected the access token")
        if response.status_code == 403:
            raise IntegrationAuthError(f"Allegro denied access to {what}")
        if response.status_code >= 400:
            raise IntegrationUnavailable(f"Allegro API returned {response.status_code} for {what}")
        return _json_object(response, f"Allegro {what}")

    def fetch_shipments(self, checkout_form_id: str) -> list[dict[str, Any]]:
        """Return the parcels registered for an order (carrier and waybill).

        `GET /order/checkout-forms/{id}/shipments`. The checkout-form itself
        carries no tracking numbers, hence this second call per order.
        """
        payload = self._get_object(
            f"/order/checkout-forms/{checkout_form_id}/shipments", "shipments"
        )
        shipments = payload.get("shipments", [])
        if not isinstance(shipments, list):
            raise IntegrationUnavailable("Allegro shipments is not a list")
        return [s for s in shipments if isinstance(s, dict)]

    def fetch_tracking(self, carrier_id: str, waybills: list[str]) -> list[dict[str, Any]]:
        """Return the carrier's tracking for up to MAX_TRACKING_WAYBILLS waybills.

        `GET /order/carriers/{carrierId}/tracking?waybill=...`; each item is
        `{"waybill": ..., "trackingDetails": {"statuses": [...], ...}}`.
        """
        if not 1 <= len(waybills) <= MAX_TRACKING_WAYBILLS:
            raise ValueError(f"between 1 and {MAX_TRACKING_WAYBILLS} waybills per request")
        payload = self._get_object(
            f"/order/carriers/{carrier_id}/tracking",
            "tracking",
            params=[("waybill", waybill) for waybill in waybills],
        )
        found = payload.get("waybills", [])
        if not isinstance(found, list):
            raise IntegrationUnavailable("Allegro tracking is not a list")
        return [w for w in found if isinstance(w, dict)]

    def fetch_billing_entries(
        self, occurred_since: datetime, limit: int = MAX_PAGE_SIZE, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return one page of the seller's billing entries (fees, corrections).

        `GET /billing/billing-entries`, newest first, for operations that
        occurred at or after `occurred_since`. Each carries `type`, a signed
        `value` and, for the types that name one, `order.id`.
        """
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
        payload = self._get_object(
            "/billing/billing-entries",
            "billing entries",
            params=[
                ("occurredAt.gte", _timestamp(occurred_since)),
                ("limit", str(limit)),
                ("offset", str(offset)),
            ],
        )
        entries = payload.get("billingEntries", [])
        if not isinstance(entries, list):
            raise IntegrationUnavailable("Allegro billing entries is not a list")
        return [e for e in entries if isinstance(e, dict)]

    def fetch_account_login(self) -> str | None:
        """Return the login of the seller the token belongs to, or None.

        Best-effort, like fetch_offer_image: it only labels the connected
        account in Settings, so failing to read it must not undo a
        connection that worked.
        """
        try:
            token = self._access_token_value()
            response = self._http.get(
                f"{self._api_url}/me",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": ACCEPT_HEADER,
                    "User-Agent": self._user_agent,
                },
            )
            if response.status_code >= 400:
                logger.warning("Allegro /me returned %s", response.status_code)
                return None
            payload = _json_object(response, "Allegro /me")
        except (httpx2.RequestError, IntegrationError) as exc:
            logger.warning("Allegro account login unreadable: %s", exc)
            return None

        login = payload.get("login")
        return login if isinstance(login, str) and login else None

    def fetch_offer_image(self, offer_id: str) -> str | None:
        """Return the offer's first picture, or None if it cannot be read.

        Unlike fetch_checkout_forms, failure here never raises: a picture is
        not required for an order to be valid, so a deleted offer, a missing
        scope or a network error should cost the item its thumbnail, not the
        import. GET /sale/product-offers/{offerId} is public product data,
        not an order resource, so it needs no scope beyond what listing the
        order already required - the same access token is enough, but Allegro
        may still refuse it if the application does not carry the right scope.
        """
        try:
            token = self._access_token_value()
            response = self._http.get(
                f"{self._api_url}/sale/product-offers/{offer_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": ACCEPT_HEADER,
                    "User-Agent": self._user_agent,
                },
            )
            if response.status_code >= 400:
                logger.warning(
                    "Allegro offer %s: image request returned %s",
                    offer_id,
                    response.status_code,
                )
                return None

            payload = _json_object(response, "Allegro product-offer")
        except (httpx2.RequestError, IntegrationError) as exc:
            logger.warning("Allegro offer %s: image unreachable: %s", offer_id, exc)
            return None

        images = payload.get("images")
        if isinstance(images, list) and images and isinstance(images[0], str):
            return images[0]
        return None
