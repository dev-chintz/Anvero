import base64
from datetime import UTC, datetime, timedelta, timezone

import httpx2
import pytest

from app.integrations.allegro.client import ACCEPT_HEADER, AllegroClient
from app.integrations.base import (
    InMemoryRefreshTokenStore,
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)

TOKEN_URL = "https://auth.test/token"
API_URL = "https://api.test"
USER_AGENT = "anvero/0.1.0 (+https://example.com/anvero)"


def _client(handler, **overrides):
    kwargs = {
        "client_id": "id",
        "client_secret": "secret",
        "refresh_token": "refresh",
        "api_url": API_URL,
        "auth_url": "https://auth.test",
        "user_agent": USER_AGENT,
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


def test_sends_the_configured_user_agent_on_every_request():
    """Allegro blocks the application's key over calls without it."""
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers.get("User-Agent"))
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, json={"checkoutForms": []})

    _client(handler).fetch_checkout_forms()

    assert seen == [USER_AGENT, USER_AGENT]


def test_without_a_user_agent_nothing_reaches_allegro():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("should not reach the network")

    client = _client(handler, user_agent="")

    assert client.is_configured is False
    with pytest.raises(IntegrationNotConfigured, match="ALLEGRO_USER_AGENT"):
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


def _rotating_token_handler(seen_refresh_tokens):
    """Token endpoint that rotates the refresh token like Allegro does."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            body = dict(
                pair.split("=", 1) for pair in request.content.decode().split("&")
            )
            used = body["refresh_token"]
            seen_refresh_tokens.append(used)
            return httpx2.Response(
                200,
                json={
                    "access_token": f"access-for-{used}",
                    "refresh_token": f"{used}-next",
                    "expires_in": 43200,
                },
            )
        return httpx2.Response(200, json={"checkoutForms": []})

    return handler


def test_the_rotated_refresh_token_is_used_on_the_next_run():
    """Regression: the rotated token was discarded, so a second run posted the
    original token, which Allegro invalidates a minute after first use."""
    seen = []
    store = InMemoryRefreshTokenStore("refresh")

    # two clients sharing one store stand in for two separate runs
    _client(_rotating_token_handler(seen), token_store=store).fetch_checkout_forms()
    _client(_rotating_token_handler(seen), token_store=store).fetch_checkout_forms()

    assert seen == ["refresh", "refresh-next"]
    assert store.current() == "refresh-next-next"


def test_a_response_without_a_new_refresh_token_leaves_the_store_alone():
    store = InMemoryRefreshTokenStore("refresh")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, json={"checkoutForms": []})

    _client(handler, token_store=store).fetch_checkout_forms()

    assert store.current() == "refresh"


def test_failing_to_store_the_rotated_token_stops_with_a_clear_error():
    """The old token is already dying, so this must not pass silently."""

    class BrokenStore(InMemoryRefreshTokenStore):
        def save(self, token: str) -> None:
            raise RuntimeError("disk full")

    with pytest.raises(IntegrationError, match="authorizing again"):
        _client(
            _rotating_token_handler([]), token_store=BrokenStore("refresh")
        ).fetch_checkout_forms()


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


# --- fetch_offer_image: best-effort, never raises -------------------------


def test_fetch_offer_image_returns_the_first_picture():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        seen["path"] = request.url.path
        return httpx2.Response(200, json={"images": ["https://img.test/a.jpg", "https://img.test/b.jpg"]})

    image = _client(handler).fetch_offer_image("offer-1")

    assert image == "https://img.test/a.jpg"
    assert seen["path"] == "/sale/product-offers/offer-1"


def test_fetch_offer_image_is_none_when_there_are_no_images():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, json={"images": []})

    assert _client(handler).fetch_offer_image("offer-1") is None


def test_fetch_offer_image_does_not_raise_on_a_missing_offer():
    """A deleted or hidden offer must cost the item its picture, not the import."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(404, json={})

    assert _client(handler).fetch_offer_image("offer-1") is None


def test_fetch_offer_image_does_not_raise_when_the_scope_is_missing():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(403, json={})

    assert _client(handler).fetch_offer_image("offer-1") is None


def test_fetch_offer_image_does_not_raise_on_a_network_failure():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        raise httpx2.ConnectError("boom", request=request)

    assert _client(handler).fetch_offer_image("offer-1") is None


def test_fetch_offer_image_does_not_raise_on_a_non_json_response():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        return httpx2.Response(200, content=b"not json")

    assert _client(handler).fetch_offer_image("offer-1") is None


def test_sends_the_time_filters_in_allegros_format():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        seen["params"] = dict(request.url.params)
        return httpx2.Response(200, json={"checkoutForms": []})

    _client(handler).fetch_checkout_forms(
        bought_since=datetime(2026, 9, 14, 8, 30, 15, 123456, tzinfo=UTC),
        updated_since=datetime(2026, 9, 14, 12, 0, tzinfo=timezone(timedelta(hours=2))),
    )

    assert seen["params"]["lineItems.boughtAt.gte"] == "2026-09-14T08:30:15.123Z"
    # converted to UTC, whatever zone it arrived in
    assert seen["params"]["updatedAt.gte"] == "2026-09-14T10:00:00.000Z"


def test_sends_no_time_filter_unless_asked():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            return _token_response()
        seen["params"] = dict(request.url.params)
        return httpx2.Response(200, json={"checkoutForms": []})

    _client(handler).fetch_checkout_forms()

    assert set(seen["params"]) == {"limit", "offset"}
