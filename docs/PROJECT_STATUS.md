# PROJECT STATUS

## Project

Anvero

Modern Business Management Platform

---

## Version

0.1.0

---

## Status

Foundation

---

## Current Sprint

Sprints 2, 3 and 4 are delivered. PostgreSQL is connected on the main
machine: the migrations and the full test suite run on it. The Allegro
import first ran against the real API in the Allegro Sandbox; since
2026-09-25 both Allegro and Erli are connected on the owner's real,
production accounts and import real orders (and, for Allegro, buyer
messages) - see "Not yet verified" below for what that has and has not
covered.

Since 2026-09-18 the development database is one shared PostgreSQL 17 on the
owner's NAS, which every machine reaches through `DATABASE_URL` in its own
`.env` (`DEVELOPMENT.md`, "Shared database on the NAS"; `DECISIONS.md`). A
machine that has not been pointed at it still runs on its own SQLite file.
Nightly dumps are kept on the NAS, copied daily to an encrypted Google Drive
folder, and one was restored from that copy into a scratch database as a test.

---

## Sprint 2 — Working Skeleton

- Backend framework selection and configuration — done (FastAPI)
- Connection to local PostgreSQL database — done (PostgreSQL 17.10; SQLite
  remains the no-setup default for a fresh clone)
- Health endpoint and first order model — done
- Minimal order list interface — done
- Automated tests for core flows — done (1352 backend, 764 frontend passing
  across the suite as of 2026-10-01, the backend on SQLite, where one more
  fails on a machine not in UTC: see "Not yet verified")

---

## Sprint 3 — Order Flow

- Order list and details — done, including items, buyer, delivery and
  pickup point, payment and invoice (MVP item 3)
- Filtering by source, status and date — done
- Change history — done (status transitions and who made them)
- Sample data — done (`backend/scripts/generate_sample_data.py --force`)

---

## Sprint 4 — First Integration

- Secure credential configuration — done (environment only, `.env` ignored)
- Allegro adapter — done, built from Allegro's published documentation
- Order import and mapping — done (`backend/scripts/import_allegro.py`,
  `POST /api/v1/integrations/allegro/import` and an "Import from Allegro"
  button, both using the same wiring as the script)
- Error handling and logging — done

Run against the Allegro Sandbox on 2026-09-17: a real order was imported and
re-imported. Production needs its own application and authorization; see
`INTEGRATIONS.md`.

---

## Also completed

- Project name and branding direction
- Repository structure, local Git repository, GitHub remote
- Login (MVP item 1): login page, every orders endpoint and page protected,
  accounts created by script, 8-hour tokens, signing key enforced
- Rate limiting on the login endpoint (5/minute per IP)
- Order status editing via `PATCH /orders/{id}/status`
- Dashboard aggregates computed in SQL (`GET /orders/stats`)
- Unique constraint on `(source, external_id)`, so an import is safe to re-run
- Allegro import as an endpoint and a button, one import at a time, rate
  limited
- The marketplace's own status kept beside the operator's and shown, in the
  marketplace's own words, when they differ (`marketplace_status`,
  `marketplace_status_label`)
- Dark mode
- VS Code configuration and development scripts
- Initial Figma dashboard prototype (not followed yet; kept for the visual
  pass planned after the system runs unattended, see `ROADMAP.md`)

---

## Not yet verified

The Help page (2026-10-01, `GUIDE.md`, `GDPR.md`): the guide, the GDPR tab, the
controller card in Settings and `GET /gdpr/overview` and `PUT /gdpr/controller` are
tested (the endpoints against the permission rules, the guide against the application's
routes, menu and Settings tabs, the notice and the register against the retention
periods), and the Help page was drawn by headless Chrome on a scratch database for
the screenshots of 2026-10-01 (its GDPR tab among them, with a made-up controller). It
has not been opened behind the owner's login, the controller card has not been used in
a browser, and no controller's details have been entered on the NAS, so there the
notice still shows its `[uzupełnij: ...]` gaps. `tools/guide/make.ps1` was not run
again when the branch was merged: the screenshots are as made on 2026-10-01, and
nobody has yet compared the guide's sentences with the live screens. The notice to
buyers and the register are drafts no lawyer has seen (the tab lists what is theirs to
settle). No migration (`gdpr_controller` is a row of `app_settings`).

