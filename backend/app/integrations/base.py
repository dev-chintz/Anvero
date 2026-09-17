from typing import Protocol

from app.models.order import OrderSource
from app.schemas.order import OrderCreate


class IntegrationError(Exception):
    """Base for every failure originating in an external marketplace."""


class IntegrationNotConfigured(IntegrationError):
    """Credentials for this marketplace are missing."""


class IntegrationAuthError(IntegrationError):
    """The marketplace rejected our credentials."""


class IntegrationUnavailable(IntegrationError):
    """The marketplace could not be reached, or answered with an error."""


class RefreshTokenStore(Protocol):
    """Where a rotating refresh token lives between uses.

    Allegro invalidates a refresh token about a minute after it is used and
    hands back a replacement, so whatever issued the refresh must record the
    replacement or the next run has nothing that works.
    """

    def current(self) -> str: ...

    def save(self, token: str) -> None: ...


class InMemoryRefreshTokenStore:
    """Keeps the rotated token for the life of the process only.

    Enough for tests and for a single run; anything that runs again later
    needs a persistent store, or its second run starts from a dead token.
    """

    def __init__(self, token: str):
        self._token = token

    def current(self) -> str:
        return self._token

    def save(self, token: str) -> None:
        self._token = token


class MarketplaceAdapter(Protocol):
    """What the rest of the application may assume about an integration.

    An adapter converts a marketplace's own representation into OrderCreate.
    Nothing outside the adapter's own module should ever see the raw payload,
    so callers stay independent of any single marketplace's API.
    """

    source: OrderSource

    def fetch_orders(self, limit: int = 100, offset: int = 0) -> list[OrderCreate]:
        """Return a page of orders already translated to the domain shape."""
        ...
