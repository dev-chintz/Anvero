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
import has now run against the real API in the Allegro Sandbox, so what
remains is the same on production Allegro, with the owner's seller account.

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
- Automated tests for core flows — done (543 backend, 130 frontend passing
  across the suite as of 2026-09-21)

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

The NAS deployment (`DEPLOYMENT.md`) and the scheduled import (`ALLEGRO_IMPORT_INTERVAL_MINUTES`) have not run: the Dockerfiles, the compose file and the publish workflow were written without Docker or GitHub Actions to try them on, and the scheduled path was only checked up to "skips when no account is connected" on a machine without one.

Shipments and carrier tracking (`INTEGRATIONS.md`) were built from Allegro's documentation and tested against fakes only: no real response has been seen, and whether the application's scopes allow the two endpoints is unknown.

The dispatch deadline (`dispatch_by`, `INTEGRATIONS.md`, "Dispatch deadline") is read from the documented `delivery.time.dispatch.to`; no real order has shown it yet, so the "late" queue and the at-risk order stay empty-handed until one does. The queue tabs and dashboard tiles were checked in the browser on 2026-09-24 against the one sandbox order, which has no deadline.

The Erli import (`INTEGRATIONS.md`, "Erli") has never run: no API key has been used, and it was built from Erli's published OpenAPI description and tested against fakes. Unconfirmed in particular: that amounts are in grosze, the status mapping, and how soon Erli fills in the buyer's email.

Writing to Allegro (status and tracking number, `INTEGRATIONS.md`, "Writing to Allegro") has never sent anything: safe mode has been on. Unverified: that the application carries the `allegro:api:orders:write` scope, that Allegro accepts the status transitions as mapped, and the carrier ids. Safe mode itself was checked in the browser on 2026-09-24 (banner, Settings, the confirmation), without switching it off on the shared database.

The application status page (`GET /status`, the Status page) was checked in the browser on 2026-09-24 on a scratch SQLite database with made-up connection rows (an expiring token, a failed import, an Erli key never used), not against a real account: its verdicts rest on the last import, and the token expiry assumes Allegro's three months hold.

Labels through Wysyłam z Allegro (`INTEGRATIONS.md`) have never bought anything: safe mode has been on and no Allegro was reachable where they were built. Unverified: the `allegro:api:shipments:write` scope, the shape of Allegro's shipment (carrier and waybill), whether Allegro links the shipment to the order itself, and the label PDF request, including one request for many labels (the Labels page), and every courier pickup call (proposals, ordering, their shapes). The Settings section and the order's label card were checked in the browser on 2026-09-24 on a scratch SQLite database, with a label row made up by hand, and the Labels page the same way.

Billing entries (fees, `INTEGRATIONS.md`, "Fees") are likewise from the documentation and fakes only: not known whether the application may read them, or whether the history holds anything besides fees.

Buyer messages (plan B2, `INTEGRATIONS.md`, "Buyer messages") have never talked to Allegro: built without reading its published OpenAPI specification, since this session's network egress could not reach `developer.allegro.pl`, and tested against fakes shaped by search-indexed excerpts of the documentation instead. Unconfirmed: the exact shape of one thread message, whether threads really sort newest-activity-first (the sync's early stop depends on it), and the messaging scope's real name. Safe mode has been on throughout, so nothing has reached a real buyer. Erli is not read: no messaging endpoint was found in its public API.

One backend test failure was found while working on the above, unrelated to it: `tests/services/test_order_import_service.py::test_the_recorded_point_is_the_start_of_the_run_less_a_small_overlap` compares a naive and an aware datetime and only fails on SQLite (`TypeError: can't compare offset-naive and offset-aware datetimes`); the full suite passes on PostgreSQL (527, 2026-09-24, after merging B1/A7 and B2). A second, unrelated bug was found and fixed: `OrderRepository.list_buyer_orders` and `.list_in_queue_with_items`, added by plan A3, had a `-> list[Order]` return annotation evaluated *after* a method literally named `list` in the same class body, so Python resolved `list` to that method instead of the builtin and the whole backend failed to import (`TypeError: 'function' object is not subscriptable`) — moved both methods earlier in the file; no behaviour changed. Worth checking whether this broke every backend since plan A3 landed earlier the same day.

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

## Next Milestone

**PICK UP HERE (2026-09-21): first deployment to the NAS.** Everything is
written and pushed but has never run: `docs/DEPLOYMENT.md` is the step-by-step,
to be done with the owner at the NAS. Start by checking that the *Publish
images* workflow (GitHub, Actions) went green and the two images exist under
the account's Packages; if it failed, fix the Dockerfiles/workflow first. Then
the owner needs, at the NAS: access for it to pull the images (public packages
or a `read:packages` token), the LAN address and password for `DATABASE_URL`,
and a new `SECRET_KEY`. Only that one backend may run the scheduled import.

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
3. **Production Allegro** with the owner's seller account, same steps.
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
- The order detail view opens as a slide-over above the list instead of a
  full-page navigation, so the list's filters and scroll position survive.
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

2026-09-24
