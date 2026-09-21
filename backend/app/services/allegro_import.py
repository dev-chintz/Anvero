from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.allegro import AllegroAdapter
from app.integrations.allegro.client import AllegroClient
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.order_repository import OrderRepository
from app.services.allegro_settings import build_client
from app.services.order_import_service import OrderImportService


def build_allegro_client(db: Session) -> AllegroClient:
    """Wire an AllegroClient with the database-backed rotating refresh token.

    Shared by scripts/import_allegro.py and the /integrations/allegro
    endpoints so both read and rotate the same stored token. A second copy of
    this wiring would read a stale token and could not persist a rotation it
    did not know about; see DECISIONS.md, "Rotated Allegro Refresh Tokens
    Live in the Database". Which application's credentials it uses (entered
    in Settings, else the environment) is decided in allegro_settings.
    """
    return build_client(db)


def build_allegro_import_service(db: Session) -> OrderImportService:
    """Build the same OrderImportService the import script builds."""
    client = build_allegro_client(db)
    return OrderImportService(
        OrderRepository(db),
        AllegroAdapter(client=client),
        credentials=IntegrationCredentialRepository(db),
        initial_days=settings.allegro_initial_import_days,
    )
