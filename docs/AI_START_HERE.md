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

**Feature work:** decided 2026-09-24 to keep building, modelled on
AlleIntegrator; the order of work is the feature plan at the end of
`ROADMAP.md`, followed there by a comparison with AlleIntegrator and the
suggested next steps (stages A1–A3 are done: work queues, the "to make" list,
wider search and the buyer's other orders; A4, the Erli import, has its
adapter built from Erli's docs and waits for the owner's API key; A5, safe
mode, is done, so every marketplace write must go through `MarketplaceWriter`;
A6, status and tracking number to Allegro, is built but never sent for real;
A7, the application status page, is done. Stage A is complete apart from
A4's first real run and A6's first real send. B1, labels through "Wysyłam z
Allegro", is built for one parcel per order, with printing many at once and
ordering a courier on the Labels page, and never used for real; cash on
delivery is not shipped, so B1 is complete in code. B2, buyer messages, is
started: see below. B4, returns and claims, is started: a read-only queue
with deadlines, an alert on the order and a dashboard reminder, built from
Allegro's published specification and never run against a real account).

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
- 636 backend and 168 frontend tests passing.
- The order opens as a page of its own with back and next/previous arrows, the
  list shows each order's items, the menu shows what waits, and a new interface
  language is a dictionary file and one line (`DECISIONS.md`, 2026-09-24).

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