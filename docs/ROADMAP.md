# Development Plan

## Sprint 1 — Foundation ✅

- Repository structure,
- Product and architecture documentation,
- Local environment setup and diagnostics.

## Sprint 2 — Working Skeleton ✅

- Backend framework selection and configuration,
- Connection to local PostgreSQL database,
- Health endpoint and first order model,
- Minimal order list interface,
- Automated tests for core flows.

## Sprint 3 — Order Flow ✅

- Order list and details,
- Filtering by source, status, and date,
- Change history,
- Sample data.

## Sprint 4 — First Integration ✅

- Secure credential configuration,
- Allegro adapter,
- Order import and mapping,
- Error handling and logging.

Verified against the Allegro Sandbox on 2026-09-17: a real order imported and
re-imported, from the script and from the button. Production Allegro is the
remaining step; see `PROJECT_STATUS.md`.

## After the MVP

The first integration has now been evaluated, which is what the plan waited
for. The MVP's own criterion is all but met: login, list, filters, details,
status with history, and an import that has run against the real API. What
follows is what daily work on real orders needs, in the order it is worth
doing. Each item is a heading in itself, not a sprint plan; scope them when
they come up.

### 1. Allegro in production

The owner's seller account, its own application, its own User-Agent and
authorization, starting from a database with no sandbox orders in it. Until
this runs, everything below is built on one test order.

Afterwards, worth a few hours: **a "Connect Allegro" button in place of the
script.** Allegro's authorization code flow sends the operator to Allegro,
where they log in and consent, and redirects back with a one-time code the
backend exchanges for tokens — the same thing BaseLinker does when it asks
for nothing but a click. It needs a redirect URI registered with the
application, so first check whether Allegro accepts a `localhost` one; if it
does, this is one endpoint and a settings screen. The client id and secret
are still entered once, because the application is the owner's: only a hosted
Anvero with an application of its own could hide those, and that belongs with
item 3, not here. Today's device flow keeps working meanwhile, and an
authorization lasts as long as imports keep the token chain alive, so this is
comfort, not a blocker.

### 2. An import that runs without a person

Today a button fetches one page of at most 100 orders, and only when someone
clicks it. Real volume needs every page, incremental sync from Allegro's
order event journal rather than re-reading the same page, and a schedule.
This is what makes the data trustworthy without anyone watching it.

### 3. Somewhere to run, and a way back

Anvero runs on a laptop, started by hand in two terminals, with the database
in a local file that nothing backs up and no procedure restores. Deployment
and backups are a bigger gap than any missing feature: a lost file is lost
order history. Docker was deliberately left out of Sprint 1 (`DECISIONS.md`)
and belongs to this step's decision, along with where it runs and who can
reach it.

### 4. Shipments, so Anvero replaces the panel rather than mirroring it

Carrier and tracking number are not imported at all — Allegro serves them
from another endpoint — and there are no labels or invoices. Without them an
order is handled in Allegro anyway, which undercuts the MVP's own goal of not
switching between panels. Invoicing and courier labels stay out until
shipments themselves are in.

### 5. The interface — a visual pass, once the system works

The interface will be reworked, but deliberately after items 1–3, when
Anvero imports unattended and runs somewhere with backups
(`DECISIONS.md`, 2026-09-17). What it should look like is decided then:
whether the Figma dashboard prototype and the premium-SaaS direction in
`AI_HANDOFF.md` are taken up, whether a component library is worth the
rewrite of ten stylesheets, and what a design pass would cost. Judging that
after real daily use costs least and is most likely to be right.

Until then, nothing decorative, only what makes the screens readable:

- Fixes already visible in use: the order list scrolls sideways with a single
  order in it, badges crowd the status column, and the buyer's email takes a
  third of the row — personal data, on a screen someone leaves open. Cheap,
  and worth doing whenever.
- One pass over `index.css` so colours, spacing, radii and type are defined
  once, in the values already in use. This makes the later restyle a change
  in one place rather than ten.
- ~~The frontend has no tests, only the type-check.~~ Done 2026-09-18: Vitest
  and React Testing Library, wired into the hook and CI, with a first set of
  tests covering `session.ts`, `types/order.ts` and `OrderRow` (`CHANGELOG.md`).
  Still thin — the interface fixes above and any redesign want more component
  tests before they land.
- Every screen is behind a login, so the owner verifies interface work in the
  browser; assistants check the API instead.

### 6. Status transition rules

Any status can be set from any other, so a mistake has nothing to stop it.
The rules are the owner's decision, not a technical one.

### 7. The safety net around the code

~~Tests run only in a local pre-commit hook a fresh clone can miss.~~ Done
2026-09-18: GitHub Actions runs the backend tests on SQLite and on
PostgreSQL 17, the migrations up, down and up, and the frontend type-check and
build on every push (`.github/workflows/checks.yml`). ~~22 lint findings
predate 2026-09-17.~~ Done 2026-09-18: `ruff check backend/` is clean; see
`DECISIONS.md`. Still open: the frontend has no tests at all, only the
type-check, and ruff is not wired into the pre-commit hook or CI, so nothing
stops new findings from accumulating again.

### 8. What real buyer data will demand

The database and `.env` sit in plain text on a developer machine, a buyer's
email shows on the order list, accounts are made by script with no password
reset and tokens cannot be revoked before their eight hours are up.
Acceptable on localhost; not once this is deployed anywhere with real
buyers' data in it. Revisit alongside step 3.

### 9. ERLI

The second marketplace exists in the model and in the source enum, and
nowhere else. Worth doing when Allegro has proved the shape of the work, and
only if selling there.
