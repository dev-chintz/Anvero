from fastapi import HTTPException, status

from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import Token

_invalid_credentials = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
)

# Hashed once, lazily. Verifying a password against it when the email is
# unknown makes that case take as long as a wrong password for a real account;
# otherwise the response time tells an attacker which emails have accounts.
_dummy_hash: str | None = None


def _timing_equaliser_hash() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password-used-only-for-timing")
    return _dummy_hash


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    def login(self, email: str, password: str) -> Token:
        user = self.user_repository.get_by_email(email)

        if user is None:
            verify_password(password, _timing_equaliser_hash())
            raise _invalid_credentials

        if not verify_password(password, user.hashed_password):
            raise _invalid_credentials

        # checked after the password, and answered the same way, so a
        # deactivated account cannot be told apart from a wrong password.
        # It used to receive a token that every endpoint then rejected.
        if not user.is_active:
            raise _invalid_credentials

        return Token(access_token=create_access_token(user.id))
