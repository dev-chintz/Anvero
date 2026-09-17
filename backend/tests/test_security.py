import pytest

from app.core.config import ensure_secret_key
from app.core.security import hash_password, verify_password


def test_password_hashing():
    password = "MySecret123!"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword", hashed)


@pytest.mark.parametrize(
    "key",
    ["", "   ", "CHANGE_ME", "change_me", "secret", "short-but-random-7fQ2"],
)
def test_the_api_refuses_a_guessable_signing_key(key):
    """Regression: .env.example shipped SECRET_KEY=CHANGE_ME and the default
    was empty, so anyone could sign a valid login token."""
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ensure_secret_key(key)


def test_a_long_random_signing_key_is_accepted():
    ensure_secret_key("9sV1-kQ7rXpL3eT0wZb8hN5yC2mA6uJ4dF_gR")
