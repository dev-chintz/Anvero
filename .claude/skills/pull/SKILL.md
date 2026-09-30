---
name: pull
description: Pull the latest Anvero changes from GitHub and run whatever follow-up (migrations, npm install, pip install) the pull requires. Use when the user asks to pull, sync, or update the local repo from GitHub, or says "zrob pull".
---

Pull the Anvero repo from GitHub and bring this machine's environment back in
sync, following `CLAUDE.md`'s "Start of every session" rules exactly.

1. Run `git status`. If there are uncommitted changes, stop and tell the
   user — do not stash or discard anything automatically. Ask how they want
   to proceed before pulling.
2. Run `git pull`. If it does not fast-forward cleanly (merge conflicts,
   diverged branch), stop and report the conflict instead of resolving it
   silently.
3. Diff what the pull brought in:
   - `git diff --stat ORIG_HEAD HEAD -- backend/migrations/versions/` — if
     this lists new files, run (from `backend/`):
     `.\.venv\Scripts\alembic.exe upgrade head`
   - `git diff --stat ORIG_HEAD HEAD -- frontend/package-lock.json` — if this
     is non-empty, run (from `frontend/`): `npm.cmd install`
   - `git diff --stat ORIG_HEAD HEAD -- backend/requirements.txt` — if this
     is non-empty, run (from `backend/`):
     `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
4. Report a short summary: how many commits/files came in, whether
   migrations ran, whether npm install and pip install ran, and flag anything that failed
   (e.g. a migration failing because `DATABASE_URL` points at a database
   this machine can't reach — that's an environment issue to surface, not to
   silently work around).

Use full paths / `cd` explicitly before each command rather than chaining
with `&&` — this is Windows PowerShell 5.1.
