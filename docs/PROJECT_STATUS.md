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

Sprint 2, with most of Sprint 3 already delivered. Sprint 2 is not closed:
the application runs on SQLite, and the PostgreSQL connection it calls for
has not been made.

---

## Sprint 2 — Working Skeleton

- Backend framework selection and configuration — done (FastAPI)
- Connection to local PostgreSQL database — NOT done, running on SQLite
- Health endpoint and first order model — done
- Minimal order list interface — done
- Automated tests for core flows — done (22 passing)

---

## Sprint 3 — Order Flow

- Order list and details — done
- Filtering by source, status and date — done
- Change history — not started
- Sample data — done (`backend/scripts/generate_sample_data.py`)

---

## Also completed

- Project name and branding direction
- Repository structure, local Git repository, GitHub remote
- Rate limiting on the login endpoint (5/minute per IP)
- Order status editing via `PATCH /orders/{id}`
- Dashboard aggregates computed in SQL (`GET /orders/stats`)
- Dark mode
- VS Code configuration and development scripts
- Initial Figma dashboard prototype

---

## Not yet verified

Everything below has only been exercised against SQLite:

- Migrations use `Uuid`, `Numeric` and `Enum`; on PostgreSQL `Enum` creates
  a real database type, which is the most likely place to break.
- Date filters and the dashboard's "this week" figure compare timestamps.
  SQLite stores naive datetimes and PostgreSQL stores aware ones; the
  repository normalises per dialect, but only the SQLite path has been run.

---

## Next Milestone

Connect PostgreSQL and re-run the migrations and the test suite against it.

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
