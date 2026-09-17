# Changelog

All significant changes to the Anvero project.

---

## 2026-09-17 (Allegro User-Agent)

### 🔒 Allegro calls carry the application's User-Agent

- Allegro blocks an application's key over API calls without its own
  User-Agent, and Anvero was about to send the HTTP library's default one.
  The client and the authorization script now send `ALLEGRO_USER_AGENT` on
  every request, and without it the integration is not configured and sends
  nothing. See `DECISIONS.md` and `INTEGRATIONS.md`, step 2.

### ✅ Verification

197 tests pass (5 new): the header is sent on the token, orders, device and
polling requests, and a missing one stops everything before the network.

## 2026-09-17 (Allegro authorization)

### ✨ Allegro authorization script

- `backend/scripts/authorize_allegro.py` runs the one-time OAuth device flow:
  it prints the link to confirm on Allegro, polls until it is confirmed, and
  writes the refresh token to `ALLEGRO_REFRESH_TOKEN` in `backend/.env`
  without printing it. It follows `ALLEGRO_AUTH_URL`, so it works for the
  sandbox and production alike.
- `.env.example` and `INTEGRATIONS.md` now describe the sandbox URLs, the
  script, and that sandbox orders must not be carried into production.

### ✅ Verification

192 tests pass (17 new), covering waiting, `slow_down`, a declined or
expired authorization, refused credentials and an untouched `.env` on
failure. Run against the real sandbox with a made-up client id, the script
reached it and reported the `401 invalid_client` as refused credentials. A
real authorization still needs the registered sandbox application.

## 2026-09-17 (last)

### 🔒 Security — no personal data or tokens in logs

- SQL echo followed `DEBUG`, on by default, and printed every statement's
  values: buyers' personal data and Allegro refresh tokens. It is now a
  separate `SQL_ECHO` setting, off by default, and the engine hides values
  always, in the echo and in database error messages alike.
- The access log wrote full request URLs, including search terms such as a
  buyer's email. It now logs the path and marks a dropped query string as
  `?...`.

### ✅ Verification

175 tests pass on PostgreSQL and on SQLite (7 new). With value hiding turned
off, three of the new tests fail. A server started with `SQL_ECHO=true` was
sent an order search containing an email and a login attempt: the log showed
the statements with `[SQL parameters hidden due to hide_parameters=True]` and
`GET /api/v1/orders?...`, and neither email.

## 2026-09-17 (late night)

### ✨ PostgreSQL connected (closes Sprint 2)

- The application runs on PostgreSQL 17.10 on the main machine, in its own
  `anvero` role and database. Setup, including recovering a forgotten
  `postgres` password, is in `docs/DEVELOPMENT.md`, "Using PostgreSQL".
- `TEST_DATABASE_URL` runs the test suite on PostgreSQL, in a separate
  database; the suite refuses to start if it names the application's
  database. Without it the suite still uses SQLite.
- The service tests now use a shared `session` fixture on the suite's
  database, instead of each creating an in-memory SQLite that bypassed
  PostgreSQL even when the rest of the suite ran there.

### 🐛 Fixed

- Rolling back the orders table migration left the PostgreSQL enum types
  `order_source` and `order_status` behind, so migrating up again failed with
  "type already exists". The downgrade now drops them.
- Two import tests compared timestamps by forcing UTC onto them, which only
  works for SQLite's zone-less values; PostgreSQL returns them in the
  connection's zone. The application code was already correct.

### ✅ Verification

On PostgreSQL 17.10: all 9 migrations up, down to base and up again twice,
`alembic check` reports no drift; 168 tests pass; sample data generates with
item totals matching order totals; the API starts, answers health, refuses
anonymous requests and runs the login query. The same migration cycle and the
168 tests also pass on SQLite. The project owner then created an account on
PostgreSQL, logged in, opened an order with its details and changed its
status, with the history recording the change and its author.

### 🎨 Order page layout

- The order page had no padding and no width limit: on a wide monitor its
  cards sat against the sidebar and an item's price ended up far from its
  name. It is now padded like the other pages and at most 1100px wide.
  Measured in the app's shell at 1009px and 2100px wide with no horizontal
  overflow; on a phone, where the collapsed sidebar leaves about 300px, the
  items table scrolls inside its card rather than widening the page.

## 2026-09-17 (night)

### 🔒 Security — frontend dependencies

