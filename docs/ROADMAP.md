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

**The order of work from here is set by "Feature plan, modelled on
AlleIntegrator" at the end of this file** (agreed 2026-09-24: build in Anvero,
borrowing AlleIntegrator's ideas; `DECISIONS.md`). The Allegro API survey
below remains the reference for what each of its stages calls.

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
nowhere else. As of 2026-09-24 the owner sells there, so it is no longer
conditional: it is stage A4 of the feature plan below.

## Feature plan, modelled on AlleIntegrator (agreed 2026-09-24)

Built from a walk through a running AlleIntegrator v1.3.36 (its screen map is
the owner's Claude Docs page "AlleIntegrator — mapa aplikacji") and the
owner's answers on how the business works: two channels (Allegro and Erli),
10–50 orders a day, most goods **made to order** (so no stock keeping),
shipping mainly through "Wysyłam z Allegro" with the owner's own courier
contract for exceptions and Erli, and invoices issued by an external
invoicing program, not by Anvero. Items 1–3 above (production Allegro, the
unattended import, the NAS) still stand; stage A1–A3 touch only Anvero's own
data and can proceed alongside them.

### A — Handle the day's orders without the marketplace panels

In this order (the owner chose queues before any write to Allegro):

1. ~~**Work queues and dashboard tiles.**~~ Done 2026-09-24: to make,
   unpaid, to ship and late, sorted newest, oldest or at risk (closest
   dispatch deadline), with dashboard tiles leading into them; a new "ready
   to ship" status, and the dispatch deadline imported (`DECISIONS.md`).
   Whether Allegro actually fills the deadline is unverified.
2. ~~**"To make today" list.**~~ Done 2026-09-24: the "To make" page and
   `GET /orders/production`, the to-make queue grouped by product (SKU, else
   listing, else name) with quantities, the orders each serves and the
   earliest dispatch deadline, most urgent first, printable.
3. ~~**Search and the buyer's other orders.**~~ Done 2026-09-24: search
   also by login, name, company, phone, SKU or product name, city, pickup
   point and tracking number; the order shows the same buyer's other orders
   (same email, or same login on the same marketplace).
4. **Erli order import**, so the queues and the list above cover both
   channels. Started 2026-09-24: the adapter and `scripts/import_erli.py`,
   built from Erli's documentation and tested on fakes (`INTEGRATIONS.md`,
   "Erli"). Since 2026-09-24 the key is entered in Settings and an "Import
   now" button runs it (`DECISIONS.md`). Left: a first run with the owner's
   API key, then a schedule like Allegro's.
5. ~~**Safe mode (dry run).**~~ Done 2026-09-24: `MarketplaceWriter`, the
   switch in Settings (on by default, asks before going off), the log of what
   was or would have been sent, and a banner while it is on (`DECISIONS.md`).
6. ~~**Writing to Allegro:**~~ Done 2026-09-24, through safe mode:
   fulfillment status and tracking number; the last change made in Anvero
   wins (`DECISIONS.md`). Not yet sent for real: try it on the Sandbox with
   safe mode off (`INTEGRATIONS.md`, "Writing to Allegro").
7. ~~**Application status page.**~~ Done 2026-09-24: the Status page and
   `GET /status`: per marketplace, the connection, until when Allegro's token
   is valid, the last import and its outcome (by any route, the scripts
   included), and whether this backend's schedule is running, each with a
   verdict and what to do. Read from what Anvero holds, never a live call
   (`DECISIONS.md`).

### B — Next, in the owner's order of urgency

1. **Labels through "Wysyłam z Allegro"**: buy the shipment, print A6.
   Started 2026-09-24: buying one parcel per order from the order, the A6
   PDF, cancelling, the sender and the usual parcel in Settings, all through
   safe mode, built from Allegro's documentation and tested on fakes
   (`INTEGRATIONS.md`). Printing many at once and ordering a courier: the
   Labels page, done the same day. Cash on delivery is not needed: the
   business does not ship it (`DECISIONS.md`). Left: a first real purchase
   and pickup on the Sandbox.
2. **Buyer messages**: one inbox across channels, reply from Anvero, put a
   thread aside until later. Started 2026-09-24: `message_threads` and
   `messages`, Allegro's Message Center read into a unified inbox, a reply
   sent through safe mode, and putting a thread aside (`INTEGRATIONS.md`,
   "Buyer messages"; `DECISIONS.md`). Built without reading Allegro's
   published OpenAPI specification — this session's network egress could
   not reach `developer.allegro.pl` — so field names beyond what more than
   one other source confirms are flagged unverified rather than asserted.
   Erli is not read: no messaging endpoint was found in its public API.
   Left: starting a new thread from Anvero (only replying to an existing
   one works), attachments, a schedule (only the button runs a sync today),
   disputes, and sending anything for real (safe mode has been on
   throughout, as for the first Allegro status and tracking-number writes).
3. **Invoices and money.** Choose the invoicing program first (compare APIs,
   KSeF support and cost; Fakturownia, wFirma, inFakt are candidates). Then a
   queue of orders waiting for an invoice, issuing through that program, and
   uploading the PDF to Allegro. Money: a period summary of Allegro's fees
   and what is left per order after them.
4. **Returns and claims**: a queue with Allegro's deadlines (14 days to
   decide, 45 to recover the commission) and an alert on the order.
5. **Own courier contract** (InPost ShipX first) for exceptions and Erli.

### C — Later, when daily use asks for it

Merging several orders of one buyer into one parcel; EAN scanning while
packing; rules "condition → action" with a dry run before enabling;
autoresponder and AI-drafted replies; ratings; regular customers; people,
roles and an audit log; notifications (bell, e-mail).

### D — Optional add-ons, not planned

Kept as ideas, not rejected: offer management (bulk edit, description
templates, bundles, copying between accounts, import from file, AI offer
generator, price rules), a product catalogue and stock by SKU with stock
sync, stocktaking, PZ/WZ documents, suppliers and reordering, advertising and
ROAS, other channels (PrestaShop, EmpikPlace, WooCommerce, OLX), Anvero's own
KSeF invoice issuer, and onboarding/help screens.
