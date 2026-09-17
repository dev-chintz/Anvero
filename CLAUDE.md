# Anvero

Marketplace order management: FastAPI backend, React + TypeScript frontend,
Allegro integration. The documentation in `docs/` is the source of truth;
this file only points at it and records how to work here without tripping.

## Start of every session

1. Read `docs/AI_START_HERE.md`, then `docs/PROJECT_STATUS.md`.
2. Treat everything under "Not yet verified" in `PROJECT_STATUS.md` as
   unproven, however finished the code looks.
3. `git pull` first. This project is worked on from several machines and with
   both Claude Code and Kiro, and chat history does not travel between them.
4. If the pull brought new files under `backend/migrations/versions/`, run
   `alembic upgrade head` in `backend/`. Each machine has its own database, and
   code ahead of its schema fails on the first request touching a new column.

## Rules that are easy to miss

- `docs/API.md` and `docs/DATABASE.md` are contracts. Check them before adding
  or changing an endpoint or table; implement to them, or change them
  deliberately and say so.
- Decisions go to `docs/DECISIONS.md`, milestones to `CHANGELOG.md`
  (`docs/PROJECT_RULES.md`).
- Do not report work as done without running it: backend tests, frontend
  type-check, and for UI changes, the page in a browser.

## Commands

Run from the directory shown. The shell is Windows PowerShell 5.1: no `&&`,
and use `npm.cmd` / `npx.cmd` there.

```powershell
# backend/
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts\create_user.py you@example.com

# frontend/
npx.cmd tsc --noEmit
npm.cmd run dev
```

Setup on a new machine is `scripts\bootstrap.ps1` plus the README; it also
enables the pre-commit hook in `.githooks/`, which runs the checks above for
whichever side a commit touches.

## Environment gotchas

- The first `python` on PATH may not be a usable CPython (on the main machine
  it is Inkscape's). Use the `py` launcher or the venv interpreter directly.
- Local development uses SQLite; `.env` and the database file are per machine
  and not in Git. PostgreSQL is the target but its migration path has never
  run.
- The test suite uses its own database (`tests/conftest.py`). Never point it
  at the development database: the API tests drop all tables on teardown.
- Windows PowerShell prefixes text piped into a program with a byte-order
  mark. Anything reading piped stdin must decode with `utf-8-sig`.
- Every page and orders endpoint needs a login. Do not type passwords into the
  browser to verify UI work: check the login flow through the API, and leave
  logging in on the page to the user.

## Before ending a session

Commit, push, and make sure `docs/AI_START_HERE.md`, `docs/AI_HANDOFF.md` and
`docs/PROJECT_STATUS.md` still describe reality. If setup changed, a fresh
clone must still run from the README.
