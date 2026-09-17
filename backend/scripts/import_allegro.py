#!/usr/bin/env python3
"""Import orders from Allegro into Anvero.

Usage:
    python scripts/import_allegro.py [--limit N] [--offset N]

The client id and secret come from the environment. The refresh token is
seeded from the environment too, but Allegro replaces it on every use, so the
current one is kept in the database; see docs/INTEGRATIONS.md.

This is a script rather than an HTTP endpoint on purpose: the orders
endpoints carry no authentication yet, so an unauthenticated route that makes
outbound calls to a third party would be an obvious thing to abuse.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.integrations.allegro import AllegroAdapter
from app.integrations.allegro.client import MAX_PAGE_SIZE, AllegroClient
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.models.order import OrderSource
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.repositories.order_repository import OrderRepository
from app.services.order_import_service import OrderImportService
from app.services.refresh_token_store import DatabaseRefreshTokenStore

logger = logging.getLogger(__name__)


def _page_size(value: str) -> int:
    size = int(value)
    if not 1 <= size <= MAX_PAGE_SIZE:
        raise argparse.ArgumentTypeError(
            f"must be between 1 and {MAX_PAGE_SIZE}; Allegro rejects larger pages"
        )
    return size


def _offset(value: str) -> int:
    offset = int(value)
    if offset < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return offset


def main() -> int:
    parser = argparse.ArgumentParser(description="Import orders from Allegro")
    parser.add_argument(
        "--limit",
        type=_page_size,
        default=MAX_PAGE_SIZE,
        help=f"orders per page, 1-{MAX_PAGE_SIZE} (default {MAX_PAGE_SIZE})",
    )
    parser.add_argument(
        "--offset", type=_offset, default=0, help="skip this many orders"
    )
    args = parser.parse_args()

    setup_logging()

    db = SessionLocal()
    try:
        # Allegro rotates the refresh token on every use, so the rotated one is
        # kept in the database for the next run rather than read from .env
        token_store = DatabaseRefreshTokenStore(
            IntegrationCredentialRepository(db),
            provider=OrderSource.ALLEGRO.value,
            configured_token=settings.allegro_refresh_token,
        )
        client = AllegroClient(token_store=token_store)
        service = OrderImportService(OrderRepository(db), AllegroAdapter(client=client))
        result = service.import_orders(limit=args.limit, offset=args.offset)
    except IntegrationNotConfigured as exc:
        print(f"Allegro is not configured: {exc}", file=sys.stderr)
        return 2
    except IntegrationAuthError as exc:
        print(f"Allegro refused the credentials: {exc}", file=sys.stderr)
        return 3
    except IntegrationError as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created {result.created}, updated {result.updated}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
