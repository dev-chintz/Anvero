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
- Login: every orders endpoint and every page requires it. Accounts are
  created with `backend/scripts/create_user.py`; there is no sign-up.
- React + TypeScript frontend: dashboard, order list with filtering, order
  detail with items, buyer, delivery, payment and invoice, status editing and
  history.
- Allegro adapter, import script, an import endpoint and a button, one
  import at a time.
- 175 tests passing.

- PostgreSQL 17 on the main machine, with the test suite running on it;
  SQLite is the no-setup default elsewhere. Check `DATABASE_URL` in
  `backend/.env` to see which one a machine uses.

One thing is **not** done, and it needs a person rather than more code:
**the Allegro import has never run against the live API.** It was built from
Allegro's published documentation and needs a registered application plus a
one-time manual authorization. See INTEGRATIONS.md.

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