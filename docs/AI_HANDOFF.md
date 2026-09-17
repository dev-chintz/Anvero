# AI HANDOFF

## Project

Anvero

Modern Business Management Platform

---

# Mission

Anvero is a modern SaaS platform for managing e-commerce businesses.

The long-term goal is to build a modular, scalable system focused on excellent UX, clean architecture and AI-assisted development.

The project is developed incrementally using sprint-based planning.

---

# Current Status

Version: 0.1.0

Phase: Foundation

Sprint: Sprint 3 and Sprint 4 delivered; Sprint 2 not closed, because
PostgreSQL is still not connected.

Repository: <https://github.com/dev-chintz/Anvero>

---

# Completed

- Project name, branding direction, folder structure, development workflow
- FastAPI backend: orders, status changes, status history, statistics,
  rate-limited login
- React + TypeScript frontend: dashboard, order list with filtering and
  search, order detail with status editing and history, dark mode
- Alembic migrations for `users`, `orders` and `order_status_history`
- Allegro adapter, order mapping and import script
- 96 tests passing

---

# Current Directory Structure

```
backend/    FastAPI application, migrations, tests, scripts
frontend/   React + TypeScript (Vite)
docs/       project documentation
scripts/    PowerShell helpers for the local environment
```

`database/` and `branding/` do not exist; migrations live under
`backend/migrations/`.

---

# Current Priorities

1. Connect PostgreSQL and re-run migrations and tests against it. The status
   history migration has a PostgreSQL-only branch that has never executed.
2. Run the Allegro import against a real account, which needs a registered
   application and a one-time manual authorization (INTEGRATIONS.md).
3. Add authentication to the orders endpoints. Several things are waiting on
   it: the change author in the status history, and turning the import script
   into an endpoint.

---

# UI Direction

Style:

- Premium SaaS
- Dark left sidebar
- Bright workspace
- Purple accent color
- Rounded corners
- Large whitespace
- Modern typography

Inspired by:

- Linear
- Stripe Dashboard
- Notion
- Vercel

---

# Development Principles

- Clean Architecture
- Modular design
- Production-quality code
- Documentation first
- Small commits
- Simplicity over complexity

---

# Before Writing Code

Read:

- AI_START_HERE.md
- PROJECT_STATUS.md
- PROJECT_CONTEXT.md
- PROJECT_RULES.md
- ROADMAP.md
- ARCHITECTURE.md
- DATABASE.md
- API.md
- MVP.md
- DECISIONS.md
- INTEGRATIONS.md

---

# AI Responsibilities

Before implementing anything:

- understand current sprint
- understand project architecture
- avoid unnecessary redesign
- keep documentation synchronized
- explain important architectural decisions

---

# Long-Term Vision

Anvero should become a professional business management platform that combines:

- ERP
- Inventory
- Orders
- CRM
- Marketplace integrations
- Analytics

The system should remain modular and easy to extend.

---

# Notes

Repository documentation is the single source of truth.

Chat history must never be treated as project documentation.