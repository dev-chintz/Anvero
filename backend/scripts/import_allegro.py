#!/usr/bin/env python3
"""Import orders from Allegro into Anvero.

Usage:
    python scripts/import_allegro.py [--days N]

The first run fetches orders bought in the last ALLEGRO_INITIAL_IMPORT_DAYS
(default 7); every later run fetches only orders new or changed since the last
one that finished, all pages of them. `--days N` ignores that recorded point
and fetches orders bought in the last N days instead (a backfill); the
recorded point still moves forward afterwards.

The client id and secret come from the environment. The refresh token is
seeded from the environment too, but Allegro replaces it on every use, so the
current one is kept in the database; see docs/INTEGRATIONS.md.

This still exists alongside `POST /integrations/allegro/import`, which uses
the same wiring (app/services/allegro_import.py); see DECISIONS.md.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.services.allegro_import import build_allegro_import_service

logger = logging.getLogger(__name__)


def _days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= 365:
        raise argparse.ArgumentTypeError("must be between 1 and 365")
    return days


def main() -> int:
    parser = argparse.ArgumentParser(description="Import orders from Allegro")
    parser.add_argument(
        "--days",
        type=_days,
        default=None,
        help="fetch orders bought in the last N days, ignoring the recorded sync point",
    )
    args = parser.parse_args()

    setup_logging()

    db = SessionLocal()
    try:
        # same wiring the /integrations/allegro/import endpoint uses, so both
        # read and rotate the one stored refresh token; see
        # app/services/allegro_import.py
        service = build_allegro_import_service(db)
        result = service.sync_orders(days=args.days)
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
    if result.cancellation_warnings:
        print(
            f"WARNING: {result.cancellation_warnings} order(s) were cancelled on "
            "Allegro but are still active in Anvero. Check them before shipping: "
            "Orders page, 'cancelled on marketplace' filter."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
