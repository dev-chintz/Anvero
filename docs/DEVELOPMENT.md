# Local Development

## Requirements

- Windows PowerShell 5.1 or PowerShell 7,
- Git,
- Python 3.11 or newer,
- Node.js 20 or newer,
- PostgreSQL 16 or newer — not needed yet. Local development runs on SQLite;
  PostgreSQL is the target, but its migration path has never been run.

## Setup

1. Open PowerShell in the project root directory.
2. Run `./scripts/bootstrap.ps1`. It creates `backend/.venv`, installs
   `backend/requirements.txt` into it, and copies `backend/.env.example` to
   `backend/.env` if no `.env` exists yet.
3. Run `./scripts/doctor.ps1` and fix reported errors.
4. Install the frontend dependencies: `cd frontend`, then `npm install`.

The scripts do not install Python, Node.js, Git, or PostgreSQL and do not modify the computer's global configuration. `bootstrap` can safely run multiple times.

`backend/.env` is git-ignored, so it does not travel between machines. The
default it is copied from points at a SQLite file, `backend/anvero.db`, which
is also git-ignored: each machine builds its own database. See the README for
creating the schema and sample data.

## Backend Dependencies

To activate the environment manually:

```powershell
.\backend\.venv\Scripts\Activate.ps1
```

## Quality Control

`bootstrap` enables a pre-commit hook from `.githooks/`. It runs the backend
tests when a commit touches `backend/`, and the frontend type-check when it
touches `frontend/`; a commit that touches neither skips both. A failing check
blocks the commit. `git commit --no-verify` bypasses it — for emergencies,
since the whole point is that broken code does not reach the repository.

The hook applies whoever commits, including Kiro. Git does not version
`.git/hooks`, so the hook lives in `.githooks/` and each clone is pointed at
it with `git config core.hooksPath .githooks`, which `bootstrap` does.

To run the same checks by hand, run `./scripts/doctor.ps1`, then:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

```powershell
cd frontend
npx tsc --noEmit
```