A known failure, found 2026-10-01 on a machine in UTC+2 on SQLite and not on this
branch's code: `tests/services/test_catalog.py::test_the_first_sync_keeps_every_offer_with_its_category_and_pictures`
reads `last_seen_at` back without its zone and `.astimezone(UTC)` takes it for local
time (10:00 for 12:00 UTC). Not run on PostgreSQL or on a machine in UTC; the order import
test that did the same was fixed with `_as_utc` on 2026-09-24.

The assortment (2026-10-01, `CATALOG.md`): built from Allegro's and Erli's published descriptions, tested against fakes (161 backend and 61 frontend tests), and seen in a browser on a scratch database with made-up offers and pictures, in both looks and modes; the backend tests ran on SQLite only (the main machine's PostgreSQL run of the suite is still to do); never read from the real services. To check on the first sync (the button on the page, on a machine with the real Allegro connection, after `alembic upgrade head`): that the application has the scope `allegro:api:sale:offers:read` (a refusal is shown on the page); that the offers and their pictures arrive and the pictures are stored; how many of Erli's products are tied to an offer and by what (`EXTERNAL_REFERENCE`, `EXTERNAL_ID`, `SKU`) or not at all, and whether the "different category" ones are real differences. The cost of making a piece and the margin (2026-10-01): tested (backend and page), and used in a browser on a scratch
database (a cost typed in, kept, the margin worked out again, an invalid one refused, Enter going on to the next
field); the costs themselves are the owner's to enter, and the margin is only as good as they are. After pulling this, run
`alembic upgrade head` (migration `e8c3b7f1a926`). What each offer sold and what is left after the fees (2026-10-01) is the Finance page's arithmetic, tested, and seen in a browser on made-up orders (the figures checked by hand); not yet compared with the real orders: pick one product and check its pieces and its fees against the order page and Finance. An Erli offer shows Erli sales only once the Erli product is tied to it. How long a first read takes is not known (the first attempt, as one request, outlasted the proxy's 300 seconds; it now runs in the background with a progress bar, seen in a browser with a made-up state, never over a real read). On the NAS the backend still needs the mounted folder for the pictures (`DEPLOYMENT.md`, "The assortment's pictures").

The non-invoiced record's reports, exports and screen (2026-10-01, stages 4 and
5 of `NON_INVOICED_SALES.md`): tested, and seen in a browser on a scratch
database with made-up rows; not yet on the real ledger, and no report handed
over for real. September was compared with the old report on 2026-10-01 and
every difference explained (stage 6 in `NON_INVOICED_SALES.md`); still to do
before it goes to the accountant: confirm that the 13 private buyers who asked
for an invoice got one, let the NAS's first import after the update classify
the 6 Erli sales, and compare the total with Allegro's payout report.

Erli's payments for the non-invoiced record (2026-10-01): built from Erli's API
description, tested against fakes, never read from the real service. The first
import after the update should store `CONTRIBUTION` and `PAYOUT` operations of
source `ERLI`, give the Erli orders their payment ids, and move the eleven Erli
sales out of `TO_REVIEW`.

