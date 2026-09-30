#!/usr/bin/env python3
"""Classify the orders paid in a period for the non-invoiced sales record, and print the counts.

Usage:
    python scripts/classify_non_invoiced.py [--from YYYY-MM-DD] [--to YYYY-MM-DD]

By default the previous month. Prints how many orders fall in each category and reason, and the
sum of the ones in the report; never a buyer's name or anything else personal. Reads only: it
changes nothing and does not call Allegro, so it can run beside a running import, on the NAS too
(`docker exec <backend container> python scripts/classify_non_invoiced.py`). Stage 2 of
docs/NON_INVOICED_SALES.md: the counts are looked at before anything uses them.
"""

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.non_invoiced.classifier import REASON_TEXT, RULESET, Category
from app.services.non_invoiced.run import classify_paid_between, counts


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _previous_month(today: date) -> tuple[date, date]:
    first_of_this = today.replace(day=1)
    last_of_previous = first_of_this - timedelta(days=1)
    return last_of_previous.replace(day=1), last_of_previous


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify the orders paid in a period")
    parser.add_argument("--from", dest="start", type=_day, help="first day, inclusive (default: the previous month)")
    parser.add_argument("--to", dest="end", type=_day, help="last day, inclusive")
    args = parser.parse_args()

    zone = ZoneInfo(settings.business_timezone)
    default_start, default_end = _previous_month(datetime.now(zone).date())
    start, end = args.start or default_start, args.end or default_end
    # the business's own calendar days, as UTC bounds
    paid_from = datetime.combine(start, datetime.min.time(), zone).astimezone(UTC)
    paid_to = datetime.combine(end + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC)

    db = SessionLocal()
    try:
        classified = classify_paid_between(db, paid_from, paid_to)
    finally:
        db.close()

    by_category, by_reason = counts(classified)
    in_report = [c for c in classified if c.classification.in_report]
    total = sum((c.order.paid_amount or Decimal("0")) for c in in_report)
    print(f"Paid {start} to {end} ({settings.business_timezone}), rules {RULESET}: {len(classified)} orders")
    for category in Category:
        if not by_category[category]:
            continue
        print(f"\n{category.value}: {by_category[category]}")
        for (cat, reason), count in sorted(by_reason.items(), key=lambda item: -item[1]):
            if cat is category:
                print(f"  {count:5}  {reason.value}: {REASON_TEXT[reason]}")
    print(f"\nIn the report: {len(in_report)} orders, {total} PLN paid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
