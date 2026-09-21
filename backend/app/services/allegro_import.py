from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.allegro import AllegroAdapter
from app.integrations.allegro.client import AllegroClient
from app.models.order import OrderSource
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.order_repository import OrderRepository
from app.services.order_import_service import OrderImportService
from app.services.refresh_token_store import DatabaseRefreshTokenStore


def build_allegro_client(db: Session) -> AllegroClient:
    """Wire an AllegroClient with the database-backed rotating refresh token.

    Shared by scripts/import_allegro.py and the /integrations/allegro
    endpoints so both read and rotate the same stored token. A second copy of
    this wiring would read a stale token and could not persist a rotation it
    did not know about; see DECISIONS.md, "Rotated Allegro Refresh Tokens
    Live in the Database".
    """
    token_store = DatabaseRefreshTokenStore(
        IntegrationCredentialRepository(db),
        provider=OrderSource.ALLEGRO.value,
        configured_token=settings.allegro_refresh_token,
    )
    return AllegroClient(token_store=token_store)


def build_allegro_import_service(db: Session) -> OrderImportService:
    """Build the same OrderImportService the import script builds."""
    client = build_allegro_client(db)
    return OrderImportService(
        OrderRepository(db),
        AllegroAdapter(client=client),
        credentials=IntegrationCredentialRepository(db),
        initial_days=settings.allegro_initial_import_days,
    )
