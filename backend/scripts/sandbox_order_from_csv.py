#!/usr/bin/env python3
"""Buy the offers listed in an import CSV on the Allegro Sandbox, to make orders.

Usage (from backend/, with the venv):

    .\\.venv\\Scripts\\python.exe scripts\\sandbox_order_from_csv.py FILE.csv --dry-run
    .\\.venv\\Scripts\\python.exe scripts\\sandbox_order_from_csv.py FILE.csv \\
        --buyer-email buyer@example.com [--orders-per-offer 2] [--show]

FILE.csv is the file that was used to list the offers ("import and list" CSV);
only its EXTERNAL_ID (and NAME) columns are read. Each EXTERNAL_ID is looked up
among the connected seller's own offers with `GET /sale/offers?external.id=`,
using the Allegro account connected in Anvero (Settings), to find the offer's
page on the Sandbox. Then, as a separate BUYER account, one purchase per offer
(or `--orders-per-offer`) is made by driving the browser exactly as
`sandbox_bulk_purchase.py` does, which this script reuses: install Playwright
as described there, and read its warnings, which apply here too.

`--dry-run` only does the lookup and prints what would be bought, so it needs
no Playwright and no buyer account. Do it first: it also shows which listings
did not become active offers (a CSV import is processed by Allegro afterwards
and may reject rows).

Safety:
- Refuses to run unless Anvero's Allegro connection is the Sandbox one, and
  only ever opens Sandbox pages: it must never place a real order.
- The seller cannot buy their own offers, so the buyer must be another Sandbox
  account. The password is asked for in the terminal and is not stored.

Not verified against Allegro: written from the documentation. That
`external.id` matches the CSV's EXTERNAL_ID, that the listing call is allowed
by the application's scopes, and the whole buying flow (see
`sandbox_bulk_purchase.py`) are untried. With `--offers-file` (one offer URL or
id per line) the lookup is skipped, if it does not work.
"""

import argparse
import csv
import getpass
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SANDBOX_URL = "https://allegro.pl.allegrosandbox.pl"
# how many external ids one lookup asks about
LOOKUP_BATCH = 20


@dataclass(frozen=True)
class Listing:
    external_id: str
    name: str


@dataclass(frozen=True)
class Offer:
    external_id: str | None
    name: str
    url: str