- `npm audit` reported 4 vulnerabilities (1 high, 3 moderate); it now reports
  none. Vite 5 → 8 with `@vitejs/plugin-react` 4 → 6, which also removes
  esbuild from the tree, and React Router 6 → 7. See `DECISIONS.md`.
- The frontend now needs Node.js 20.19+ or 22.12+, declared in
  `package.json` `engines` and checked by `scripts/doctor.ps1`, which now also
  checks that `frontend/node_modules` exists.
- After pulling this on another machine, run `npm install` in `frontend/`.

### ✅ Verification

`tsc --noEmit` is clean and `npm run build` succeeds. In the browser with the
dev server on Vite 8: opening a protected order page while logged out leads to
the login page, the page it came from is kept in router state for the return,
and the console shows no errors or warnings (the React Router v7 future flag
warnings are gone). The logged-in pages were not opened, since that needs a
login.

## 2026-09-17 (evening)

### ✨ Added — Order details

- Orders now store and show their items, buyer, delivery address and pickup
  point, payment and invoice details, and the buyer's message: MVP item 3.
  New tables `order_items` and `order_addresses`, new columns on `orders`
  (migration `e4a7c2d9f5b1`). Existing orders simply have no details.
- The Allegro import maps all of them, with field names checked against
  Allegro's OpenAPI specification, and a re-import replaces them. Details are
  read leniently: one that cannot be read is logged by field name and left
  out, and the order is still imported.
- `GET /api/v1/orders/{id}`, `PATCH .../status` and `POST /api/v1/orders`
  return the order with its details; the list stays lean. See `docs/API.md`.
- The order page shows an items table with item, delivery and order totals,
  and cards for the buyer, delivery, payment state and invoice.
- Sample data includes details, so the page has something to show.

### 🐛 Fixed

- A line item that was not a JSON object made the Allegro mapper raise
  `AttributeError`, which escaped the per-order skip and lost the whole import
  page. Malformed `buyer`, `summary` and `fulfillment` values had the same
  weakness.

### ✅ Verification

168 backend tests pass (137 before; the new ones cover the mapping of every
detail, lenient handling of malformed ones, storing and replacing them on
re-import, and the API shape). The migration was run up, down and up again
on a copy of a development database with existing orders, and `alembic check`
reports no drift from the models. Replacing an address on re-import needs the
old rows flushed before the new ones are added; removing that flush makes two
tests fail on the unique constraint. `tsc --noEmit` is clean. The details
panel was checked in a browser, rendered from real API responses, at desktop
and phone width and in dark mode; the logged-in order page itself was not
opened, since that needs a login. Nothing has been imported from the live
Allegro API.

## 2026-09-17 (later)

### ✨ Added — Allegro import as an endpoint

- `POST /api/v1/integrations/allegro/import` and
  `GET /api/v1/integrations/allegro`, both behind the same login as every
  orders endpoint. The status endpoint returns only `{"configured": bool}` —
  never a credential, token or part of one.
- An "Import from Allegro" button on the Orders page: disabled with a
  configuration hint when Allegro is not configured, "Importing..." while a
  request is in flight, a success toast with the created/updated counts, and
  a second warning toast only when the import found orders newly cancelled
  on the marketplace. The list refetches on success.
- `app/services/allegro_import.py` holds the wiring `scripts/import_allegro.py`
  used to build inline, so the script and the endpoint share one place that
  constructs the database-backed refresh token store; a second copy would
  read the current token but have nowhere shared to persist a rotation.
- A non-blocking lock limits the import to one at a time: Allegro rotates
  the refresh token on every use, and two imports refreshing it together
  would race, leaving the loser with an already-dead token. A concurrent
  attempt gets `409`. The import endpoint is also rate limited, 6 per minute
  per IP, since it makes outbound calls to a third party on the caller's
  behalf.
- `docs/API.md`, `docs/INTEGRATIONS.md` and `docs/DECISIONS.md` updated to
  match; the script is unchanged and still works.

### ✅ Verification

136 backend tests pass (122 existing + 14 new, covering auth, the status
response shape, a successful import, all three error mappings, request
validation, the lock refusing a concurrent import, and the lock releasing
after a failed one so the next import can still run). `tsc --noEmit` is
clean. The new tests replace the service factory with a fake — nothing here
has called the real Allegro API, and this machine has no credentials to call
it with; see "Not yet verified" in `PROJECT_STATUS.md`.

### 🔧 Review follow-ups

