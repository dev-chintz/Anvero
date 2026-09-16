# Changelog

All significant changes to the Anvero project.

---

## 2026-09-16

### ✨ Added

#### Security
- Rate limiting on `POST /api/v1/auth/login`: 5 attempts per minute per IP,
  configurable through `RATE_LIMIT_LOGIN`, returning 429 once exceeded.

#### Order Management
- `Order` model: UUID primary key, `OrderSource` and `OrderStatus` enums,
  `Decimal` amounts, timestamps.
- Repository, service and schema layers following the existing structure.
- `GET /orders` — paginated, filterable by `source`, `status`, `search`,
  `date_from` and `date_to`. All filters combine, and every one is resolved
  by the database, so the reported total spans all pages.
- `GET /orders/{id}` and `POST /orders`.
- `PATCH /orders/{id}` — change an order's status.
- `GET /orders/stats` — count, revenue, this-week, pending and the
  status/source breakdowns, aggregated in SQL.
- Alembic migration for the `orders` table.

#### Frontend
- React 18 + TypeScript (strict) on Vite, with `/api` proxied to the backend.
- Sidebar navigation, dashboard, order list, order detail, settings stub.
- Advanced filter panel: search, source, status and date range, seeded from
  the URL and debounced by 300 ms.
- Status editing on the order detail page.
- Dark mode, persisted in `localStorage`.
- Toast notifications and an error boundary.

#### Tooling
- Git repository initialised and pushed to GitHub.
- `backend/scripts/generate_sample_data.py` — 10 sample orders for local work.

### 🔧 Fixed

Defects introduced earlier the same day and corrected before close:

- The test suite shared `settings.database_url` with development and called
  `drop_all()` on teardown, so running the tests destroyed local data.
  `tests/conftest.py` now points the suite at its own database.
- The frontend did not type-check; `OrdersPage` passed a type
  `AdvancedFilters` does not accept.
- The dashboard derived its totals from a single 100-row page and used
  `orders.length` as the order count, so it under-reported past 100 orders.
- Search filtered only the rows already on screen, so a match on a later
  page read as "no results" while the pager showed the unfiltered total.
- `OrderService` used `if/elif`, so `source` and `status` together filtered
  the page by source alone while counting the total with both.
- The From/To date inputs fed the URL but no backend filter existed.
- `OrderList` carried a second pair of source/status selects that duplicated
  `AdvancedFilters` and reused the same DOM ids, breaking `label` association.
- `Dashboard.css` held 24 rules under `.dashboard.dark`, a class the
  component never received, so the dashboard stayed light in dark mode.
  All theming now keys off `:root.dark`.
- Migrations used `sa.text("now()")`, which is PostgreSQL-only and fails on
  SQLite; replaced with `func.current_timestamp()`.
- `generate_sample_data.py` called `db.func`, which does not exist on a
  SQLAlchemy `Session`.
- `test.db`, `vite.config.js`, `vite.config.d.ts`, both `.tsbuildinfo` files
  and `.claude/settings.local.json` were tracked in Git despite being
  regenerated on every run. Untracked, and the tsconfigs now emit into
  `node_modules` so they stop reappearing.

### ✅ Verification

- 22 backend tests passing.
- `tsc --noEmit` clean; production build succeeds.
- Rate limiting: 5 requests return 401, the 6th returns 429.
- Search, combined filters, date range and `PATCH` confirmed in the browser
  against live data, each read back independently from the API.
- Typing 10 characters into search issues one request, not ten.

### ⚠️ Not verified

The application runs on SQLite. Nothing here has been exercised against
PostgreSQL, and two areas are likely to differ:

- Migrations use `Uuid`, `Numeric` and `Enum`; on PostgreSQL `Enum` creates
  a real database type.
- Date filters and the "this week" figure compare timestamps. SQLite stores
  naive datetimes, PostgreSQL aware ones. The repository normalises per
  dialect, but only the SQLite path has been run.

### 📌 Next

- Connect PostgreSQL and re-run migrations and tests against it.
- Order change history.
- Allegro adapter.

---

## 2026-08-06

### ✨ Added

#### Authentication
- Added JWT authentication.
- Implemented `AuthService`.
- Added `/api/v1/auth/login` endpoint.
- Implemented password verification.
- Implemented JWT access token generation.
- Added OAuth2 support for FastAPI.

#### Users
- Added persistent user registration.
- Added duplicate email validation.
- User passwords are now stored as hashed values.
- Registration now persists users in PostgreSQL.

#### Database
- Configured Alembic.
- Created initial migration for the `users` table.
- Alembic now uses FastAPI application settings.
- Added automatic model discovery for migrations.

#### API
- Added authentication router.
- Updated users endpoint to use dependency injection.
- Added proper response models.

#### Tests
- Added registration API tests.
- Added duplicate registration test.
- Registration tests now generate unique email addresses.

### 🔧 Changed

- Configuration now loads `.env` correctly regardless of the current working directory.
- SQLAlchemy session configuration cleaned up.
- Repository and service layers fully integrated.
- Project architecture aligned around:
  - Repository
  - Service
  - API Endpoint

### 🧠 Architecture

Implemented layered architecture:

```text
API
 │
 ▼
Service
 │
 ▼
Repository
 │
 ▼
Database
```

JWT flow:

```text
Login
 │
 ▼
AuthService
 │
 ▼
UserRepository
 │
 ▼
verify_password()
 │
 ▼
create_access_token()
 │
 ▼
JWT
```

### ✅ Verification

- Alembic migrations working.
- User registration verified.
- Login verified.
- JWT generation verified.
- Swagger integration verified.
- All tests passing.

### 📌 Next Sprint

- Implement `get_current_user()`
- Add `GET /users/me`
- Enable Swagger Authorize
- Add authentication tests
- Protect authenticated endpoints
