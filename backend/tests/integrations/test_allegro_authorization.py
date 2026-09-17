import base64
import importlib.util
import urllib.parse
from pathlib import Path

import httpx2
import pytest

from app.integrations.allegro.authorization import (
    DEVICE_CODE_GRANT,
    AllegroDeviceAuthorizer,
    AuthorizationDenied,
    AuthorizationExpired,
    DeviceAuthorization,
)
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# shaped like Allegro's documented example, numbers as strings included
DEVICE_RESPONSE = {
    "device_code": "device-abc",
    "expires_in": "3600",
    "user_code": "cbt3zdu4g",
    "interval": "5",
    "verification_uri": "https://allegro.test/skojarz-aplikacje",
    "verification_uri_complete": "https://allegro.test/skojarz-aplikacje?code=cbt3zdu4g",
}


class FakeClock:
    """Time that moves only when the authorizer sleeps."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _authorizer(handler, clock: FakeClock | None = None) -> AllegroDeviceAuthorizer:
    clock = clock or FakeClock()
    return AllegroDeviceAuthorizer(
        client_id="id",
        client_secret="secret",
        auth_url="https://auth.test/",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        sleep=clock.sleep,
        clock=clock,
    )


def _authorization(expires_in: int = 3600, interval: int = 5) -> DeviceAuthorization:
    return DeviceAuthorization(
        device_code="device-abc",
        user_code="cbt3zdu4g",
        verification_uri_complete="https://allegro.test/skojarz-aplikacje?code=cbt3zdu4g",
        interval=interval,
        expires_in=expires_in,
    )


def _token_responses(*responses: httpx2.Response):
    """A handler answering successive token polls in order."""
    remaining = list(responses)
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return remaining.pop(0)

    return handler, seen


def _pending() -> httpx2.Response:
    return httpx2.Response(400, json={"error": "authorization_pending"})


def _granted() -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 43199,
        },
    )


def test_start_requests_a_device_code_with_basic_auth():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content.decode()
        return httpx2.Response(200, json=DEVICE_RESPONSE)

    authorization = _authorizer(handler).start()

    assert seen["url"] == "https://auth.test/device"
    assert seen["auth"] == f"Basic {base64.b64encode(b'id:secret').decode()}"
    assert seen["body"] == "client_id=id"
    assert authorization == _authorization()


def test_start_falls_back_to_defaults_for_unreadable_timings():
    payload = {**DEVICE_RESPONSE, "interval": "soon", "expires_in": None}

    authorization = _authorizer(lambda r: httpx2.Response(200, json=payload)).start()

    assert (authorization.interval, authorization.expires_in) == (5, 3600)


@pytest.mark.parametrize("status", [400, 401])
def test_start_reports_refused_client_credentials(status):
    """Also what an application registered in the sandbox gets from production."""
    with pytest.raises(IntegrationAuthError, match="sandbox or production"):
        _authorizer(lambda r: httpx2.Response(status)).start()


def test_start_rejects_a_response_without_a_link():
    payload = {
        k: v for k, v in DEVICE_RESPONSE.items() if k != "verification_uri_complete"
    }

    with pytest.raises(IntegrationUnavailable):
        _authorizer(lambda r: httpx2.Response(200, json=payload)).start()


def test_start_reports_an_unreachable_server():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route", request=request)

    with pytest.raises(IntegrationUnavailable, match="unreachable"):
        _authorizer(handler).start()


def test_polls_until_confirmed_and_returns_the_refresh_token():
    handler, seen = _token_responses(_pending(), _pending(), _granted())
    clock = FakeClock()

    token = _authorizer(handler, clock).wait_for_refresh_token(_authorization())

    assert token == "refresh-1"
    assert len(seen) == 3
    # waits before every poll, so the first one does not arrive too early
    assert clock.sleeps == [5, 5, 5]
    assert str(seen[0].url) == "https://auth.test/token"
    body = urllib.parse.parse_qs(seen[0].content.decode())
    assert body == {"grant_type": [DEVICE_CODE_GRANT], "device_code": ["device-abc"]}
    assert seen[0].headers.get("Authorization").startswith("Basic ")


def test_slow_down_lengthens_the_interval_for_good():
    handler, _ = _token_responses(
        httpx2.Response(400, json={"error": "slow_down"}), _pending(), _granted()
    )
    clock = FakeClock()

    _authorizer(handler, clock).wait_for_refresh_token(_authorization())

    assert clock.sleeps == [5, 10, 10]


def test_declining_on_allegros_page_stops_polling():
    handler, seen = _token_responses(
        httpx2.Response(400, json={"error": "access_denied"})
    )

    with pytest.raises(AuthorizationDenied):
        _authorizer(handler).wait_for_refresh_token(_authorization())
    assert len(seen) == 1


def test_gives_up_once_the_device_code_has_expired():
    handler, seen = _token_responses(*[_pending() for _ in range(10)])

    with pytest.raises(AuthorizationExpired):
        _authorizer(handler).wait_for_refresh_token(
            _authorization(expires_in=12, interval=5)
        )
    # polled at 5 and 10 seconds; at 15 the code is dead, so no third request
    assert len(seen) == 2


def test_allegro_reporting_the_code_expired_stops_polling():
    handler, _ = _token_responses(httpx2.Response(400, json={"error": "expired_token"}))

    with pytest.raises(AuthorizationExpired):
        _authorizer(handler).wait_for_refresh_token(_authorization())


def test_an_unknown_device_code_error_is_reported():
    handler, _ = _token_responses(
        httpx2.Response(400, json={"error": "Invalid device code"})
    )

    with pytest.raises(IntegrationAuthError, match="Invalid device code"):
        _authorizer(handler).wait_for_refresh_token(_authorization())


def test_a_server_error_while_polling_is_reported():
    handler, _ = _token_responses(httpx2.Response(503, text="<html>maintenance</html>"))

    with pytest.raises(IntegrationUnavailable, match="503"):
        _authorizer(handler).wait_for_refresh_token(_authorization())


def test_a_grant_without_a_refresh_token_is_an_error():
    handler, _ = _token_responses(
        httpx2.Response(200, json={"access_token": "access-1"})
    )

    with pytest.raises(IntegrationAuthError, match="refresh_token"):
        _authorizer(handler).wait_for_refresh_token(_authorization())


# --- the script -----------------------------------------------------------


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "authorize_allegro", BACKEND_DIR / "scripts" / "authorize_allegro.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "allegro_client_id", "id")
    monkeypatch.setattr(settings, "allegro_client_secret", "secret")
    return _load_script()


def _script_authorizer(*token_responses: httpx2.Response) -> AllegroDeviceAuthorizer:
    remaining = list(token_responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/device":
            return httpx2.Response(200, json=DEVICE_RESPONSE)
        return remaining.pop(0)

    return _authorizer(handler)


def test_script_saves_the_token_to_env_without_printing_it(script, tmp_path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Allegro\nALLEGRO_CLIENT_ID=id\nALLEGRO_REFRESH_TOKEN=old-token\nDEBUG=true\n",
        encoding="utf-8",
    )

    code = script.main(_script_authorizer(_pending(), _granted()), env_file=env_file)

    assert code == 0
    assert env_file.read_text(encoding="utf-8") == (
        "# Allegro\nALLEGRO_CLIENT_ID=id\nALLEGRO_REFRESH_TOKEN=refresh-1\nDEBUG=true\n"
    )
    output = capsys.readouterr()
    assert "refresh-1" not in output.out + output.err
    assert DEVICE_RESPONSE["verification_uri_complete"] in output.out


def test_script_leaves_env_alone_when_authorization_is_declined(script, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ALLEGRO_REFRESH_TOKEN=old-token\n", encoding="utf-8")

    code = script.main(
        _script_authorizer(httpx2.Response(400, json={"error": "access_denied"})),
        env_file=env_file,
    )

    assert code == 3
    assert env_file.read_text(encoding="utf-8") == "ALLEGRO_REFRESH_TOKEN=old-token\n"


def test_script_needs_the_client_id_and_secret(script, monkeypatch, tmp_path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "allegro_client_secret", "")
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("must not contact Allegro without credentials")

    assert script.main(_authorizer(handler), env_file=env_file) == 2
