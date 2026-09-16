#!/usr/bin/env python3
"""Import orders from Allegro into Anvero.

Usage:
    python scripts/import_allegro.py [--limit N] [--offset N]

Credentials come from the environment; see docs/INTEGRATIONS.md for the
one-time authorization that produces the refresh token.

This is a script rather than an HTTP endpoint on purpose: the orders
endpoints carry no authentication yet, so an unauthenticated route that makes
outbound calls to a third party would be an obvious thing to abuse.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.integrations.allegro import AllegroAdapter
from app.integrations.allegro.client import MAX_PAGE_SIZE
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.repositories.order_repository import OrderRepository
from app.services.order_import_service import OrderImportService

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
        service = OrderImportService(OrderRepository(db), AllegroAdapter())
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
