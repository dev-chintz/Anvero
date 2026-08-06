# Local Development

## Requirements

- Windows PowerShell 5.1 or PowerShell 7,
- Git,
- Python 3.11 or newer,
- Node.js 20 or newer — required only with frontend,
- PostgreSQL 16 or newer — required from Sprint 2.

## Setup

1. Open PowerShell in the project root directory.
2. Run `./scripts/bootstrap.ps1`.
3. Run `./scripts/doctor.ps1` and fix reported errors.

The scripts do not install Python, Node.js, Git, or PostgreSQL and do not modify the computer's global configuration. `bootstrap` can safely run multiple times.

## Backend Dependencies

When `backend/requirements/base.txt` appears, bootstrap will install it to `.venv`. To manually activate the environment, use:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Quality Control

Before submitting changes, run `./scripts/doctor.ps1`. In implementation Sprints, the document will be expanded with test and formatting commands.
