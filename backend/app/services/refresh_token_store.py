import hashlib

from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DatabaseRefreshTokenStore:
    """Keeps a marketplace's rotating refresh token in the database.

    The token from the environment seeds the chain. After that the stored,
    rotated token wins, unless the environment now holds a different token
    than the one the chain started from — that means the application was
    authorized again, and the fresh token must replace the stale chain.
    """

    def __init__(
        self,
        repository: IntegrationCredentialRepository,
        provider: str,
        configured_token: str,
    ):
        self._repository = repository
        self._provider = provider
        self._configured = configured_token

    def current(self) -> str:
        stored = self._repository.get(self._provider)
        if stored is None:
            return self._configured
        if self._configured and stored.seed_fingerprint != _fingerprint(self._configured):
            return self._configured
        return stored.refresh_token

    def save(self, token: str) -> None:
        stored = self._repository.get(self._provider)
        if self._configured:
            seed = _fingerprint(self._configured)
        elif stored is not None:
            # no token in the environment any more; keep the chain's origin so
            # re-adding the same token later is not mistaken for a new one
            seed = stored.seed_fingerprint
        else:
            seed = _fingerprint("")
        self._repository.save(self._provider, token, seed)