The Users and Updates tabs (2026-10-01): tested, not yet opened in a browser
(the owner's login), nor an account saved or an update installed since.

The status tab (2026-10-01): tested; seen in a browser on a scratch database on
2026-10-01, which showed the tiles' titles cut off by the card's edge (fixed); not yet
opened with the owner's login.

The InPost lockers tab (2026-09-30): tested, not yet opened in a browser (the
owner's login), nor a parcel created from it since the change.

The settings page (2026-09-30): tested, its new pieces seen on the real
stylesheets, the page itself not yet opened in a browser (the owner's login).

Payment trace for the non-invoiced sales record (2026-09-30, stage 1 of
`NON_INVOICED_SALES.md`): first run on the real account 2026-09-30, the NAS on
`f595bd4`, one import (15:45 UTC, no error). Seen working: `payment_operations`
filled back to 1 August, the previous month's start as the code does (827 rows:
365 `CONTRIBUTION`, every one with a payment id, 403 `DEDUCTION_CHARGE`, 39
`PAYOUT`, 18 `REFUND_CHARGE`, 2 `SURCHARGE`); `orders.payment_id` on 108 of the
234 orders since 1 September, the rest left to the next imports' backfill of
100; `delivery_method_id` on all 108, `invoice.address.company` on 16.
**Not seen: `tax`.** `order_items.tax_rate` and `tax_subject` are empty on all
516 items of the orders read again - either Allegro sends no `tax` for this
account or the mapper reads the wrong place; needs one raw response to tell.
Then the classifier (stage 2): `python scripts/classify_non_invoiced.py` in the
backend container prints September's counts by category and reason, to be
looked at with the owner before anything uses them.
Then the ledger (stage 3, 2026-09-30): first written by that same import, 233
rows, none locked. Sales: 88 `EXEMPT_MAIL_ORDER` (E41), 20 `BUSINESS`, 14
`PRIVATE_INVOICED`, 105 `TO_REVIEW` (92 `MISSING_BUYER_DATA`, every one an
order not yet given its payment id by the backfill, so expected to shrink over
the next imports; 11 `SOURCE_NOT_SUPPORTED`; 2 `CANCELLED_AFTER_PAYMENT`).
Refunds became corrections (4 E41, 2 `TO_REVIEW`). Still to check: that the
`TO_REVIEW` count falls once the backfill ends, that September's rows match the
classifier's counts, and above all that the payout each payment was linked to
(`payout_link` `FIRST_AFTER`, an approximation; 83 of the 88 E41 sales have one)
agrees with the payout report Allegro's Sales Center exports. The three
migrations of 2026-09-30 (`a9c4e7d2b815`, `c7e2a9f4d318`, `e3b7a1c9d524`) ran
on the NAS's PostgreSQL without error.
Checked again on 2026-10-01 (counts only, read-only, from the shared
database): the backfill has ended, 205 of 215 orders since 1 September have a
payment id and no `MISSING_BUYER_DATA` row is left. September holds 174
`EXEMPT_MAIL_ORDER` sales (8 168,48 zł gross) and 5 of their refunds
(−194,09 zł), 19 `BUSINESS`, 13 `PRIVATE_INVOICED`, and `TO_REVIEW` only 2
Allegro sales cancelled after payment (each with its refund) and 6 Erli sales
(`SOURCE_NOT_SUPPORTED`; 5 more in August). Every E41 sale now has a payout
(`FIRST_AFTER`), still unchecked against Allegro's payout report; no row is
locked. `order_items.tax_rate` is still empty on all 1 155 items. What remains
of the plan is stage 4 onward (`NON_INVOICED_SALES.md`, section 5): no report,
export or handing over reads the ledger yet, so the only export is still the
old report's CSV.

The new logo (2026-09-30): seen on the login page in light and dark; the menu,
behind the login, not yet.

`SECRETS_KEY` on the NAS (2026-09-30): not confirmed set; without it the
Allegro and InPost tokens are plain text in the database and its backups
(`DECISIONS.md`, "Security audit").

The Papier look (2026-09-30): tested, seen on the login page in light and dark;
the pages behind the login not yet looked at in Papier.

Colours as variables (2026-09-30): checked by script and on the login page in
both modes; the pages behind the login not yet looked at in dark mode, where
seven accent buttons now have dark text instead of white (`DECISIONS.md`).

The finance page's layout (2026-09-30): tested, not yet opened in a browser
(the owner's login).

Returns and claims (2026-09-30): tested, not yet opened in a browser (the
owner's login). The inbox's row height fix was checked on the real stylesheet
in a browser (a row 229px before, 58px after), not on the live page.

The labels page (2026-09-30): tested, not yet opened in a browser (the owner's
login), nor a courier ordered or labels printed since the change.

The to-make list (2026-09-30): tested, not yet opened in a browser (the owner's
login), nor printed since the change.

The inbox (2026-09-30): tested, not yet opened in a browser (the owner's
login); in particular the buyer's orders over a conversation with a real nick.

The dashboard (2026-09-29): tested, not yet opened in a browser (the owner's
login), with and without anything needing attention.

The order list and the tinted status chips (2026-09-29): tested, not yet opened
in a browser (the owner's login). Worth a look at about 1080px wide and in dark
mode, where the chips use the tones' dark values.

The order page in two columns (2026-09-29): tested, not yet opened in a browser
(it needs the owner's login). Worth a look at about 1080px wide (a monitor
turned upright), and below 900px where the columns stack.

Update history and progress (2026-09-29): tested with fakes only. The first real
check is the update after the one that installs this code on the NAS: the
dialog's steps and bar, the application inert meanwhile, and the history row
closed by the new backend.

Order page summary redesign (2026-09-29): not yet opened in a browser. To
check, logged in by the owner: a Smart and a non-Smart order, one with no
parcel and one with a parcel (the shipping form folded behind "+ Dodaj
kolejną przesyłkę"), light and dark mode, and the Smart badge in the order
list. Existing orders show no Smart badge until an import refreshes them, and
whether Allegro really sends `delivery.smart: true` on a Smart order is taken
from its documentation, not yet seen in a response.

CI's `alembic check` failed on PostgreSQL from `b0bf5ee` (2026-09-28) until
`2f55e98`: `UserPermission.id` declared an index no migration made. So no image
was published for `b0bf5ee`, `b196796` or `716c908`, and the NAS's `latest` is
still `6c31ea1`. The next green push publishes all of it at once.

GDPR (2026-09-28, `GDPR.md`): retention, the per-buyer scripts and secret
encryption were tested against fakes and on SQLite and PostgreSQL test
databases, the scripts run against a development database with nothing to
erase, and `encrypt_secrets.py` run against a copy of one with seeded secrets.
Not yet run on the NAS against the real orders and messages: the first daily
run there will erase message threads quiet for over two years, if Allegro's
history holds any, and closed cases opened that long ago. `SECRETS_KEY` is not
set on the NAS, so its secrets stay plain text until the owner sets it
(`DEPLOYMENT.md`). The anonymized-order banner and the search kept out of the
address were checked by the frontend tests, not yet in a browser.

Verified against the Allegro Sandbox on 2026-09-17, on the SQLite machine:
the authorization script completed a real device flow authorization of the
sandbox seller account, and `scripts/import_allegro.py` imported a real
sandbox order twice — created once, updated on the second run, with the
stored refresh token replaced between the runs. The mapping matched the real
payload: status `NEW`, buyer login and email, total `45.49 PLN` equal to the
line item plus delivery, the ordered and paid timestamps, an `ONLINE`
payment through PayU, the delivery, pickup point and invoice addresses, and
an invoice with a tax id. So the client, the token rotation, the orders
endpoint and the mapper all work against the real API.

The same order was then imported a third time from the interface, with the
"Import from Allegro" button: it reported 0 created and 1 updated, the
stored refresh token was replaced again, and no duplicate appeared. So both
ways of importing have now run against the real API.

**Since 2026-09-25 (Friday), Allegro and Erli are connected on the owner's
real, production accounts** (not the Sandbox), confirmed by the owner
2026-09-28: orders import from both, and Allegro's buyer messages, on the
usual 15-minute schedule. Safe mode has stayed on throughout, so nothing has
been written back to either marketplace - every "Writing to Allegro" and
"never bought/sent" note below still stands for what leaves Anvero, only not
for what comes in. Returns, claims and disputes have not been checked this
way and, unlike orders and messages, have no automatic schedule at all
(`app/services/schedule.py`'s `default_jobs()` lists only Allegro orders,
Erli orders and Allegro messages): the sync only runs when the button in the
interface is clicked.

The NAS deployment (`DEPLOYMENT.md`) and the automatic update (every 15 minutes by default for Allegro, Erli and messages, set in Integrations, backends taking turns by a lease, `DECISIONS.md`) have not run: the Dockerfiles, the compose file and the publish workflow were written without Docker or GitHub Actions to try them on, and the scheduled path was only checked up to "skips when no account is connected" on a machine without one.

Shipments and carrier tracking (`INTEGRATIONS.md`) were built from Allegro's documentation and tested against fakes only: no real response has been seen, and whether the application's scopes allow the two endpoints is unknown.

The dispatch deadline (`dispatch_by`, `INTEGRATIONS.md`, "Dispatch deadline") is read from the documented `delivery.time.dispatch.to`; no real order has shown it yet, so the "late" queue and the at-risk order stay empty-handed until one does. The queue tabs and dashboard tiles were checked in the browser on 2026-09-24 against the one sandbox order, which has no deadline.

The InPost integration (`INTEGRATIONS.md`, "InPost") has never run against InPost: no token has been used, and it was built from ShipX's documentation and tested against fakes. Unconfirmed in particular: that `sending_method` is not required, that InPost chooses the offer itself, the batch labels request, and the status words after `confirmed`. Its migration `e9b4c2a7d5f1` was applied to the shared PostgreSQL on 2026-09-25: the other machines need `alembic upgrade head`. The Settings card, the Labels tab and the not-connected state were opened in the browser; nothing beyond that. The shipping analysis of the same day (`ROADMAP.md`, "Shipping and labels: analysis and proposed plan") found it would probably pay for Allegro Smart parcels from the InPost balance: keep it off for Allegro orders until that plan is settled.

The Erli import (`INTEGRATIONS.md`, "Erli") was built from Erli's published OpenAPI description and tested against fakes before it had ever run for real; since 2026-09-25 it runs against the owner's real shop (see above). Still unconfirmed from that: that amounts are in grosze, the status mapping, and how soon Erli fills in the buyer's email - the owner has not reported checking those specifically, only that orders come in.

Writing to Allegro (status and tracking number, `INTEGRATIONS.md`, "Writing to Allegro") has never sent anything: safe mode has been on. Unverified: that the application carries the `allegro:api:orders:write` scope, that Allegro accepts the status transitions as mapped, and the carrier ids. Safe mode itself was checked in the browser on 2026-09-24 (banner, Settings, the confirmation), without switching it off on the shared database.

The application status page (`GET /status`, the Status page) was checked in the browser on 2026-09-24 on a scratch SQLite database with made-up connection rows (an expiring token, a failed import, an Erli key never used), not against a real account: its verdicts rest on the last import, and the token expiry assumes Allegro's three months hold.

Labels through Wysyłam z Allegro (`INTEGRATIONS.md`) have never bought anything: safe mode has been on and no Allegro was reachable where they were built. Unverified: the `allegro:api:shipments:write` scope, the shape of Allegro's shipment (carrier and waybill), whether Allegro links the shipment to the order itself, and the label PDF request, including one request for many labels (the Labels page), and every courier pickup call (proposals, ordering, their shapes). The Settings section and the order's label card were checked in the browser on 2026-09-24 on a scratch SQLite database, with a label row made up by hand, and the Labels page the same way.

Returns, claims and disputes (plan B4, `INTEGRATIONS.md`, "Returns and claims") were built from Allegro's published OpenAPI specification, read in full, and tested against payloads shaped like its examples. First read against the real account, 2026-09-28: failed with a `406` (the disputes-and-claims call was missing the beta `Accept` header the endpoint needs); fixed, and a second read succeeded - 0 open issues, 10 closed issues, 10 customer returns (`DECISIONS.md`). Still unverified: the 14 and 45 day rules (Allegro's API gives no deadline for a return), whether the 45 days start at the declaration, and all of it against a real *open* case (none was open at the time of this read). Read only; every action is left.

Billing entries (fees, `INTEGRATIONS.md`, "Fees") have been read from the owner's real Allegro account since 2026-09-27, and Erli's billing and payouts from the real Erli the same day. Allegro's payouts (`INTEGRATIONS.md`, "Payouts") were read from the real account on 2026-09-27, once `allegro:api:payments:read` had been added to the application and the account connected again: 21 payouts in September, all through Allegro Finance (`AF`), none cancelled, so `PAYOUT_CANCEL` has not been seen.

Buyer messages (plan B2, `INTEGRATIONS.md`, "Buyer messages") made their first real call on 2026-09-24, to production Allegro, and were answered `422 Incorrect limit or offset`: the page size was 100 where the Message Center allows 20. Fixed (`MESSAGING_PAGE_SIZE`), and the specification, fetched that day from `developer.allegro.pl/swagger.yaml`, confirmed the sort order, the scope name and the message shape, and gave a message's direction as a field (`author.isInterlocutor`). Since 2026-09-25 it runs successfully against the owner's real account on the usual schedule (see "Not yet verified" above), so the retry after the fix did succeed. Still unseen: a reply, and the link of a thread to its order, which the public thread schema does not carry (`INTEGRATIONS.md`). Safe mode has been on throughout, so nothing has reached a real buyer. Erli is not read: no messaging endpoint was found in its public API.

The non-invoiced sales report ported on 2026-09-27 (`DECISIONS.md`, "Non-invoiced sales report,
ported") was opened in the browser against the owner's real September orders that day. It was
removed on 2026-10-01, replaced by the non-invoiced sales record (`NON_INVOICED_SALES.md`), whose
state is under "Not yet verified" above.

One backend test failure was found while working on the above, unrelated to it: `tests/services/test_order_import_service.py::test_the_recorded_point_is_the_start_of_the_run_less_a_small_overlap` compared a naive and an aware datetime and only failed on SQLite; fixed on 2026-09-24 by normalising with `_as_utc` (636 pass on SQLite). A second, unrelated bug was found and fixed: `OrderRepository.list_buyer_orders` and `.list_in_queue_with_items`, added by plan A3, had a `-> list[Order]` return annotation evaluated *after* a method literally named `list` in the same class body, so Python resolved `list` to that method instead of the builtin and the whole backend failed to import (`TypeError: 'function' object is not subscriptable`) — moved both methods earlier in the file; no behaviour changed. Worth checking whether this broke every backend since plan A3 landed earlier the same day. The same mistake came back in `AfterSalesRepository.list` (a `list[...]` annotation after a method named `list`), which stopped the backend from starting on Python 3.13 while CI (3.14, deferred annotations) stayed green; fixed on 2026-09-24 with `from __future__ import annotations`. Any class with a method named after a builtin it also uses in annotations can do this: run the suite on 3.13 as well as 3.14.

What the sandbox did **not** cover: a cancelled order and the flag it sets,
an order with several line items or without a pickup point, more than one
page of orders, and production Allegro, which has its own application,
credentials and real buyers.

Verified on PostgreSQL 17.10 on the main machine: every migration up, all
the way down and up again, with `alembic check` reporting no drift; the whole
test suite, including the date filters, "this week" and the repository's
per-dialect timestamp handling; sample data generation; the API starting and
serving requests; logging in to the interface, opening an order with its
details and changing its status. Only PostgreSQL 17 has been tried.

---

The 2026-09-24 interface work (`DECISIONS.md`, "Design agreements") was checked in the browser only for the order page, its arrows and back, and the list's Items column, on three real orders (two from Erli); the menu's counts were read from the DOM on real data, with no overdue or unread thing among them, so the red state and the messages figure have not been seen for real. Item pictures do not appear on any of the three (none carries one: the Allegro one predates the picture import, and Erli's import does not read pictures). The list's table is wider than its container at 1280 px because of the Shipping column, and scrolls sideways. The design document's open areas (place of work, a typical day, dashboard, packing, alert thresholds) are still unanswered.

---

The test label (`GET /labels/test-pdf`) was opened in the browser pane's PDF viewer and looks as designed; it has not been printed on the thermal A6 printer, which is what it is for. The tracking links were checked in the browser for the two Erli orders (InPost, the address they point at is right by construction) and not opened on the carriers' sites; the addresses for DPD, DHL, Poczta Polska, UPS, GLS and FedEx are unchecked against real numbers.

---

Deleting an order (`DECISIONS.md`, 2026-09-24, "soft") is covered by tests and its list view was opened in the browser (the "Deleted" chip, empty), but the trash button was not pressed on the real orders in the shared database, so the confirmation, the toast and a restore have not been seen end to end. Its migration `b8e3d5a7c246` was applied to the shared PostgreSQL on 2026-09-24: the other machines need `alembic upgrade head`.

---

The 2026-09-25 order-page work (`DECISIONS.md`, "The order's page is laid out like BaseLinker's") was checked in the browser on a scratch SQLite database with sample data, at a phone-like width only (the pane was 374 px wide): the header with the next-step button, a real status step, the star and flag, the attention chips, the message window, the actions menu, the folded sections with their counts and the internal note saved. The two-column layout at desktop width was seen only in a shrunken screenshot, so its spacing has not been judged; the copy buttons, the Allegro and InPost tabs with real labels, and the page on the shared PostgreSQL were not opened. The migration `b6e2f9a1c473` has not been applied to the shared PostgreSQL.

---

The 2026-09-25 list and menu work (`DECISIONS.md`, "Ideas from BaseLinker") was checked in the browser on a scratch SQLite database with sample data, not on the shared PostgreSQL: the menu folding at 900 and 600 px (the page's left edge and width, the choice kept, the narrow menu folding after a link), the ticking and the bar, one bulk status change over ten orders (ten `PATCH .../status` answered 200, the list read again), a star kept after a reload and the starred filter, the menu's status and channel shortcuts, and the enlarged picture in an order's details (320 px, wholly inside the window). Not seen: the toast messages on screen (only the tests assert them), a bulk change on orders that go on to a real Allegro (safe mode was on and nothing is connected there), the flag and the three icons that need real data (a parcel, an invoice, a note), and the whole on real orders. **Its migration `a4d7c1e9b352` has not been applied to the shared PostgreSQL**, so a backend with this code cannot serve that database until `alembic upgrade head` is run on it.

---

The 2026-09-24 order-list work (`DECISIONS.md`, "Open orders are read again every import") was checked on the real orders: an import after the change stored parcels for all 12 open orders, the sticky scrollbar and the thumbnail preview were exercised in the browser (the hover by a simulated pointer event, the scroll by moving the bar). Not seen: the automatic import running on its own for a while (this machine's `.env`, which is not in Git, now has `ALLEGRO_IMPORT_INTERVAL_MINUTES=15`; a second backend on the same database must not set it, and the NAS deployment will need it set there instead), and the paging choices past the second page (there are only 48 orders).

---

Fixed on 2026-09-28, found from real orders on the shared database: 11 Allegro
orders packed and marked ready by hand, then shipped through "Wysyłam z
Allegro", stayed showing "ready to ship" in Anvero even though Allegro already
said `SENT` - the guard against an in-flight import overwriting a status just
set by hand was comparing against Allegro's own `updatedAt`, which does not
reliably move for a fulfillment-only change, so it almost always blocked the
marketplace's move, and once blocked the order never got another chance
(`DECISIONS.md`, "Fixed: orders stuck showing 'ready to ship' after Allegro
marked them sent"). The 11 were moved to `SHIPPED` directly on the shared
database. **Deployed to the NAS 2026-09-28**: `/api/v1/health` there answers
`commit: 286ab9d`. The updater was also set up on this deploy (`UPDATER_TOKEN`
added to the NAS's `docker-compose.yml`, `anvero-updater` made public), so the
next one can go through Settings instead of SSH.

---

The 2026-09-28 roles-and-permissions work (`DECISIONS.md`, "Accounts Get a Role and Per-Area
Permissions") was checked in the browser only on a scratch SQLite database with made-up accounts
(an admin and a limited "user" granted `orders:manage` and `messages:view`): the Users tab's list,
its permission grid reading and saving correctly, and creating a new account. Its migration
`c2a6f9e3b184` was applied to the shared PostgreSQL on 2026-09-28 (along with `a7d4e2c9f136`,
GDPR's `anonymized_at`), and the code deployed to the NAS the same day (below) - the migration
that filled `role`/`admin` for every existing account, so nobody lost access. Not seen: the tab on
the owner's own real account or real data, a "user" role account actually logged in and clicking
through the interface with the sidebar's sections hidden by its grants (checked only by the
backend's own tests and by reading the code), and the production frontend build (`npm run build`)
- only the Vite dev server was used. No end-to-end browser test exists for it yet, only `pytest`
and Vitest component tests.

---

## Next Milestone

**First deployment to the NAS is done (2026-09-27).** Running in Container
Station on the QNAP (`domowy`), reached at `http://NAS_ADDRESS:8081` (not
8080 - the NAS's own `apache_proxy` already held it). The backend reaches the
database by joining its stack's Docker network and addressing it by container
name, not the NAS's LAN address, which timed out from inside a container
(`DEPLOYMENT.md`, `DECISIONS.md`). Health check, login and the shared accounts
were confirmed working. Confirmed: the NAS's application directory has no git clone and no
build context, only the compose file pulling `ghcr.io` images, so updating it
is `docker compose pull && docker compose up -d` (or Container Station's
recreate) - see `DEPLOYMENT.md`, "Updating".

**Updater set up on the NAS, 2026-09-28.** Update detection and the Settings
button are built (`DEPLOYMENT.md`, "Updating from Settings"): the backend
polls GitHub and GHCR, the updater container recreates backend and web. The
one-time setup is done: `anvero-updater` made public, `UPDATER_TOKEN`
generated and added to the NAS's `docker-compose.yml` (both the `backend` and
the new `updater` service), the file confirmed named `docker-compose.yml` in
the application's folder, `/var/run/docker.sock` confirmed present and
mountable. Confirmed live: the backend's own log shows a successful call to
`api.github.com` for the newest commits, and `/api/v1/health` answers
`commit: 286ab9d`. **Not yet seen:** the Update button actually clicked from
Settings (the recreate so far was done by hand over SSH, to get the updater
itself onto the NAS in the first place) - the next push to `main` is the real
test of the button end to end. This answers the older "automatic update
detection and deployment" open task (`ROADMAP.md`, "Somewhere to run").

**Left from the updater setup:** next push to `main` - use the Settings,
Updates button on the NAS instead of SSH, to confirm the button itself works.

**Order page summary redesign (2026-09-29): built, awaiting the owner's look.**
Round two of the 2026-09-28 design session is in (`DECISIONS.md`, 2026-09-29):
status picker and facts in the header, payment folded after the status
history, shipping its own card again, an Allegro Smart badge from the new
`orders.delivery_smart`. Tests and type-check pass; the page itself has not
been seen in a browser - see "Not yet verified".

**Feature work after that (agreed 2026-09-24):** the feature plan at the end
of `ROADMAP.md`, modelled on AlleIntegrator. Its first stage (work queues,
the "to make today" list, search) touches only Anvero's own data and can
start before the NAS or production Allegro are done.

**Also started 2026-09-24, ahead of that order:** plan B2, buyer messages —
see "Current State" (`AI_START_HERE.md`) and "Not yet verified" above. Left:
confirming the unverified fields against Allegro's real response or its
published spec (this session could not reach `developer.allegro.pl`), and
trying a reply on the Sandbox with safe mode off.

Run the Allegro import against a real account, starting in the Allegro
Sandbox. Agreed plan, in order:

1. ~~**Fix SQL logging first.**~~ Done 2026-09-17: SQL echo no longer
   follows `DEBUG` and never shows values, and the access log drops query
   strings. See `DECISIONS.md`.
2. ~~**Allegro Sandbox.**~~ Done 2026-09-17. The sandbox application is
   registered with its own User-Agent and authorized against the sandbox
   seller account, and a real order the sandbox buyer placed was imported and
   re-imported; "Not yet verified" above says what that covered. Payment
   needed no special handling: the order arrived paid, through PayU. The
   authorization was made on the SQLite machine, and the token chain was per
   machine (`INTEGRATIONS.md`). On 2026-09-18 its credentials row was copied
   into the shared PostgreSQL; an import from another machine against that
   database has not been tried yet. Importing from
   the interface button was checked too. Left from this step, when there is
   a reason: a cancelled order and an order with several line items.
3. ~~**Production Allegro** with the owner's seller account, same steps.~~
   Connected and importing since 2026-09-25 ("Not yet verified" above); what
   the sandbox did not cover (below) still applies, and every write is still
   untried for real (safe mode has stayed on).
4. **What real data will likely demand:** ~~importing every page and only
   what changed~~ done 2026-09-21 (first import: last 7 days, then only new
   or changed orders, all pages; `DECISIONS.md`); what remains is a
   scheduled import, and the order event journal if `updatedAt` proves too
   coarse.
5. **Owner decisions after using it on real orders:** status transition
   rules, and which of ERLI, shipping or invoicing comes after the MVP
   (`ROADMAP.md`).

All the smaller items from `ROADMAP.md`'s interface/safety-net sections are
done as of 2026-09-18: backend lint findings cleared, a first set of frontend
tests (Vitest + React Testing Library) wired into the hook and CI, the order
list's worst readability faults fixed, and a pass over the CSS naming values
that were already repeated across files (see `DECISIONS.md`,
`CHANGELOG.md`).

With production Allegro blocked on the owner's own steps, more interface
work and one more imported field were pulled forward the same day, not the
postponed redesign (`DECISIONS.md` has the full list):

- Order status is editable directly from the list, colored options included.
- The status-history timeline shows an icon per entry.
- The order detail view opened as a slide-over above the list; since
  2026-09-24 it is a page of its own again (back, next/previous), and the list
  shows items and the menu shows counts (`DECISIONS.md`, "Design agreements").
- The seller's own Allegro note (`note.text`, distinct from the buyer's
  message) is now imported and shown in its own yellow-tinted card.
- The order list is reorganized toward the owner's reference (BaseLinker):
  one Order cell (id, buyer, source) replacing three columns and dropping
  the raw email from the list, a real Payment column, and empty
  Items/Shipping placeholders for what Anvero cannot show yet. Sidebar
  narrowed to 200px.
- Order items show a thumbnail fetched from Allegro's offer API
  (`GET /sale/product-offers/{offerId}`, a second call the checkout-form
  data does not carry), hover to enlarge in place. Best-effort: unverified
  whether the current authorization's scope allows it until tried against
  the sandbox.

Still open: a browser check of the authenticated pages by the owner, since
every screen needs a login and that verification is deliberately not
something an assistant does — including, now, whether the item pictures
actually come through on a real Allegro order.

---

## Tech Stack

Backend:
Python, FastAPI, SQLAlchemy, Alembic

Frontend:
React + TypeScript, Vite

Database:
PostgreSQL 17, SQLite (no-setup default for a fresh clone)

---

## Last Update

2026-10-01
