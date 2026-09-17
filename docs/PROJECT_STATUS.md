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

Sprint 3 and Sprint 4 are delivered, but **Sprint 2 is still not closed**:
the application runs on SQLite, and the PostgreSQL connection Sprint 2 calls
for has not been made. Two things therefore stand between the current state
and a working system — connecting PostgreSQL, and running the Allegro import
against a real account. Both need steps only the project owner can take.

---

## Sprint 2 — Working Skeleton

- Backend framework selection and configuration — done (FastAPI)
- Connection to local PostgreSQL database — NOT done, running on SQLite
- Health endpoint and first order model — done
- Minimal order list interface — done
- Automated tests for core flows — done (96 passing across the suite)

---

## Sprint 3 — Order Flow

- Order list and details — done
- Filtering by source, status and date — done
- Change history — done (status transitions and who made them)
- Sample data — done (`backend/scripts/generate_sample_data.py --force`)

---

## Sprint 4 — First Integration

- Secure credential configuration — done (environment only, `.env` ignored)
- Allegro adapter — done, built from Allegro's published documentation
- Order import and mapping — done (`backend/scripts/import_allegro.py`)
- Error handling and logging — done

Never run against the live Allegro API. Needs a registered application and a
one-time manual authorization; see `INTEGRATIONS.md`.

---

## Also completed

- Project name and branding direction
- Repository structure, local Git repository, GitHub remote
- Rate limiting on the login endpoint (5/minute per IP)
- Order status editing via `PATCH /orders/{id}/status`
- Dashboard aggregates computed in SQL (`GET /orders/stats`)
- Unique constraint on `(source, external_id)`, so an import is safe to re-run
- Dark mode
- VS Code configuration and development scripts
- Initial Figma dashboard prototype

---

## Not yet verified

The Allegro client and mapper have never touched the live API. They follow
the published contract and are covered by tests against recorded payload
shapes, which catches mapping mistakes but not a contract that differs from
its documentation.

Everything below has only been exercised against SQLite:

- Migrations use `Uuid`, `Numeric` and `Enum`; on PostgreSQL `Enum` creates
  a real database type, which is the most likely place to break. The status
  history migration branches on dialect to reference the existing
  `order_status` type instead of recreating it; only the SQLite branch has
  been run.
- Date filters and the dashboard's "this week" figure compare timestamps.
  SQLite stores naive datetimes and PostgreSQL stores aware ones; the
  repository normalises per dialect, but only the SQLite path has been run.

---

## Next Milestone

Connect PostgreSQL and re-run the migrations and the test suite against it,
then run the Allegro import against a real account.

---

## Tech Stack

Backend:
Python, FastAPI, SQLAlchemy, Alembic

Frontend:
React + TypeScript, Vite

Database:
PostgreSQL (target), SQLite (current local)

---

## Last Update

2026-09-16
