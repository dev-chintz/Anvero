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

**Open task:** the first deployment to the NAS is prepared but not yet run; see "PICK UP HERE" in `PROJECT_STATUS.md` and `DEPLOYMENT.md`.

Backend and frontend both run. See PROJECT_STATUS.md for the sprint-by-sprint
breakdown; the short version:

- FastAPI backend with orders, status changes, status history and statistics.
- Login: every orders endpoint and every page requires it. Accounts are
  created with `backend/scripts/create_user.py`, passwords changed with
  `backend/scripts/reset_password.py`; there is no sign-up.
- React + TypeScript frontend: dashboard, order list with filtering, order
  detail with items, buyer, delivery, payment and invoice, status editing and
  history.
- Allegro adapter, import script, an import endpoint and a button, one
  import at a time.
- 284 backend and 55 frontend tests passing.

- One shared PostgreSQL 17 on the owner's NAS is the development database;
  each machine's `backend/.env` points at it (the password is not in Git, ask
  the owner). SQLite remains the no-setup default for a fresh clone. Check
  `DATABASE_URL` in `backend/.env` to see which one a machine uses. Away from
  home the NAS is reachable only through a VPN (`DEVELOPMENT.md`).

The Allegro import **has** now run against the real API, in the Allegro
Sandbox: one order imported and re-imported on 2026-09-17. Production
Allegro is the next step and needs its own application, its own one-time
authorization and the owner's seller account. See INTEGRATIONS.md.

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