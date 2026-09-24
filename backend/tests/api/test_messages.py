"""The unified inbox: listing threads, a thread's messages, putting one
aside, and replying (through safe mode, so no network is needed here)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.order import OrderSource
from app.repositories.message_repository import MessageRepository
from app.repositories.user_repository import UserRepository
from app.schemas.message import SyncedMessage, SyncedThread
from app.schemas.user import UserCreate
from app.services.user_service import UserService

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def api():
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        operator = UserService(UserRepository(db)).create_user(
            UserCreate(email="inbox-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)


def _thread(db, external_id="T1", **overrides):
    data = {"external_id": external_id, "interlocutor_login": "buyer1"}
    data.update(overrides)
    return MessageRepository(db).upsert_thread(OrderSource.ALLEGRO, SyncedThread(**data))


def test_the_inbox_lists_threads_newest_first(api):
    older = _thread(api, "T1", last_message_at=datetime(2026, 9, 20, tzinfo=UTC))
    newer = _thread(api, "T2", last_message_at=datetime(2026, 9, 21, tzinfo=UTC))

    body = client.get("/api/v1/messages/threads").json()

    assert [t["id"] for t in body] == [str(newer.id), str(older.id)]


def test_a_thread_set_aside_is_excluded_by_default(api):
    thread = _thread(api, "T1")
    MessageRepository(api).set_aside(thread, True)

    assert client.get("/api/v1/messages/threads").json() == []
    aside = client.get("/api/v1/messages/threads?aside=true").json()
    assert [t["id"] for t in aside] == [str(thread.id)]


def test_a_thread_shows_its_messages(api):
    thread = _thread(api, "T1")
    MessageRepository(api).add_messages(
        thread, [SyncedMessage(text="Hello", direction="IN", sent_at=datetime.now(UTC))]
    )

    body = client.get(f"/api/v1/messages/threads/{thread.id}").json()

    assert len(body["messages"]) == 1
    assert body["messages"][0]["text"] == "Hello"


def test_an_unknown_thread_is_404(api):
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/messages/threads/{missing}").status_code == 404


def test_putting_a_thread_aside_and_back(api):
    thread = _thread(api, "T1")

    body = client.patch(f"/api/v1/messages/threads/{thread.id}/aside", json={"aside": True}).json()
    assert body["aside"] is True

    body = client.patch(f"/api/v1/messages/threads/{thread.id}/aside", json={"aside": False}).json()
    assert body["aside"] is False


def test_replying_in_safe_mode_is_recorded_but_not_sent(api):
    thread = _thread(api, "T1")

    response = client.post(
        f"/api/v1/messages/threads/{thread.id}/reply", json={"text": "Dziękuję za zamówienie"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["marketplace_write"]["outcome"] == "DRY_RUN"
    assert body["thread"]["messages"][-1]["text"] == "Dziękuję za zamówienie"
    assert body["thread"]["messages"][-1]["created_in_anvero"] is True


def test_messages_need_a_login(api):
    thread = _thread(api, "T1")
    anonymous = TestClient(app)

    assert anonymous.get("/api/v1/messages/threads").status_code == 401
    assert (
        anonymous.post(f"/api/v1/messages/threads/{thread.id}/reply", json={"text": "hi"}).status_code
        == 401
    )


# --- searching the inbox ------------------------------------------------------------


def _message(db, thread, text, external_id):
    MessageRepository(db).add_messages(
        thread,
        [
            SyncedMessage(
                external_id=external_id,
                direction="IN",
                author_login=thread.interlocutor_login,
                text=text,
                sent_at=datetime(2026, 9, 20, 12, tzinfo=UTC),
            )
        ],
    )


def _found(query: str, **params) -> list[str]:
    body = client.get("/api/v1/messages/threads", params={"search": query, **params}).json()
    return [t["interlocutor_login"] for t in body]


def test_a_buyer_is_found_by_nick_however_it_was_typed(api):
    _thread(api, "T1", interlocutor_login="Welka2marki")
    _thread(api, "T2", interlocutor_login="martita1031")

    assert _found("welka2") == ["Welka2marki"]
    assert _found("MARTITA") == ["martita1031"]
    assert _found("1031") == ["martita1031"]
    assert _found("nobody") == []


def test_a_search_looks_through_the_messages_and_the_order_too(api):
    thread = _thread(api, "T1", interlocutor_login="buyer1", order_external_id="ORDER-42-XYZ")
    _message(api, thread, "Prosz\u0119 o zmian\u0119 adresu na Warszawa", "M1")
    _thread(api, "T2", interlocutor_login="buyer2")

    assert _found("adresu") == ["buyer1"]
    assert _found("order-42") == ["buyer1"]


def test_a_search_covers_the_threads_set_aside_and_the_tab_can_narrow_it(api):
    kept = _thread(api, "T1", interlocutor_login="same-nick-a")
    put_aside = _thread(api, "T2", interlocutor_login="same-nick-b")
    MessageRepository(api).set_aside(put_aside, True)

    assert sorted(_found("same-nick")) == ["same-nick-a", "same-nick-b"]
    assert _found("same-nick", aside="true") == ["same-nick-b"]
    assert _found("same-nick", aside="false") == ["same-nick-a"]
    # and without a search, the default view is still what needs attention
    assert [t["id"] for t in client.get("/api/v1/messages/threads").json()] == [str(kept.id)]


def test_a_search_treats_wildcards_as_the_characters_they_are(api):
    _thread(api, "T1", interlocutor_login="a_b")
    _thread(api, "T2", interlocutor_login="axb")
    _thread(api, "T3", interlocutor_login="100%_sure")

    assert _found("a_b") == ["a_b"]
    assert _found("%") == ["100%_sure"]


def test_a_blank_search_is_no_search(api):
    _thread(api, "T1", interlocutor_login="buyer1")

    assert _found("   ") == ["buyer1"]


def test_the_search_is_not_limited_to_the_newest_threads(api):
    for i in range(3):
        _thread(api, f"T{i}", interlocutor_login=f"nick{i}", last_message_at=datetime(2026, 9, 20 + i, tzinfo=UTC))

    # only the newest one is listed with a limit of 1, but a search still reaches the oldest
    assert len(client.get("/api/v1/messages/threads", params={"limit": 1}).json()) == 1
    assert _found("nick0", limit=1) == ["nick0"]
