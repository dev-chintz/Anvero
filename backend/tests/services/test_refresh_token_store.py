import httpx2

from app.integrations.allegro.client import AllegroClient
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.services.refresh_token_store import DatabaseRefreshTokenStore

# `session` comes from tests/conftest.py


def _store(session, configured="env-token"):
    return DatabaseRefreshTokenStore(
        IntegrationCredentialRepository(session),
        provider="ALLEGRO",
        configured_token=configured,
    )


def test_the_environment_token_seeds_the_first_run(session):
    assert _store(session).current() == "env-token"


def test_a_rotated_token_outlives_the_process(session):
    _store(session).save("rotated-1")

    # a fresh store over the same database is the next run
    assert _store(session).current() == "rotated-1"


def test_a_new_environment_token_replaces_a_stale_chain(session):
    """Authorizing again puts a new token in .env; the stored chain descends
    from the old one and must not win over it."""
    _store(session, configured="env-token").save("rotated-1")

    assert _store(session, configured="reauthorized").current() == "reauthorized"


def test_the_chain_continues_after_re_authorization(session):
    _store(session, configured="env-token").save("rotated-1")
    _store(session, configured="reauthorized").save("rotated-2")

    assert _store(session, configured="reauthorized").current() == "rotated-2"


def test_removing_the_environment_token_keeps_the_stored_chain(session):
    _store(session, configured="env-token").save("rotated-1")

    assert _store(session, configured="").current() == "rotated-1"


def test_two_import_runs_against_one_database(session):
    """End to end: the second run must present the token the first run was
    given, not the one in the environment."""
    posted = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/token":
            body = dict(p.split("=", 1) for p in request.content.decode().split("&"))
            posted.append(body["refresh_token"])
            return httpx2.Response(
                200,
                json={
                    "access_token": "access",
                    "refresh_token": f"{body['refresh_token']}-next",
                    "expires_in": 43200,
                },
            )
        return httpx2.Response(200, json={"checkoutForms": []})

    for _ in range(2):
        AllegroClient(
            client_id="id",
            client_secret="secret",
            api_url="https://api.test",
            auth_url="https://auth.test",
            user_agent="anvero/0.1.0 (+https://example.com/anvero)",
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
            token_store=_store(session),
        ).fetch_checkout_forms()

    assert posted == ["env-token", "env-token-next"]


def test_a_rotation_notes_when_the_new_token_was_issued(session):
    repository = IntegrationCredentialRepository(session)
    _store(session).save("rotated-1")
    first = repository.get("ALLEGRO").token_issued_at
    assert first is not None

    # the same token saved again is not a new one
    _store(session).save("rotated-1")
    assert repository.get("ALLEGRO").token_issued_at == first

    repository.get("ALLEGRO").token_issued_at = None
    session.commit()
    _store(session).save("rotated-2")
    assert repository.get("ALLEGRO").token_issued_at is not None


def test_connecting_an_account_notes_when_its_token_was_issued(session):
    repository = IntegrationCredentialRepository(session)
    repository.connect("ALLEGRO", "fresh", "seed", "seller")

    assert repository.get("ALLEGRO").token_issued_at is not None