def read_listings(path: Path) -> list[Listing]:
    """The EXTERNAL_ID and NAME of every row of an import CSV, in file order."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "EXTERNAL_ID" not in reader.fieldnames:
            raise ValueError(f"{path} has no EXTERNAL_ID column; is it an import CSV?")
        listings = []
        seen = set()
        for row in reader:
            external_id = (row.get("EXTERNAL_ID") or "").strip()
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)
            listings.append(Listing(external_id, (row.get("NAME") or "").strip()))
    return listings


def offer_url(offer_id: str) -> str:
    return f"{SANDBOX_URL}/oferta/{offer_id}"


def read_offers_file(path: Path) -> list[Offer]:
    """Offers named by hand: one Sandbox offer URL or numeric id a line."""
    offers = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.isdigit():
            text = offer_url(text)
        if not text.startswith(SANDBOX_URL):
            raise ValueError(f"not a Sandbox offer: {text}")
        offers.append(Offer(None, text, text))
    return offers


def find_offers(client, listings: list[Listing]) -> tuple[list[Offer], list[Listing]]:
    """Look the listings up among the seller's active offers.

    Returns the offers found, and the listings with no active offer (not
    imported yet, rejected, ended). The first active offer wins when several
    share an external id.
    """
    found: dict[str, Offer] = {}
    for start in range(0, len(listings), LOOKUP_BATCH):
        batch = listings[start : start + LOOKUP_BATCH]
        for raw in client.fetch_offers_by_external_id([item.external_id for item in batch]):
            external = raw.get("external")
            external_id = external.get("id") if isinstance(external, dict) else None
            offer_id = raw.get("id")
            if not isinstance(external_id, str) or not isinstance(offer_id, str):
                continue
            found.setdefault(
                external_id, Offer(external_id, str(raw.get("name") or ""), offer_url(offer_id))
            )
    offers = [found[item.external_id] for item in listings if item.external_id in found]
    missing = [item for item in listings if item.external_id not in found]
    return offers, missing


def _sandbox_client_or_exit():
    from app.db.session import SessionLocal
    from app.services import allegro_settings
    from app.services.allegro_import import build_allegro_client

    db = SessionLocal()
    application = allegro_settings.resolve_application(db)
    if application.environment != "sandbox":
        print(
            "Anvero's Allegro connection is not the Sandbox one. This script "
            "buys things, so it refuses to run against anything else.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    client = build_allegro_client(db)
    if not client.is_configured:
        print("Allegro is not connected (Settings); nothing to look offers up with.", file=sys.stderr)
        raise SystemExit(2)
    return client


def _buy(offers: list[Offer], email: str, per_offer: int, delay: float, show: bool) -> int:
    # imported only now: it needs Playwright, which a dry run does not
    import sandbox_bulk_purchase as buying
    from playwright.sync_api import sync_playwright

    password = getpass.getpass("Sandbox buyer password: ")
    total = len(offers) * per_offer
    done = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not show)
        page = browser.new_page()
        try:
            buying._log_in(page, email, password)
        except buying.PlaywrightTimeoutError as exc:
            print(f"Login failed: {exc}\nCurrent page: {page.url}", file=sys.stderr)
            page.screenshot(path="login-failure.png")
            browser.close()
            return 1

        number = 0
        for offer in offers:
            for _ in range(per_offer):
                number += 1
                label = offer.external_id or offer.url
                try:
                    buying._buy_once(page, offer.url)
                    done += 1
                    print(f"[{number}/{total}] bought {label}")
                except buying.PlaywrightTimeoutError as exc:
                    print(f"[{number}/{total}] failed {label}: {exc}", file=sys.stderr)
                    page.screenshot(path=f"failure-{number}.png")
                time.sleep(delay)
        browser.close()

    print(f"{done}/{total} purchases completed.")
    return 0 if done == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Buy the offers of an import CSV on the Allegro Sandbox, to make test orders."
    )
    parser.add_argument("csv", type=Path, help="the CSV the offers were listed from")
    parser.add_argument("--buyer-email", help="the Sandbox BUYER account (not the seller's)")
    parser.add_argument("--orders-per-offer", type=int, default=1, help="purchases per offer (default 1)")
    parser.add_argument("--only", nargs="+", metavar="EXTERNAL_ID", help="only these listings")
    parser.add_argument("--offers-file", type=Path, help="skip the lookup: a file of offer URLs or ids")
    parser.add_argument("--dry-run", action="store_true", help="look the offers up and list them; buy nothing")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between purchases (default 2)")
    parser.add_argument("--show", action="store_true", help="show the browser window")
    args = parser.parse_args()

    if not 1 <= args.orders_per_offer <= 50:
        parser.error("--orders-per-offer must be between 1 and 50")
    if not args.dry_run and not args.buyer_email:
        parser.error("--buyer-email is required unless --dry-run")

    if args.offers_file:
        offers, missing = read_offers_file(args.offers_file), []
    else:
        listings = read_listings(args.csv)
        if args.only:
            listings = [item for item in listings if item.external_id in set(args.only)]
        if not listings:
            print("No listings to look up.", file=sys.stderr)
            return 1
        offers, missing = find_offers(_sandbox_client_or_exit(), listings)

    for offer in offers:
        print(f"{offer.external_id or '-':<16} {offer.url}  {offer.name[:50]}")
    for item in missing:
        print(f"{item.external_id:<16} NO ACTIVE OFFER  {item.name[:50]}", file=sys.stderr)
    print(f"{len(offers)} offers found, {len(missing)} without an active offer.")

    if args.dry_run or not offers:
        return 0 if offers else 1
    return _buy(offers, args.buyer_email, args.orders_per_offer, args.delay, args.show)


if __name__ == "__main__":
    raise SystemExit(main())
