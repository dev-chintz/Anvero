"""Allegro's Message Center: the client's calls, the mapping, and the adapter
that pages through threads and messages."""

from datetime import UTC, datetime

import httpx2
import pytest

from app.integrations.allegro.client import MESSAGING_PAGE_SIZE, AllegroClient
from app.integrations.allegro.mapper import map_message, map_thread
from app.integrations.allegro.messaging import AllegroMessagingAdapter
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.models.message import MessageDirection


def _raw_thread(thread_id="T1", login="buyer1", read=False, last="2026-09-20T10:00:00.000Z"):
    return {
        "id": thread_id,
        "read": read,
        "lastMessageDateTime": last,
        "interlocutor": {"login": login},
    }


def _raw_message(message_id="M1", text="Hello", author="buyer1", created="2026-09-20T10:00:00.000Z"):
    return {"id": message_id, "text": text, "author": {"login": author}, "createdAt": created}


# --- the client -------------------------------------------------------------


def _client(handler):
    return AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url="https://api.test",
        auth_url="https://auth.test",
        user_agent="anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def test_fetch_threads_asks_the_message_center():
    seen = []

    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(200, json={"threads": [_raw_thread()]})

    threads = _client(handler).fetch_threads(limit=15, offset=100)

    assert threads == [_raw_thread()]
    assert seen[0].url.path == "/messaging/threads"
    assert (seen[0].url.params["limit"], seen[0].url.params["offset"]) == ("15", "100")


def test_fetch_thread_messages_asks_the_thread():
    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        assert request.url.path == "/messaging/threads/T1/messages"
        return httpx2.Response(200, json={"messages": [_raw_message()]})

    messages = _client(handler).fetch_thread_messages("T1")

    assert messages == [_raw_message()]


def test_reply_to_thread_posts_the_text():
    seen = []

    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(200, json={"id": "M2"})

    answer = _client(handler).reply_to_thread("T1", "Dziękuję za zamówienie")

    assert answer == {"id": "M2"}
    assert seen[0].url.path == "/messaging/threads/T1/messages"
    import json as _json

    assert _json.loads(seen[0].content) == {"text": "Dziękuję za zamówienie", "attachments": []}


def test_a_refused_reply_names_the_messaging_scope():
    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        return httpx2.Response(403)

    with pytest.raises(IntegrationAuthError, match="allegro:api:messaging"):
        _client(handler).reply_to_thread("T1", "hi")


# --- the mapping --------------------------------------------------------


def test_maps_a_thread():
    thread = map_thread(_raw_thread())

    assert thread is not None
    assert thread.external_id == "T1"
    assert thread.interlocutor_login == "buyer1"
    assert thread.read is False
    assert thread.last_message_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def test_a_thread_without_an_id_is_dropped():
    assert map_thread({"read": True}) is None


def test_a_thread_with_an_unreadable_read_flag_defaults_to_read():
    thread = map_thread({"id": "T1", "read": "not a bool"})

    assert thread is not None
    assert thread.read is True


def test_maps_an_incoming_message_from_the_buyer():
    message = map_message(_raw_message(author="buyer1"), seller_login="seller1")

    assert message is not None
    assert message.direction is MessageDirection.IN
    assert message.author_login == "buyer1"
    assert message.text == "Hello"


def test_maps_an_outgoing_message_from_the_seller():
    message = map_message(_raw_message(author="seller1"), seller_login="seller1")

    assert message is not None
    assert message.direction is MessageDirection.OUT


def test_allegros_own_flag_decides_the_direction():
    """`author.isInterlocutor` is true for the other party, false for the seller."""
    from_buyer = {**_raw_message(author="whoever"), "author": {"login": "whoever", "isInterlocutor": True}}
    from_seller = {**_raw_message(author="whoever"), "author": {"login": "whoever", "isInterlocutor": False}}

    # without any seller login at all, and against the login comparison's own answer
    assert map_message(from_buyer, seller_login=None).direction is MessageDirection.IN
    assert map_message(from_seller, seller_login=None).direction is MessageDirection.OUT
    assert map_message(from_seller, seller_login="whoever").direction is MessageDirection.OUT
    assert map_message(from_buyer, seller_login="whoever").direction is MessageDirection.IN


