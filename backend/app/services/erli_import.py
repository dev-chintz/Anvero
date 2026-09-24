"""Wiring an Erli import: the adapter, and where its sync point is kept."""

import hashlib

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.base import IntegrationNotConfigured
from app.integrations.erli import ErliAdapter
from app.integrations.erli.client import ErliClient
from app.models.order import OrderSource
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.order_repository import OrderRepository
from app.services.order_import_service import OrderImportService

PROVIDER = OrderSource.ERLI.value


def build_erli_import_service(db: Session, client: ErliClient | None = None) -> OrderImportService:
    """Build the import service for the Erli shop whose key is configured.

    Erli's key does not rotate, so nothing is stored for it; but the sync
    point and the last import's outcome live on an `integration_credentials`
    row, which is made here, holding only a fingerprint of the key (never the
    key). A different key may be another shop, so it starts the sync over,
    exactly as a re-authorization does for Allegro.
    """
    client = client or ErliClient()
    if not client.is_configured:
        raise IntegrationNotConfigured("ERLI_API_KEY is not set")
    credentials = IntegrationCredentialRepository(db)
    fingerprint = hashlib.sha256(client.api_key.encode()).hexdigest()
    credentials.save(PROVIDER, refresh_token="", seed_fingerprint=fingerprint)
    return OrderImportService(
        OrderRepository(db),
        ErliAdapter(client=client),
        credentials=credentials,
        initial_days=settings.erli_initial_import_days,
    )
