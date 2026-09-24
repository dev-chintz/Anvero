#!/usr/bin/env python3
"""Import orders from Erli into Anvero.

Usage:
    python scripts/import_erli.py [--days N]

The first run fetches orders placed in the last ERLI_INITIAL_IMPORT_DAYS
(default 7); every later run fetches only orders new or changed since the last
one that finished, all pages of them. `--days N` ignores that recorded point
and fetches orders placed in the last N days instead (a backfill).

The API key comes from ERLI_API_KEY in backend/.env; see docs/INTEGRATIONS.md.
Built from Erli's documentation and not yet run against the real service.
"""

import argparse
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
from app.services.erli_import import PROVIDER as ERLI_PROVIDER
from app.services.erli_import import build_erli_import_service
from app.services.import_outcome import run_and_record


def _days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= 365:
        raise argparse.ArgumentTypeError("must be between 1 and 365")
    return days


def main() -> int:
    parser = argparse.ArgumentParser(description="Import orders from Erli")
    parser.add_argument(
        "--days",
        type=_days,
        default=None,
        help="fetch orders placed in the last N days, ignoring the recorded sync point",
    )
    args = parser.parse_args()

    setup_logging()

    db = SessionLocal()
    try:
        # noted, so the status page shows how it ended
        result = run_and_record(
            db,
            ERLI_PROVIDER,
            lambda: build_erli_import_service(db).sync_orders(days=args.days),
        )
    except IntegrationNotConfigured as exc:
        print(f"Erli is not configured: {exc}", file=sys.stderr)
        return 2
    except IntegrationAuthError as exc:
        print(f"Erli refused the API key: {exc}", file=sys.stderr)
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
            "Erli but are still active in Anvero. Check them before shipping."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