def test_the_page_size_is_what_the_message_center_allows():
    """A larger `limit` is answered 422 (Incorrect limit or offset)."""
    assert MESSAGING_PAGE_SIZE == 20
    for method in (
        lambda client: client.fetch_threads(limit=MESSAGING_PAGE_SIZE + 1),
        lambda client: client.fetch_thread_messages("T1", limit=MESSAGING_PAGE_SIZE + 1),
    ):
        with pytest.raises(ValueError, match="limit must be between 1 and 20"):
            method(_client(lambda request: httpx2.Response(200, json={})))


def test_a_refusal_carries_what_allegro_said():
    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        return httpx2.Response(
            422, json={"errors": [{"code": "X", "userMessage": "Incorrect limit or offset"}]}
        )

    with pytest.raises(IntegrationUnavailable, match="422 for message threads: Incorrect limit or offset"):
        _client(handler).fetch_threads()


def test_a_refusal_without_a_readable_body_is_still_reported():
    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        return httpx2.Response(422, text="not json")

    with pytest.raises(IntegrationUnavailable) as caught:
        _client(handler).fetch_threads()

    assert str(caught.value) == "Allegro API returned 422 for message threads"


def test_without_a_seller_login_everything_maps_as_incoming():
    message = map_message(_raw_message(author="seller1"), seller_login=None)

    assert message is not None
    assert message.direction is MessageDirection.IN


def test_a_message_without_text_is_dropped():
    assert map_message({"id": "M1", "author": {"login": "x"}}, seller_login=None) is None


# --- the adapter --------------------------------------------------------


class FakeMessagingClient:
    is_configured = True

    def __init__(self, thread_pages=None, message_pages=None, error=None):
        self.thread_pages = thread_pages or []
        self.message_pages = message_pages or []
        self.error = error
        self.thread_calls = []
        self.message_calls = []

    def fetch_threads(self, limit=MESSAGING_PAGE_SIZE, offset=0):
        self.thread_calls.append((limit, offset))
        if self.error:
            raise self.error
        index = offset // limit
        return self.thread_pages[index] if index < len(self.thread_pages) else []

    def fetch_thread_messages(self, thread_id, limit=MESSAGING_PAGE_SIZE, offset=0):
        self.message_calls.append((thread_id, limit, offset))
        index = offset // limit
        pages = self.message_pages
        return pages[index] if index < len(pages) else []


def test_iter_thread_pages_reads_every_page_until_a_short_one():
    full = [_raw_thread(f"T{i}") for i in range(MESSAGING_PAGE_SIZE)]
    client = FakeMessagingClient([full, [_raw_thread("LAST")]])

    pages = list(AllegroMessagingAdapter(client=client).iter_thread_pages())

    assert [len(p) for p in pages] == [MESSAGING_PAGE_SIZE, 1]
    assert [c[1] for c in client.thread_calls] == [0, MESSAGING_PAGE_SIZE]


def test_an_unusable_thread_costs_only_itself():
    client = FakeMessagingClient([[_raw_thread("T1"), {"read": True}, _raw_thread("T2")]])

    pages = list(AllegroMessagingAdapter(client=client).iter_thread_pages())

    assert [t.external_id for t in pages[0]] == ["T1", "T2"]


def test_a_failing_thread_page_raises_instead_of_returning_a_partial_read():
    client = FakeMessagingClient(error=IntegrationUnavailable("boom"))

    with pytest.raises(IntegrationUnavailable):
        list(AllegroMessagingAdapter(client=client).iter_thread_pages())


def test_fetch_thread_messages_reads_every_page():
    full = [_raw_message(f"M{i}") for i in range(MESSAGING_PAGE_SIZE)]
    client = FakeMessagingClient(message_pages=[full, [_raw_message("LAST")]])

    messages = AllegroMessagingAdapter(client=client).fetch_thread_messages("T1", "seller1")

    assert len(messages) == MESSAGING_PAGE_SIZE + 1
    assert [c[0] for c in client.message_calls] == ["T1", "T1"]


def test_a_message_is_read_as_the_text_a_person_wrote_not_as_html():
    raw = _raw_message(text="Dzi\u0119kujemy za zam&oacute;wienie &quot;AN-1&quot;&zwnj;")

    message = map_message(raw, seller_login="seller1")

    assert message is not None
    assert message.text == 'Dzi\u0119kujemy za zam\u00f3wienie "AN-1"'


def test_a_message_with_nothing_but_invisible_text_is_dropped():
    assert map_message(_raw_message(text="&zwnj;&nbsp;"), seller_login=None) is None