- `tests/conftest.py` blanks `ALLEGRO_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN`,
  so a future test that forgets to patch the builders cannot use a
  developer's real credentials: one refresh would rotate the real token into
  the test database and kill the developer's chain. A test checks it (137
  tests).
- The Orders page no longer says "Allegro is not configured" when the status
  request itself failed; it says the connection could not be checked.

---

## 2026-09-17

### ✨ Added — Login (MVP item 1)

- Login page; every page and every `/api/v1/orders` endpoint requires a
  login. Going to a page while logged out leads to the login page and back to
  that page afterwards. An expired token ends the session everywhere at once.
- The sidebar shows the logged-in user's email and a log-out button.
- The status history records and shows who made each change.
- `backend/scripts/create_user.py` creates accounts; there is no sign-up.
- Tokens last `ACCESS_TOKEN_EXPIRE_MINUTES`, default 480 (a working day).

### 🔧 Fixed — before the login could mean anything

- The token signing key shipped as `CHANGE_ME`, with an empty default; anyone
  knowing it can forge a login. The API now refuses to start without a
  strong key, and `bootstrap.ps1` generates one per machine.
- `POST /users/register` let anyone create an account. Removed.
- A deactivated account was issued a token at login. It is now refused.
- An unknown email was answered faster than a wrong password, revealing which
  emails have accounts. Both now take comparable time and get the same answer.
- `create_user.py` stored the byte-order mark Windows PowerShell adds to piped
  text as part of the password, so such an account could never log in. Found
  while verifying the login end to end.
- A relative SQLite path such as `sqlite:///./test.db` was resolved against
  the current directory, so a script started from the project root would
  silently create and use a new, empty database there. It is now resolved
  against `backend/`. Found when creating the first real account from the
  wrong directory.

### 🔧 Fixed — Allegro integration (found by code review)

- **The import worked only once.** Allegro returns a new refresh token on
  every refresh and invalidates the used one about 60 seconds later; the
  client discarded the new one and re-read `.env`, so the second run was
  refused. Rotated tokens are now stored in `integration_credentials` the
  moment they are issued. A new token in `.env` is recognised as a fresh
  authorization. The 2026-09-16 entry's claim that the token lasts about three
  months was wrong once the token had been used.
- An order failing the domain model's validation (e.g. an email it rejects)
  raised pydantic's `ValidationError`, which bypassed the per-order skip and
  lost the whole page. It is now skipped and logged by field name.
- A 200 response that is not a JSON object ended the import in a traceback;
  it is now reported as the integration being unavailable.
- **A cancellation on Allegro disappeared without trace** for an order already
  in Anvero, so it could be shipped anyway. The status is still left to the
  operator, but the order is now flagged: a warning in the import output, a
  dashboard banner with a link, a row marker and filter in the order list, and
  a "do not ship" banner on the order page. The flag clears when the status is
  set to `CANCELLED`. Checked in the browser end to end, light and dark.
- **Imported orders were dated at import time.** A backfill would have made
  every order "this week" and date filters useless. Orders now have
  `ordered_at`, filled from Allegro's earliest `lineItems[].boughtAt`, and
  filters, sorting and `this_week` use it. Existing orders were backfilled
  from `created_at`.

### 🔧 Fixed — dates and times

- **Every time in the interface was two hours early.** SQLite returns
  timestamps without a zone and the API passed them on that way, so browsers
  read UTC as local time. All API timestamps now go out marked as UTC (`Z`).
  Checked against the system clock: a status change at 09:46:43 now shows as
  09:46:43.
- **Date filters used UTC days**, so in Poland a day ran from 02:00 to 02:00
  and an order placed at 01:30 counted as the day before. Filters now use
  calendar days in `BUSINESS_TIMEZONE`, default `Europe/Warsaw`.
- The order list sorted only by timestamp, and many orders share one at the
  database's resolution, so pages could repeat or skip rows. Ties are now
  broken deterministically.

### ✨ Added

- Pre-commit hook in `.githooks/`: backend tests for commits touching
  `backend/`, frontend type-check for commits touching `frontend/`, nothing for
  the rest. Enabled per clone by `bootstrap.ps1`. Checked against a valid and
  an invalid change on each side, and against a commit touching neither.
- `CLAUDE.md`, read automatically by Claude Code at the start of every session
  on every machine. It points at `docs/` rather than repeating it, and records
  the Windows environment traps met so far.

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
