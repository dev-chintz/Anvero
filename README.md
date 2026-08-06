# Anvero

Anvero is a locally developed system supporting marketplace sales management. The first version focuses on a single, unified view of orders and preparing architecture for Allegro and ERLI integrations.

## Status

Sprint 1 is complete: the repository has a defined structure, initial documentation, and scripts for environment setup and diagnostics. Application implementation will begin in Sprint 2.

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

## Documentation

- [Project Context](docs/PROJECT_CONTEXT.md)
- [MVP](docs/MVP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATABASE.md)
- [API Contract](docs/API.md)
- [Development Plan](docs/ROADMAP.md)
- [Decision Log](docs/DECISIONS.md)
- [Local Development](docs/DEVELOPMENT.md)

## Structure

```text
backend/    future Python application and tests
frontend/   future user interface
database/   migrations, schema and sample data
docs/       project decisions
scripts/    tools for local environment
branding/   brand materials
```
