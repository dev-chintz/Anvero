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
machine: the migrations and the full test suite run on it. One thing stands
between the current state and a working system — running the Allegro import
against a real account, which needs steps only the project owner can take.

Other machines stay on SQLite until PostgreSQL is set up there
(`DEVELOPMENT.md`, "Using PostgreSQL"); each machine has its own database.

---

## Sprint 2 — Working Skeleton

- Backend framework selection and configuration — done (FastAPI)
- Connection to local PostgreSQL database — done (PostgreSQL 17.10; SQLite
  remains the no-setup default for a fresh clone)
- Health endpoint and first order model — done
- Minimal order list interface — done
- Automated tests for core flows — done (197 passing across the suite)

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

Never run against the live Allegro API. Needs a registered application and a
one-time manual authorization; see `INTEGRATIONS.md`.

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
- Dark mode
- VS Code configuration and development scripts
- Initial Figma dashboard prototype

---

## Not yet verified

The Allegro client and mapper have never touched the live API. They follow
the published contract and are covered by tests against recorded payload
shapes, which catches mapping mistakes but not a contract that differs from
its documentation. The same is true of the import endpoint and button: their
tests replace the import service with a fake, so the endpoint's own logic
(auth, the lock, the rate limit, error mapping) is verified, but nothing has
exercised the path all the way through to Allegro.

Verified against the Allegro Sandbox on 2026-09-17: the authorization
script completed a real device flow authorization of the owner's sandbox
seller account. That confirms the client id and secret, the User-Agent
header, the device endpoint, polling the token endpoint with a form body,
and saving the refresh token to `.env`. Nothing has been imported yet, so
the token refresh with rotation, the orders endpoint and the mapping remain
unverified.

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
2. **Allegro Sandbox.** A test copy of Allegro, fully separate from
   production (own accounts, no real buyers; data not backed up, offers wiped
   quarterly; the SMS code is always `123456`). The project owner creates two
   sandbox accounts at <https://allegro.pl.allegrosandbox.pl>: a seller, which
   Anvero connects to, and a buyer, on a different email, to purchase the
   seller's test offers and so create orders. Then, together: register the
   application at <https://apps.developer.allegro.pl.allegrosandbox.pl>,
   generate its User-Agent there into `ALLEGRO_USER_AGENT` (Allegro blocks
   the key over calls without one; nothing is sent until it is set),
   point `ALLEGRO_API_URL` at `https://api.allegro.pl.allegrosandbox.pl` and
   `ALLEGRO_AUTH_URL` at `https://allegro.pl.allegrosandbox.pl/auth/oauth`,
   authorize with `scripts/authorize_allegro.py` (done 2026-09-17: the
   sandbox application is registered and authorized on a machine running
   SQLite, not the main PostgreSQL one; import from that machine, since the
   token chain is per machine, see `INTEGRATIONS.md`), import, and check the real responses against the mapping,
   the stored details and the token rotation across repeated imports. How
   payment works in the sandbox is not documented; find out on the first
   purchase.
3. **Production Allegro** with the owner's seller account, same steps.
4. **What real data will likely demand:** importing every page rather than
   one (the button fetches up to 100 orders), incremental sync from Allegro's
   order event journal, and a scheduled import.
5. **Owner decisions after using it on real orders:** status transition
   rules, and which of ERLI, shipping or invoicing comes after the MVP
   (`ROADMAP.md`).

Smaller items to fit in along the way: frontend tests (there are none, only
the type-check), tests on GitHub Actions for every push (today only the local
pre-commit hook guards, and a new clone can miss enabling it), and 22
pre-existing backend lint findings.

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
