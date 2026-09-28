"""Integration secrets encrypted at rest (GDPR, `docs/GDPR.md`).

Allegro's refresh token and client secret and InPost's token are kept in the
database, and so in every backup of it. With `SECRETS_KEY` set they are stored
encrypted (Fernet: AES with an integrity check), marked by a prefix; without it
they are stored as plain text, as they always were, so a machine that has not
set a key works as before. A value is read the same way whichever it is, so
setting the key needs no migration: `scripts/encrypt_secrets.py` rewrites what
is stored, and Allegro's token, which rotates on every import, is rewritten
encrypted by the next import anyway.

The key lives beside `SECRET_KEY` (in `.env`, or the NAS's compose file), never
in the database or its backups. Without it an encrypted value cannot be read:
the error says so rather than handing a marketplace garbage.
"""

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings

PREFIX = "enc:v1:"


class SecretsKeyError(RuntimeError):
    pass


def new_key() -> str:
    return Fernet.generate_key().decode()


def _fernet() -> Fernet | None:
    key = settings.secrets_key.strip()
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise SecretsKeyError(
            "SECRETS_KEY is not a valid key; generate one with scripts/encrypt_secrets.py --new-key"
        ) from exc


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str) -> str:
    """The value as it is to be stored: encrypted when a key is set, and an
    empty value, or one already encrypted, as it is."""
    fernet = _fernet()
    if fernet is None or not value or is_encrypted(value):
        return value
    return PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not is_encrypted(value):
        return value
    fernet = _fernet()
    if fernet is None:
        raise SecretsKeyError(
            "A stored secret is encrypted, and SECRETS_KEY is not set on this machine"
        )
    try:
        return fernet.decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise SecretsKeyError(
            "A stored secret was encrypted with another SECRETS_KEY than this machine's"
        ) from exc


class EncryptedText(TypeDecorator):
    """A text column holding a secret: encrypted on the way in when a key is
    set, decrypted on the way out."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return decrypt(value) if value is not None else None
