#!/usr/bin/env python3
"""Buy the same Allegro Sandbox offer many times, to generate test orders.

Usage:
    pip install playwright
    playwright install chromium
    python scripts/sandbox_bulk_purchase.py OFFER_URL --email buyer@example.com --count 25

Standalone testing tool, not part of the app - Playwright is deliberately
not in requirements.txt, since nothing else needs it.

There is no bulk-purchase API: buying is a buyer-only web action (Allegro's
own Sandbox guide, developer.allegro.pl, "Zamowienia" tutorial, "Sandbox"
section - list the offer as the seller, then as the buyer: open the offer,
Buy Now, fill delivery details, pay through the Sandbox's payment simulator).
This script drives that same flow N times in one browser session (one
login, not one per purchase) to create N separate orders for Anvero's
import to page through, rather than testing against a single hand-made one.

IMPORTANT - this has not been run against the real page: no Sandbox buyer
credentials were available while writing it, so every button/field below is
a best guess at Allegro's Polish UI text, using Playwright's role/label
locators (resilient to layout changes, but not to wrong text). Before a
real run:

    python scripts/sandbox_bulk_purchase.py OFFER_URL --email ... --count 1 --show

Watch it with the browser visible. Whichever step it stalls on, open that
page by hand, check the actual button/field text or add a data-testid-based
locator instead, and fix that one line - the rest of the flow is unlikely to
need changes. A stuck step prints the page's URL and saves a screenshot
next to this script (failure-N.png) so a fix does not need a second run to
see what went wrong.

Two things this cannot get past on its own: a 2FA/SMS prompt on login, and
a CAPTCHA - if the Sandbox buyer account has either enabled, log in by hand
once with --show and let the script take over after that (not implemented
here, since it depends on which one the account has).
"""

import argparse
import getpass
import sys
import time

try:
    from playwright.sync_api import Page, sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
    print(
        "Playwright is not installed (this script is standalone; see its "
        "docstring):\n    pip install playwright\n    playwright install chromium",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

SANDBOX_URL = "https://allegro.pl.allegrosandbox.pl"
LOGIN_URL = f"{SANDBOX_URL}/login"

# Sandbox invents no real shipment, so any well-formed Polish address is
# enough to complete a checkout - used only if the account has no saved
# address for Allegro to offer instead.
TEST_ADDRESS = {
    "first_name": "Jan",
    "last_name": "Testowy",
    "street": "Testowa 1",
    "postal_code": "00-001",
    "city": "Warszawa",
    "phone": "500100200",
}

# Guesses, in the order a step is likely to offer them; the first match
# wins, and none matching is not an error - see the docstrings below.
NEXT_STEP_BUTTON_LABELS = ("Dalej", "Przejdź do płatności", "Przejdź dalej")
PAY_CONFIRM_BUTTON_LABELS = (
    "Symuluj płatność",
    "Zapłacono",
    "Potwierdź płatność",
    "Zapłać",
)
COOKIE_BANNER_BUTTON_LABELS = ("Akceptuję", "Zaakceptuj wszystkie", "Zgadzam się")


def _click_first_match(page: Page, labels: tuple[str, ...], timeout: int = 3000) -> str | None:
    """Click the first of these buttons that actually appears; return which."""
    for label in labels:
        try:
            page.get_by_role("button", name=label).click(timeout=timeout)
            return label
        except PlaywrightTimeoutError:
            continue
    return None


def _dismiss_cookie_banner(page: Page) -> None:
    _click_first_match(page, COOKIE_BANNER_BUTTON_LABELS, timeout=2000)


def _log_in(page: Page, email: str, password: str) -> None:
    page.goto(LOGIN_URL)
    _dismiss_cookie_banner(page)
    page.get_by_label("E-mail lub login").fill(email)
    page.get_by_role("button", name="Dalej").click()
    page.get_by_label("Hasło").fill(password)
    page.get_by_role("button", name="Zaloguj się").click()
    page.wait_for_load_state("networkidle")


def _fill_delivery_address_if_asked(page: Page) -> None:
    """A saved address may be offered instead of a blank form; only fill
    one in if the form actually appears."""
    try:
        page.get_by_label("Imię").fill(TEST_ADDRESS["first_name"], timeout=3000)
    except PlaywrightTimeoutError:
        return

    page.get_by_label("Nazwisko").fill(TEST_ADDRESS["last_name"])
    page.get_by_label("Ulica i numer").fill(TEST_ADDRESS["street"])
    page.get_by_label("Kod pocztowy").fill(TEST_ADDRESS["postal_code"])
    page.get_by_label("Miejscowość").fill(TEST_ADDRESS["city"])
    page.get_by_label("Telefon").fill(TEST_ADDRESS["phone"])


def _buy_once(page: Page, offer_url: str) -> None:
    page.goto(offer_url)
    _dismiss_cookie_banner(page)
    page.get_by_role("button", name="Kup teraz").click()

    _fill_delivery_address_if_asked(page)

    # delivery and payment method: Allegro pre-selects a default for each,
    # so only "next"-style buttons need clicking between them
    while _click_first_match(page, NEXT_STEP_BUTTON_LABELS) is not None:
        pass

    page.get_by_role("button", name="Kupuję i płacę").click()

    # the Sandbox payment simulator: stands in for a real bank/card form,
    # with its own button to mark the payment completed
    clicked = _click_first_match(page, PAY_CONFIRM_BUTTON_LABELS, timeout=5000)
    if clicked is None:
        raise PlaywrightTimeoutError(
            "no known payment-confirmation button matched on "
            f"{page.url} - open it by hand to find the real label"
        )

    page.wait_for_load_state("networkidle")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Buy an Allegro Sandbox offer repeatedly to generate test orders."
    )
    parser.add_argument(
        "offer_url",
        help="The Sandbox offer's own page, e.g. https://allegro.pl.allegrosandbox.pl/oferta/...",
    )
    parser.add_argument(
        "--email", required=True, help="The Sandbox BUYER account's login/email (not the seller's)"
    )
    parser.add_argument(
        "--count", type=int, default=20, help="How many separate orders to create (default: 20)"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Seconds to wait between purchases (default: 2)"
    )
    parser.add_argument(
        "--show", action="store_true", help="Run with a visible browser window instead of headless"
    )
    args = parser.parse_args()

    password = getpass.getpass("Sandbox buyer password: ")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.show)
        page = browser.new_page()

        try:
            _log_in(page, args.email, password)
        except PlaywrightTimeoutError as exc:
            print(f"Login failed: {exc}\nCurrent page: {page.url}", file=sys.stderr)
            page.screenshot(path="login-failure.png")
            browser.close()
            return 1

        succeeded = 0
        for i in range(1, args.count + 1):
            try:
                _buy_once(page, args.offer_url)
                succeeded += 1
                print(f"[{i}/{args.count}] bought")
            except PlaywrightTimeoutError as exc:
                print(f"[{i}/{args.count}] failed: {exc}", file=sys.stderr)
                page.screenshot(path=f"failure-{i}.png")
            time.sleep(args.delay)

        browser.close()

    print(f"{succeeded}/{args.count} purchases completed.")
    return 0 if succeeded == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())
