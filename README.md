# Anvero

Anvero is a locally developed system supporting marketplace sales management. The first version focuses on a single, unified view of orders and preparing architecture for Allegro and ERLI integrations.

## Status

The backend and frontend both run against a local SQLite database: orders can
be listed, filtered, searched, opened, and moved between statuses, with every
transition recorded. An Allegro adapter and import script exist.

Two things are still open, and both need a person rather than more code:
PostgreSQL is not connected, and the Allegro import has never run against the
live API. See [Project Status](docs/PROJECT_STATUS.md) for what that means in
practice and which behaviour is therefore unproven.

## Quick Start (Windows)

In PowerShell, from the project directory, run:

```powershell
.\scripts\bootstrap.ps1
.\scripts\doctor.ps1
```

`bootstrap` creates a local Python environment and installs dependencies if the requirements file has been added. `doctor` checks if the environment is ready for further work.

If PowerShell blocks running local scripts, run once:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Running the application

Install the frontend dependencies once per machine — `node_modules` is not in
Git:

```powershell
cd frontend
npm install
```

`bootstrap` created `backend/.env` from `backend/.env.example`, which uses a
local SQLite file, so no database server is needed. Neither `.env` nor the
database file is in Git; each machine builds its own.

Create the database schema and, optionally, some orders to look at:

```powershell
cd backend
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts\generate_sample_data.py --force
```

Then start the two servers, each in its own terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

```powershell
cd frontend
npm run dev
```

The interface is at <http://localhost:5173> and the API at
<http://localhost:8000>, with its generated documentation at
<http://localhost:8000/docs>. The dev server proxies `/api` to the backend,
so both must be running.

Tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

## Documentation

- [Project Context](docs/PROJECT_CONTEXT.md)
- [MVP](docs/MVP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATABASE.md)
- [API Contract](docs/API.md)
- [Development Plan](docs/ROADMAP.md)
- [Decision Log](docs/DECISIONS.md)
- [Local Development](docs/DEVELOPMENT.md)
- [Integrations](docs/INTEGRATIONS.md)

## Structure

```text
backend/    FastAPI application, Alembic migrations, tests and scripts
frontend/   React + TypeScript interface (Vite)
docs/       project documentation
scripts/    PowerShell helpers for the local environment
```
