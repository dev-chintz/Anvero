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

Other machines stay on SQLite until PostgreSQL is set up there
(`DEVELOPMENT.md`, "Using PostgreSQL"); each machine has its own database.

---

## Sprint 2 — Working Skeleton

- Backend framework selection and configuration — done (FastAPI)
- Connection to local PostgreSQL database — done (PostgreSQL 17.10; SQLite
  remains the no-setup default for a fresh clone)
- Health endpoint and first order model — done
- Minimal order list interface — done
- Automated tests for core flows — done (209 passing across the suite)

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
   authorization lives on the SQLite machine, and the token chain is per
   machine, so imports run from there (`INTEGRATIONS.md`). Importing from
   the interface button was checked too. Left from this step, when there is
   a reason: a cancelled order and an order with several line items.
3. **Production Allegro** with the owner's seller account, same steps.
4. **What real data will likely demand:** importing every page rather than
   one (the button fetches up to 100 orders), incremental sync from Allegro's
   order event journal, and a scheduled import.
5. **Owner decisions after using it on real orders:** status transition
   rules, and which of ERLI, shipping or invoicing comes after the MVP
   (`ROADMAP.md`).

Smaller items, all done 2026-09-18: backend lint findings are cleared (see
`DECISIONS.md`; ruff itself still isn't run from the hook or CI), the
frontend has a first set of tests (Vitest + React Testing Library), wired
into the hook and CI, and the order list's worst readability faults (badges
crowding the status column, the email column eating a third of the row) are
fixed (`CHANGELOG.md`). Still open from `ROADMAP.md`'s interface section: one
pass over `index.css`, and a browser check by the owner, since every screen
needs a login.

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

2026-09-17
