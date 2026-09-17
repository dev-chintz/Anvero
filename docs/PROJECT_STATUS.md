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
- Automated tests for core flows — done (168 passing across the suite)

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

Verified on PostgreSQL 17.10 on the main machine: every migration up, all
the way down and up again, with `alembic check` reporting no drift; the whole
test suite, including the date filters, "this week" and the repository's
per-dialect timestamp handling; sample data generation; the API starting and
serving requests; logging in to the interface, opening an order with its
details and changing its status. Only PostgreSQL 17 has been tried.

---

## Next Milestone

Run the Allegro import against a real account.

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
