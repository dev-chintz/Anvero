# AI START HERE

## Project

Anvero

Modern Business Management Platform

---

## Before doing anything

Read the following files in order:

1. PROJECT_STATUS.md
2. PROJECT_CONTEXT.md
3. PROJECT_RULES.md
4. ROADMAP.md
5. ARCHITECTURE.md
6. DATABASE.md
7. API.md
8. MVP.md
9. DECISIONS.md
10. INTEGRATIONS.md

---

## Current State

Backend and frontend both run. See PROJECT_STATUS.md for the sprint-by-sprint
breakdown; the short version:

- FastAPI backend with orders, status changes, status history and statistics.
- React + TypeScript frontend: dashboard, order list with filtering, order
  detail with status editing and history.
- Allegro adapter and import script.
- 96 tests passing.

Two things are **not** done, and both need a person rather than more code:

1. **PostgreSQL is not connected.** The application runs on SQLite. Migrations
   and the timestamp handling have a PostgreSQL path that has never executed.
2. **The Allegro import has never run against the live API.** It was built
   from Allegro's published documentation and needs a registered application
   plus a one-time manual authorization. See INTEGRATIONS.md.

Treat anything in the "Not yet verified" section of PROJECT_STATUS.md as
unproven, however finished the code looks.

---

## Rules

- Documentation is the source of truth.
- Never redesign architecture without updating documentation.
- Keep code clean and modular.
- Follow existing project structure.
- Prefer simple solutions.
- Every important decision goes to DECISIONS.md.
- Every milestone goes to CHANGELOG.md.

---

## Workflow

Read documentation.

Understand current sprint.

Implement.

Update documentation.

Commit.

Push.

Before writing code, also read:

- DEVELOPMENT_WORKFLOW.md