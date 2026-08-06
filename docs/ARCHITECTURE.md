# Architecture

## Principle

Anvero is divided into frontend, backend, and database. Marketplace integrations are adapters: they translate data from specific platforms to a common Anvero domain model.

```text
Frontend -> Backend API -> Domain services -> PostgreSQL
                              ^
                              |
                    Allegro / ERLI adapters
```

## Responsibilities

- `frontend/` — views, forms, API communication.
- `backend/app/api/` — HTTP endpoints and input validation.
- `backend/app/services/` — use cases and business rules.
- `backend/app/integrations/` — client and data mapping for each external API.
- `backend/app/models/` — persistent data models.
- `backend/app/schemas/` — API data contracts.
- `database/` — migrations, schema definitions, and sample data.

## Sprint 1 Assumptions

Python will be the backend language, PostgreSQL the target database, and the interface a web application. Framework selection will occur before Sprint 2 implementation and be recorded in `DECISIONS.md`.

## Boundaries

Frontend does not communicate directly with the database or marketplace APIs. Allegro and ERLI code does not expose its raw structures outside the integration module.
