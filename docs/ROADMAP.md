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

~~Afterwards: a "Connect Allegro" button in place of the script.~~ Done
2026-09-21, by the device flow rather than the authorization code flow this
paragraph first imagined, so no redirect URI is needed: Settings takes the
application's client id, secret, User-Agent and environment, and a Connect
button shows the link and code and waits for the seller to confirm
(`DECISIONS.md`). The client id and secret are still those of the owner's own
application; only a hosted Anvero with an application of its own could hide
those, and that belongs with item 3.

### 2. An import that runs without a person

~~Today a button fetches one page of at most 100 orders.~~ Done 2026-09-21:
an import pages through everything, the first reaching back seven days and
every later one fetching only what is new or changed since the last that
finished (`DECISIONS.md`). Still only when someone clicks it: what remains is
a schedule, and, if `updatedAt` filtering ever proves too coarse, the order
event journal. This is what makes the data trustworthy without anyone
watching it.

### 3. Somewhere to run

~~The database and a way back~~ Done: PostgreSQL lives on the NAS, dumped
nightly and copied encrypted to Google Drive by Hybrid Backup Sync, and a
restore from that copy has been tried (`DECISIONS.md`, `DEVELOPMENT.md`).
What remains is the application itself: it still runs on a laptop, started by
hand in two terminals, so nothing runs unattended (item 2 needs a process that
stays up). Docker was deliberately left out of Sprint 1 (`DECISIONS.md`) and
belongs to this step's decision, along with where it runs (the NAS is the
obvious candidate) and who can reach it (Tailscale, HTTPS).

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

Until then, nothing decorative, only what makes the screens readable — plus,
as of 2026-09-18, three additive interface capabilities pulled forward while
production Allegro waits on the owner's own steps (not the redesign above,
which is still on hold; see `DECISIONS.md`):

- Order status can be changed directly from the list (a select styled as the
  existing badge), instead of only from the order page.
- The status-history timeline shows an icon for each entry's status instead
  of a plain dot.
- The order detail view opens as a slide-over above the list instead of
  navigating to a full page, so the list's filters and scroll position
  survive opening and closing an order. `OrdersPage.drawer.test.tsx` covers
  the routing.

And the smaller fixes:

- ~~Fixes already visible in use: the order list scrolls sideways with a
  single order in it, badges crowd the status column, and the buyer's email
  takes a third of the row.~~ Done 2026-09-18: the status column's badges wrap
  instead of forcing the row wide, and the email column is truncated with the
  full address on hover/focus (`DECISIONS.md`). Covered by
  `OrderRow.test.tsx`; not yet checked in a browser — that is the owner's
  step, per the note below.
- ~~One pass over `index.css` so colours, spacing, radii and type are defined
  once, in the values already in use.~~ Done 2026-09-18: named tokens for the
  teal accent, the soft panel/divider greys, headings, two radii, and the
  badge/toast semantic colors, added where the exact same value already
  recurred across files (`index.css`'s `:root`/`:root.dark`, plus
  `.dashboard`-scoped tokens for its status-color pairs). Deliberately not a
  redesign: near-duplicate values that were not byte-identical (e.g.
  `#212529` vs `--color-text`'s `#1a1a2e`) kept separate tokens rather than
  being merged, so nothing renders differently — see `DECISIONS.md`. Checked
  in the browser only on the login page (no login needed there); the
  authenticated pages are the owner's to verify, per the note below.
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
