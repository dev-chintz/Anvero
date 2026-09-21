"""One-time authorization of the application by the OAuth device flow.

Reading a seller's orders needs a refresh token issued in a user context, and
only a person logged in to Allegro can grant one. The device flow suits that:
it needs no redirect URI and no web server, just a link the person opens and
confirms, while this side polls for the result. See docs/INTEGRATIONS.md.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx2

from app.integrations.allegro.client import REQUEST_TIMEOUT_SECONDS, _json_object
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationUnavailable,
)

DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

# RFC 8628 defaults, used when Allegro leaves a value out
DEFAULT_INTERVAL_SECONDS = 5
DEFAULT_EXPIRES_IN_SECONDS = 3600
SLOW_DOWN_STEP_SECONDS = 5


class AuthorizationDenied(IntegrationAuthError):
    """The person declined the authorization on Allegro's page."""


class AuthorizationExpired(IntegrationError):
    """Nobody confirmed the authorization before the device code expired."""


@dataclass(frozen=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri_complete: str
    interval: int
    expires_in: int


@dataclass(frozen=True)
class DevicePoll:
    """One answer to "has the person confirmed yet?"."""

    refresh_token: str | None = None
    slow_down: bool = False


def _positive_int(value: object, default: int) -> int:
    # Allegro's documented examples send these numbers as strings
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


class AllegroDeviceAuthorizer:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        auth_url: str,
        user_agent: str,
        http_client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if not user_agent:
            # Allegro blocks the application's key over calls without it
            raise ValueError("an Allegro User-Agent is required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._auth_url = auth_url.rstrip("/")
        self._user_agent = user_agent
        self._http = http_client or httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS)
        self._sleep = sleep
        self._clock = clock

    def _post(self, path: str, data: dict[str, str]) -> httpx2.Response:
        try:
            return self._http.post(
                f"{self._auth_url}/{path}",
                auth=httpx2.BasicAuth(self._client_id, self._client_secret),
                headers={"User-Agent": self._user_agent},
                data=data,
            )
        except httpx2.RequestError as exc:
            raise IntegrationUnavailable(
                f"Allegro {path} endpoint unreachable: {exc}"
            ) from exc

    def start(self) -> DeviceAuthorization:
        """Ask Allegro for a device code and the link a person must confirm."""
        response = self._post("device", {"client_id": self._client_id})
        if response.status_code in (400, 401):
            raise IntegrationAuthError(
                "Allegro refused the client id or secret; check ALLEGRO_CLIENT_ID, "
                "ALLEGRO_CLIENT_SECRET, and that ALLEGRO_AUTH_URL belongs to the "
                "environment the application is registered in (sandbox or production)"
            )
        if response.status_code >= 400:
            raise IntegrationUnavailable(
                f"Allegro device endpoint returned {response.status_code}"
            )

        payload = _json_object(response, "Allegro device endpoint")
        device_code = payload.get("device_code")
        user_code = payload.get("user_code")
        link = payload.get("verification_uri_complete")
        if not (
            isinstance(device_code, str)
            and isinstance(user_code, str)
            and isinstance(link, str)
            and device_code
            and link
        ):
            raise IntegrationUnavailable(
                "Allegro device endpoint did not return a device code and link"
            )
        return DeviceAuthorization(
            device_code=device_code,
            user_code=user_code,
            verification_uri_complete=link,
            interval=_positive_int(payload.get("interval"), DEFAULT_INTERVAL_SECONDS),
            expires_in=_positive_int(
                payload.get("expires_in"), DEFAULT_EXPIRES_IN_SECONDS
            ),
        )

    def poll_once(self, authorization: DeviceAuthorization) -> "DevicePoll":
        """Ask Allegro once whether the person has confirmed yet.

        Returns the refresh token when they have, `pending` otherwise (with
        `slow_down` set when Allegro wants the polling eased off). Raises when
        the person declined, the code expired, or Allegro refused something.
        Only the refresh token is kept: the access token that comes with it
        expires within hours, and the import obtains its own.
        """
        response = self._post(
            "token",
            {
                "grant_type": DEVICE_CODE_GRANT,
                "device_code": authorization.device_code,
            },
        )

        if response.status_code == 200:
            payload = _json_object(response, "Allegro token endpoint")
            refresh_token = payload.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                raise IntegrationAuthError("Allegro returned no refresh_token")
            return DevicePoll(refresh_token=refresh_token)

        if response.status_code == 401:
            raise IntegrationAuthError("Allegro refused the client id or secret")
        if response.status_code != 400:
            raise IntegrationUnavailable(
                f"Allegro token endpoint returned {response.status_code}"
            )

        try:
            error = _json_object(response, "Allegro token endpoint").get("error")
        except IntegrationUnavailable:
            error = None
        if error == "authorization_pending":
            return DevicePoll()
        if error == "slow_down":
            return DevicePoll(slow_down=True)
        if error == "access_denied":
            raise AuthorizationDenied("the authorization was declined on Allegro's page")
        if error == "expired_token":
            raise AuthorizationExpired(
                "the authorization was not confirmed in time; start it again"
            )
        # Allegro answers an unknown or already used device code this way
        raise IntegrationAuthError(
            f"Allegro refused the device code ({error or 'no reason given'})"
        )

    def wait_for_refresh_token(self, authorization: DeviceAuthorization) -> str:
        """Poll until the person confirms, then return the refresh token."""
        deadline = self._clock() + authorization.expires_in
        interval = authorization.interval

        while True:
            self._sleep(interval)
            if self._clock() > deadline:
                raise AuthorizationExpired(
                    "the authorization was not confirmed in time; run the script again"
                )
            result = self.poll_once(authorization)
            if result.refresh_token is not None:
                return result.refresh_token
            if result.slow_down:
                interval += SLOW_DOWN_STEP_SECONDS
