# Local Development

## Requirements

- Windows PowerShell 5.1 or PowerShell 7,
- Git,
- Python 3.11 or newer,
- Node.js 20.19 or newer on the 20 line, or 22.12 or newer (Node 21 is not
  supported); Vite 8 requires it, and `scripts/doctor.ps1` checks it,
- PostgreSQL 17 — optional. A fresh clone runs on SQLite with no setup;
  PostgreSQL is the target and is verified on 17.10. See "Using PostgreSQL".

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
is also git-ignored: each machine builds its own database. A relative SQLite
path is always resolved against `backend/`, so the server, Alembic and the
scripts use the same file whichever directory they are started from. See the README for
creating the schema and sample data.

## Using PostgreSQL

Each machine has its own database, so these steps are per machine.

1. Create a role and two databases, one for the application and one for the
   tests, as the `postgres` superuser:

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -h localhost -U postgres
   ```

   ```sql
   CREATE ROLE anvero LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE anvero OWNER anvero ENCODING 'UTF8' TEMPLATE template0;
   CREATE DATABASE anvero_test OWNER anvero ENCODING 'UTF8' TEMPLATE template0;
   ```

   Use letters and digits in the password; characters such as `@`, `:` or
   `/` would have to be percent-encoded in the URLs below.

2. In `backend/.env`, comment out the SQLite `DATABASE_URL` and add:

   ```
   DATABASE_URL=postgresql+psycopg://anvero:PASSWORD@localhost:5432/anvero
   TEST_DATABASE_URL=postgresql+psycopg://anvero:PASSWORD@localhost:5432/anvero_test
   ```

3. From `backend/`: `alembic upgrade head`, then `scripts/create_user.py`
   for an account, and optionally `scripts/generate_sample_data.py`. The
   SQLite file is left untouched, so switching back is a matter of the
   `DATABASE_URL` line; data is not copied between the two.

With `TEST_DATABASE_URL` set, `pytest` and the pre-commit hook run the suite
on `anvero_test`. Without it they use a SQLite file. The suite refuses to start
if `TEST_DATABASE_URL` names the same database as `DATABASE_URL`, because the
tests drop every table. To run on SQLite once, set
`TEST_DATABASE_URL=sqlite:///./test_suite.db` in the environment for that
command.

**Forgotten `postgres` password.** In `C:\Program Files\PostgreSQL\17\data\pg_hba.conf`,
back the file up, change the method on the two `host all all` lines for
`127.0.0.1/32` and `::1/128` from `scram-sha-256` to `trust`, and restart the
`postgresql-x64-17` service (an administrator PowerShell is needed for both).
Connect with `psql -h localhost -U postgres`, which no longer asks for a
password, run `ALTER USER postgres PASSWORD '...';`, then restore the backup
and restart the service again straight away: until then any program on the
machine can connect without a password.

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
