import base64

import httpx2
import pytest

from app.integrations.allegro.client import ACCEPT_HEADER, AllegroClient
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)

TOKEN_URL = "https://auth.test/token"
API_URL = "https://api.test"


def _client(handler, **overrides):
    kwargs = {
        "client_id": "id",
        "client_secret": "secret",
        "refresh_token": "refresh",
        "api_url": API_URL,
        "auth_url": "https://auth.test",
        "http_client": httpx2.Client(transport=httpx2.MockTransport(handler)),
    }
    kwargs.update(overrides)
    return AllegroClient(**kwargs)


def _token_response(expires_in=3600):
    return httpx2.Response(
        200, json={"access_token": "access-123", "expires_in": expires_in}
    )


def test_sends_the_version_header_and_bearer_token():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        seen["auth"] = request.headers.get("Authorization")
        seen["accept"] = request.headers.get("Accept")
        return httpx2.Response(200, json={"checkoutForms": []})

    _client(handler).fetch_checkout_forms()

    assert seen["auth"] == "Bearer access-123"
    # the API refuses requests that do not pin a version
    assert seen["accept"] == ACCEPT_HEADER


def test_refreshes_the_token_with_basic_auth_and_refresh_grant():
    """Orders need a user-context token, which client_credentials cannot give."""
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            seen["auth"] = request.headers.get("Authorization")
            seen["body"] = request.content.decode()
            return _token_response()
        return httpx2.Response(200, json={"checkoutForms": []})

    _client(handler).fetch_checkout_forms()

    expected = base64.b64encode(b"id:secret").decode()
    assert seen["auth"] == f"Basic {expected}"
    assert "grant_type=refresh_token" in seen["body"]
    assert "refresh_token=refresh" in seen["body"]


def test_reuses_a_token_that_has_not_expired():
    calls = {"token": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            calls["token"] += 1
            return _token_response()
        return httpx2.Response(200, json={"checkoutForms": []})

    client = _client(handler)
    client.fetch_checkout_forms()
    client.fetch_checkout_forms()

    assert calls["token"] == 1


def test_expired_token_is_fetched_again():
    calls = {"token": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            calls["token"] += 1
            # already past the safety margin, so it counts as expired
            return _token_response(expires_in=0)
        return httpx2.Response(200, json={"checkoutForms": []})

    client = _client(handler)
    client.fetch_checkout_forms()
    client.fetch_checkout_forms()

    assert calls["token"] == 2


def test_returns_the_checkout_forms():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, json={"checkoutForms": [{"id": "a"}, {"id": "b"}]})

    forms = _client(handler).fetch_checkout_forms()

    assert [form["id"] for form in forms] == ["a", "b"]


def test_missing_credentials_are_reported_before_any_request():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("should not reach the network")

    client = _client(handler, refresh_token="")

    assert client.is_configured is False
    with pytest.raises(IntegrationNotConfigured):
        client.fetch_checkout_forms()


def test_a_rejected_refresh_token_asks_for_re_authorization():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"error": "invalid_grant"})

    with pytest.raises(IntegrationAuthError, match="authorizing again"):
        _client(handler).fetch_checkout_forms()


def test_a_403_on_orders_points_at_the_missing_scope():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(403, json={})

    with pytest.raises(IntegrationAuthError, match="orders:read"):
        _client(handler).fetch_checkout_forms()


def test_a_401_on_orders_drops_the_cached_token():
    calls = {"token": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            calls["token"] += 1
            return _token_response()
        return httpx2.Response(401, json={})

    client = _client(handler)
    for _ in range(2):
        with pytest.raises(IntegrationAuthError):
            client.fetch_checkout_forms()

    # a stale token must not be reused after the API rejected it
    assert calls["token"] == 2


def test_a_network_failure_is_reported_as_unavailable():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("boom", request=request)

    with pytest.raises(IntegrationUnavailable, match="unreachable"):
        _client(handler).fetch_checkout_forms()


def test_a_server_error_is_reported_as_unavailable():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(503, json={})

    with pytest.raises(IntegrationUnavailable, match="503"):
        _client(handler).fetch_checkout_forms()


def test_a_non_json_token_response_is_reported_as_unavailable():
    """A maintenance page answering 200 must not end in a raw traceback."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, text="<html>maintenance</html>")

    with pytest.raises(IntegrationUnavailable, match="did not return JSON"):
        _client(handler).fetch_checkout_forms()


def test_a_non_json_orders_response_is_reported_as_unavailable():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, text="<html>maintenance</html>")

    with pytest.raises(IntegrationUnavailable, match="did not return JSON"):
        _client(handler).fetch_checkout_forms()


def test_json_that_is_not_an_object_is_reported_as_unavailable():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, json=["unexpected"])

    with pytest.raises(IntegrationUnavailable, match="not an object"):
        _client(handler).fetch_checkout_forms()


def test_rejects_a_page_size_the_api_will_not_accept():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("should not reach the network")

    with pytest.raises(ValueError, match="between 1 and 100"):
        _client(handler).fetch_checkout_forms(limit=101)
