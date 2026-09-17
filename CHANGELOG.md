# Changelog

All significant changes to the Anvero project.

---

## 2026-09-17

### 🔧 Fixed

A fresh clone could not be brought up by following the documentation. Found
by cloning the repository into an empty directory and following the README
step by step, which is what continuing on another machine amounts to.

- `bootstrap.ps1` used the first `python` on PATH. On a machine with Inkscape
  installed that is Inkscape's bundled MinGW Python, whose venvs have a
  `bin\` directory instead of `Scripts\` and no working pip, so bootstrap
  failed. It now tries the `py` launcher first and checks each candidate is
  3.11+ and lays a venv out the Windows way. A broken venv left by an earlier
  run is removed and rebuilt rather than blocking every later run.
- `bootstrap.ps1` printed "Dependencies installed" even when `pip install`
  failed. It now stops on a failed pip upgrade or install.
- `doctor.ps1` reported a venv as healthy if the folder existed, so the broken
  one above passed. It now checks for the interpreter inside it.
- `backend/requirements.txt` was stored in Git as UTF-16, so Git treated it as
  binary — no readable diffs — and plain-text tools could not search it. pip
  tolerated it, which is why nothing had failed. Re-encoded as UTF-8.
- `.env.example` pointed `DATABASE_URL` at PostgreSQL, so a fresh `.env`
  targeted a server that is not set up and a migration path that has never
  run. It now defaults to a local SQLite file, `backend/anvero.db`, with
  PostgreSQL left as a commented alternative.
- The README never said to run `npm install`, so `npm run dev` failed on a new
  machine. `DEVELOPMENT.md` pointed at a nonexistent
  `backend/requirements/base.txt`, the wrong venv location, and called
  PostgreSQL a requirement.

### ✅ Verification

On a clean clone: bootstrap, doctor, `alembic upgrade head`, sample data and
`npm install` all succeed; 66 tests pass; `tsc` is clean; the interface, the
API, the API docs and the `/api` proxy all answer, with the proxy returning
the sample data.

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
- `PATCH /orders/{id}/status` — change an order's status. Sending the current
  status is a no-op.
- `GET /orders/{id}/history` — status transitions, most recent first. The
  history row and the new status are committed together, so the log cannot
  drift from the order it describes. Entries record no author; the orders
  endpoints have no authentication yet.
- `GET /orders/stats` — count, revenue, this-week, pending and the
  status/source breakdowns, aggregated in SQL.
- Alembic migrations for `orders` and `order_status_history`.

#### Frontend
- React 18 + TypeScript (strict) on Vite, with `/api` proxied to the backend.
- Sidebar navigation, dashboard, order list, order detail, settings stub.
- Advanced filter panel: search, source, status and date range, seeded from
  the URL and debounced by 300 ms.
- Status editing and a status history timeline on the order detail page.
- Dark mode, persisted in `localStorage`.
- Toast notifications and an error boundary.

#### Allegro integration
- `app/integrations/` with a `MarketplaceAdapter` port; raw marketplace
  payloads never leave the adapter's own package.
- Allegro client against the published contract: refresh-token grant, the
  `application/vnd.allegro.public.v1+json` version header, in-memory token
  caching, and failures separated into not-configured, credentials-refused
  and unreachable rather than one opaque error.
- Mapper from `GET /order/checkout-forms`. `total_amount` reads
  `summary.totalToPay`, since `lineItems[].price` is a unit price excluding
  delivery and `payment.paidAmount` is zero on an unpaid order. Anvero's
  single status is derived from both of Allegro's status axes, with
  cancellation taking precedence.
- Import service matching on `(source, external_id)`, so a re-run updates
  instead of duplicating. An order already present keeps the status the
  operator set.
- `scripts/import_allegro.py`, with exit codes distinguishing a missing
  configuration from refused credentials.
- Unique constraint on `(source, external_id)`; a duplicate now returns 409
  rather than surfacing an IntegrityError as a 500.
- `docs/INTEGRATIONS.md` covering the one-time authorization, both mapping
  tables and the known limits.

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
  SQLAlchemy `Session`. It also cleared orders with a bulk delete, which
  bypasses the ORM cascade and would have orphaned history rows on SQLite,
  where foreign keys are not enforced by default. It now takes `--force` so
  it can run unattended.
- Status history ordering: SQLite's `CURRENT_TIMESTAMP` resolves to whole
  seconds, so two changes within the same second shared a timestamp and
  sorted unpredictably. `changed_at` is now set from Python, with
  microseconds, normalised per dialect.
- `test.db`, `vite.config.js`, `vite.config.d.ts`, both `.tsbuildinfo` files
  and `.claude/settings.local.json` were tracked in Git despite being
  regenerated on every run. Untracked, and the tsconfigs now emit into
  `node_modules` so they stop reappearing.

### ✅ Verification

- 66 backend tests passing.
- `tsc --noEmit` clean; production build succeeds.
- Rate limiting: 5 requests return 401, the 6th returns 429.
- Search, combined filters, date range and `PATCH` confirmed in the browser
  against live data, each read back independently from the API.
- Typing 10 characters into search issues one request, not ten.

### ⚠️ Not verified

The Allegro client and mapper have never touched the live API. They follow
Allegro's published documentation and are tested against recorded payload
shapes, which catches mapping mistakes but not a contract that differs from
its documentation. The refresh token also expires after about three months
and there is nowhere to persist a rotated one, so the integration needs
re-authorizing by hand until the `integration` table exists.

The application runs on SQLite. Nothing here has been exercised against
PostgreSQL, and two areas are likely to differ:

- Migrations use `Uuid`, `Numeric` and `Enum`; on PostgreSQL `Enum` creates
  a real database type.
- Date filters and the "this week" figure compare timestamps. SQLite stores
  naive datetimes, PostgreSQL aware ones. The repository normalises per
  dialect, but only the SQLite path has been run.

### 📌 Next

- Connect PostgreSQL and re-run migrations and tests against it. The status
  history migration has a PostgreSQL-only branch that has never run.
- Run the Allegro import against a real account.
- Persist marketplace credentials and rotated refresh tokens, which needs the
  `integration` table.

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
