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
- Automated tests for core flows — done (284 backend, 55 frontend passing
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

2026-09-18
