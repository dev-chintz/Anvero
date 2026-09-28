"""Integration secrets encrypted at rest when SECRETS_KEY is set."""

import pytest
from sqlalchemy import text

from app.core import secrets
from app.core.config import settings
from app.models.integration import IntegrationCredential, IntegrationSettings
from app.models.marketplace_write import AppSetting
from app.services import inpost_settings

KEY = secrets.new_key()


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(settings, "secrets_key", KEY)


def _raw(session, sql):
    return session.execute(text(sql)).scalar_one()


def test_without_a_key_a_secret_is_stored_as_before(session):
    session.add(IntegrationCredential(provider="ALLEGRO", refresh_token="rt-plain", seed_fingerprint="f"))
    session.commit()

    assert _raw(session, "SELECT refresh_token FROM integration_credentials") == "rt-plain"


def test_with_a_key_the_stored_token_is_unreadable_and_reads_back_whole(session, with_key):
    session.add(IntegrationCredential(provider="ALLEGRO", refresh_token="rt-secret", seed_fingerprint="f"))
    session.add(
        IntegrationSettings(
            provider="ALLEGRO", client_id="id", client_secret="cs-secret",
            user_agent="ua", environment="sandbox",
        )
    )
    session.commit()
    session.expunge_all()

    stored = _raw(session, "SELECT refresh_token FROM integration_credentials")
    assert stored.startswith(secrets.PREFIX)
    assert "rt-secret" not in stored
    assert "cs-secret" not in _raw(session, "SELECT client_secret FROM integration_settings")
    assert session.get(IntegrationCredential, "ALLEGRO").refresh_token == "rt-secret"
    assert session.get(IntegrationSettings, "ALLEGRO").client_secret == "cs-secret"


def test_a_plain_value_stored_before_the_key_still_reads(session, monkeypatch):
    session.add(IntegrationCredential(provider="ALLEGRO", refresh_token="rt-old", seed_fingerprint="f"))
    session.commit()
    session.expunge_all()
    monkeypatch.setattr(settings, "secrets_key", KEY)

    assert session.get(IntegrationCredential, "ALLEGRO").refresh_token == "rt-old"


def test_an_encrypted_value_without_the_key_says_so(monkeypatch):
    monkeypatch.setattr(settings, "secrets_key", KEY)
    stored = secrets.encrypt("rt-secret")
    monkeypatch.setattr(settings, "secrets_key", "")

    with pytest.raises(secrets.SecretsKeyError, match="not set"):
        secrets.decrypt(stored)


def test_another_key_says_so(monkeypatch):
    monkeypatch.setattr(settings, "secrets_key", KEY)
    stored = secrets.encrypt("rt-secret")
    monkeypatch.setattr(settings, "secrets_key", secrets.new_key())

    with pytest.raises(secrets.SecretsKeyError, match="another"):
        secrets.decrypt(stored)


def test_a_malformed_key_says_how_to_make_one(monkeypatch):
    monkeypatch.setattr(settings, "secrets_key", "not-a-key")

    with pytest.raises(secrets.SecretsKeyError, match="--new-key"):
        secrets.encrypt("x")


def test_encrypting_twice_does_not_wrap_it_again(with_key):
    once = secrets.encrypt("x")
    assert secrets.encrypt(once) == once
    assert secrets.encrypt("") == ""


def test_the_inpost_token_is_encrypted_too(session, with_key):
    inpost_settings.save_settings(session, "inpost-token-123", "777", "sandbox", "small", None)

    stored = session.get(AppSetting, inpost_settings.TOKEN_KEY).value
    assert stored.startswith(secrets.PREFIX)
    assert inpost_settings.get_settings(session).token == "inpost-token-123"
