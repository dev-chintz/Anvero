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
finished (`DECISIONS.md`). And a schedule, done 2026-09-21
(`ALLEGRO_IMPORT_INTERVAL_MINUTES`, off by default, on for one backend per
database), with the outcome of the last import shown on the orders page.
What remains is, if `updatedAt` filtering ever proves too coarse, the order
event journal, and running the backend somewhere that stays up (item 3): a
schedule only runs while the process does.

### 3. Somewhere to run

~~The database and a way back~~ Done: PostgreSQL lives on the NAS, dumped
nightly and copied encrypted to Google Drive by Hybrid Backup Sync, and a
restore from that copy has been tried (`DECISIONS.md`, `DEVELOPMENT.md`).
What remains is the application itself, which still runs on a laptop, started
by hand in two terminals, so nothing runs unattended (item 2 needs a process
that stays up). Prepared 2026-09-21: containers for the NAS, published by
GitHub Actions, reached over the home network and Tailscale
(`DEPLOYMENT.md`, `DECISIONS.md`). Not done until the first deployment has
actually run.

### 4. Shipments, so Anvero replaces the panel rather than mirroring it

Carrier and tracking number are not imported at all — Allegro serves them
from another endpoint — and there are no labels or invoices. Without them an
order is handled in Allegro anyway, which undercuts the MVP's own goal of not
switching between panels. Invoicing and courier labels stay out until
shipments themselves are in.

#### What Allegro's API offers beyond this (surveyed 2026-09-21)

From Allegro's developer documentation (the overview and the orders tutorial),
read but never run. Endpoints marked *from memory* were not in what was read
and must be confirmed before building on them.

**Started 2026-09-21:** reading shipments and carrier tracking (the first two
"Read" items below), shown in the list's Shipping column and on the order.
Also started 2026-09-21: **billing entries**, Allegro's fees per order, shown
on the order as "Marketplace fees" (not yet checked against real data).
Everything else here is still to do.

**Two-way today: none.** Anvero only reads. A status changed here never
reaches Allegro; it goes one way, Allegro to Anvero.

Read, not yet used:

- **Order events**, `GET /order/events`: bought, filled in, ready for
  processing, cancelled by the buyer, auto-cancelled, fulfillment status
  changed; last 60 days only. More exact than polling `updatedAt`, and it
  names *why* an order was cancelled.
- **Shipments**, `GET /order/checkout-forms/{id}/shipments`, and carrier
  tracking, `GET /order/carriers/{id}/tracking?waybill=`: carrier, waybill,
  status history (60 days, at most 20 waybills per request). Fills the empty
  "Shipping" column.
- **Buyer messages** (`/messaging/...`, *from memory*), **returns**
  (`/order/customer-returns`) and **disputes/claims**: an alert on an order
  with an open case.
- **Billing and payments** (`/billing/billing-entries`, payment operations):
  Allegro's fees and refunds per order, so the real margin, not just the sale.
- Offers (stock, prices) and ratings: outside order handling.

Write, what could be sent to Allegro:

1. **Fulfillment status**, `PUT /order/checkout-forms/{id}/fulfillment`
   (NEW, PROCESSING, READY_FOR_SHIPMENT, SENT, READY_FOR_PICKUP, PICKED_UP,
   DELIVERED, CANCELLED). Closes the loop: work an order in Anvero only.
2. **Tracking number**, `POST /order/checkout-forms/{id}/shipments` (carrier
   id and waybill); Allegro then notifies the buyer.
3. **Invoices**, `POST .../invoices` and the PDF upload (10 per order, PDF up to
   3 MB).
4. **Messages to the buyer** and replies in disputes.
5. **Refunds**, `POST /payments/refunds`, full or partial, with a reason.
   Real money: needs an explicit confirmation in the interface.
6. **Courier labels**, "Wysyłam z Allegro" (`/shipment-management/...`, *from
   memory*): create and cancel shipments, labels, pickups. Needs an active
   carrier contract on Allegro's side.
7. Offers: price, stock, publish and unpublish. A large area of its own.

Suggested order: 1 and 2 together with importing shipments and tracking (that
is item 4 itself), then billing entries for margin, then messages and case
alerts, and invoices and labels last, since they add contracts and formats.

Cautions before any write:

- **Scopes.** Writing needs OAuth scopes the application must carry, and the
  account must be connected again in Settings to grant them. Which scopes the
  current connection requests was not checked; a first write may be refused.
- **Real consequences** (buyer notifications, invoices, money): each feature is
  tried on the Sandbox first, and refunds and messages get a confirmation step.
- **Who wins.** Status already follows Allegro when it moves
  (`DECISIONS.md`); sending statuses back needs a rule for two changes at once,
  decided before it is built.

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
