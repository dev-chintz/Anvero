# Decision Log

## 2026-09-21 — Orders Get Anvero's Own Continuous Number

**Decision:** Every order has `order_number`, an integer taken from a counter
when the row is created, unique across all sources, never changed or reused,
shown as `AN-000123` (`order_label`, computed where the API serialises it).
Numbering happens in a SQLAlchemy `before_insert` listener on `Order`, so the
API, an import and the sample-data script all get it without each remembering
to. The counter is a row in a new `counters` table, incremented in the same
transaction as the insert. Migration `f7a2c4e8b613` numbered existing orders by
purchase date, oldest first. The number is the first thing in the list's Order
cell (the marketplace's id sits beneath it), a field in the order page, and
searchable in any form a person types it (`AN-000123`, `an-123`, `123`). A
first import stores its orders oldest purchase first, so numbers follow when
orders were placed rather than the order Allegro's pages arrive in (newest
first); that means a run now fetches every page before storing any.

**Rationale:** The owner wanted numbering for internal needs, and Allegro's and
ERLI's order ids are neither ours nor comparable. The choices, all the owner's
to reverse: one continuous sequence rather than per source or per year, so a
number identifies an order on its own and needs no reset; prefix and padding
kept out of the database so the look can change without a migration; existing
orders numbered rather than left blank, so no order lacks one. A plain
autoincrement column was not an option: it is only allowed on the primary key,
which is a UUID, and the tests also run on SQLite. Incrementing the counter
row before reading it holds its row lock on PostgreSQL until commit, so two
orders created at once cannot get the same number; the cost is that they
serialise, and that a rolled-back insert can leave a gap, which an internal
number tolerates. It is deliberately not an accounting document number:
invoices need their own gapless numbering, usually yearly, which belongs with
the invoicing work (`ROADMAP.md`, item 4) and should not be conflated with this.
The migration was run with data on both PostgreSQL and SQLite, up, down and up
again, with `alembic check` clean.

## 2026-09-21 — Allegro Is Connected From Settings, by the Device Flow

**Decision:** Settings has an Allegro section: environment (sandbox or
production), client id, client secret and User-Agent, saved to a new
`integration_settings` table (migration `e6c1d9a4f725`), and a Connect
account button. Connecting runs the OAuth device flow that
`scripts/authorize_allegro.py` already used, driven from the page: the
backend asks Allegro for a link and code and returns them, the page shows
them and polls `GET /integrations/allegro/connect/{flow_id}` on Allegro's
interval until the seller has confirmed in their own logged-in browser; the
token is then stored, and `GET /me` is read once to label the account
(`integration_credentials.account_login`). Credentials entered there are used
instead of the `ALLEGRO_*` variables; with none, the environment applies as
before. One account: reconnecting replaces it.

**Rationale:** The owner asked for the account to be added from Settings
rather than by editing keys into `.env`. The device flow needs no redirect
URI, no callback route and no public address, which the authorization code
flow would (the roadmap's earlier plan, left open on whether Allegro accepts
`localhost`); the flow class was already written and tested, and only had to
be split into a single-step poll. Entering the client id and secret in
Settings too, chosen by the owner over a button alone, means they are stored
in the database as plain text, the same exposure as the refresh token beside
it and as `.env`; the secret is write-only: the API never returns it and the
form shows "Unchanged". A token belongs to one application in one
environment, so changing the client id or the environment disconnects the
account, whether the previous credentials came from Settings or `.env`;
connecting always clears the sync point, since the account may be another
seller's. The sign-in in progress is held in the server's memory, not the
database: it lives for minutes and holds a device code that is worthless
afterwards, at the price that a restart mid-sign-in means starting again and
that it assumes one server process, as the import lock does. Polling faster
than Allegro's interval never reaches Allegro, and completing a connection
takes the same lock an import holds (it refreshes the token once, to read the
login), answering "pending" rather than racing it. Known gap: a token still
in `ALLEGRO_REFRESH_TOKEN` is not something Disconnect can remove; it has to
go from `.env` too. Not tried against the real Allegro yet: the flow is
covered with a fake Allegro, and `GET /me` needs no scope the orders one does
not, but that is documentation, not an observation.

## 2026-09-21 — The Anvero Status Follows Allegro

**Decision:** Reverses three earlier decisions ("An Import Never Overwrites the
Anvero Status", "The Marketplace Status Is Shown, Not Applied", "Marketplace
Cancellations Warn, They Do Not Change Status"), at the owner's request: when
an import finds that the status Allegro reports for an existing order has
moved, the Anvero status moves with it, and the transition is recorded in the
status history with no author. "Moved" means the mapped marketplace status
differs from `orders.marketplace_status` as stored by the previous import - not
that it differs from the Anvero status. A cancellation on Allegro now sets the
order to `CANCELLED`, and still counts in `cancellation_warnings` when it takes
an active order there, so the toast and the import output keep saying so.

**Rationale:** The owner wants the status to be the same as on Allegro, and
because Anvero does not write statuses back, Allegro is the only place a
marketplace-driven change can come from. Comparing against the previous
marketplace status rather than the Anvero one is the narrower reading that
still delivers that: an import that only sees the order again (any other field
changed on Allegro, or the incremental sync picking it up for a new address)
leaves a status the operator set by hand alone, so inline editing in the list
is not undone by the next click on "Import from Allegro". The cost, chosen
knowingly: when Allegro *does* move, it overrides the operator's status,
including backwards (an order marked SHIPPED here, then moved to PROCESSING on
Allegro, returns to CONFIRMED), and an order that already differed before this
change stays as it is until Allegro moves. If that proves too blunt, the
alternative is to apply only forward moves, or to write statuses back to
Allegro (`PUT /order/checkout-forms/{id}/fulfillment`), which would make the
two genuinely one status. The history entry names no one, so it reads like a
pre-login entry; a "changed by import" marker would need a column and was left
out.

## 2026-09-21 — Import Is a Time Window, Then Only What Changed

**Decision:** An Allegro import no longer reads one page of the newest 100
orders. The first one (no sync point recorded) fetches orders bought in the
last `ALLEGRO_INITIAL_IMPORT_DAYS` days, default 7 (`lineItems.boughtAt.gte`);
every later one fetches orders changed since the recorded point
(`updatedAt.gte`), so new orders and updates to old ones arrive together. Both
page through everything. The point lives in
`integration_credentials.last_synced_at` (migration `d5b8e2f7a391`), is the
start of the last complete run less five minutes, and moves only after every
page was fetched and stored. Re-authorizing clears it. The endpoint lost its
`limit`/`offset` body; the script's `--limit`/`--offset` became `--days N`, a
backfill that ignores the recorded point. `import_orders` (one raw page) is
kept for callers that want exactly that.

**Rationale:** The owner asked for seven days on the first import and only
changes after that. `updatedAt.gte` was chosen over Allegro's order event
journal because the orders endpoint the import already reads supports it, so
no second resource and no event-to-order lookup; the journal remains the
answer if that proves too coarse. The point is set to when the run *started*,
not when it ended, and overlapped by five minutes, because an order changed
while a run is in progress must land in the next one, and Allegro's clock is
not ours; the price is a few repeated orders, which matching on `(source,
external_id)` makes free. A run that fails part way deliberately leaves the
point alone: the pages already stored are kept, and the next run repeats
them. No sort is requested, so paging by offset uses Allegro's default (newest
purchase first): a purchase time never changes, whereas sorting by update time
would let an order updated mid-run jump to the end and shift the rest down
one, skipping an order. Paging ends on the first *raw* page shorter than 100,
not the first mapped one, since an unmappable order is dropped from a page and
counting what is left would stop the run early. Running past 500 pages raises
instead of ending quietly, so an incomplete sync is never recorded as
complete. Resetting the point on re-authorization matters for the planned move
from the sandbox to production: another seller account has another order
history, and carrying the old point over would skip its orders.

Known edge: an order bought before the first window and changed later arrives
as a new order, since `updatedAt` cannot tell "new to Anvero" from "new to
Allegro". Not checked against the real API yet (the sandbox has few orders):
the filter parameter names come from Allegro's published documentation, and
the tests cover the request format with a mock transport.

## 2026-09-18 — One Shared PostgreSQL on the Home NAS

**Decision:** The development database is now a single PostgreSQL 17 on the
owner's QNAP NAS (TS-251B, container `postgres:17` run from Container
Station, database and role `anvero`, data in a Docker named volume). Every
machine points `DATABASE_URL` in its own `.env` at it. The SQLite file on
this machine was copied into it once (users, orders, items, addresses and the
Allegro credentials row) and is no longer used. `TEST_DATABASE_URL` stays a
local database: the API tests drop all tables on teardown and must never run
against the shared one.

**Rationale:** Until now each machine had its own database, and the Allegro
refresh token, which rotates on every use, tied imports to one machine. A
shared database removes both problems, and the target was PostgreSQL anyway.
The NAS costs nothing and keeps the data at home; a hosted free tier (Neon,
Supabase) was the alternative.

**Consequences:** The NAS must be reachable: on the home network by its LAN
address, elsewhere only through a VPN (Tailscale), never by forwarding port
5432 on the router. A second container in the same Container Station app
(`prodrigestivill/postgres-backup-local:17`) runs `pg_dump` nightly (about midnight) into the
NAS shared folder `anvero-backup` (7 daily, 4 weekly, 3 monthly kept). The NAS
has a single disk, so those dumps do not survive its failure: a Hybrid Backup
Sync job copies the folder every day at 03:00 to a Google Drive account made
only for this, with client-side encryption (`.qdff`, readable only through HBS
or QNAP's decrypt tool, with the encryption password). The first dump was
restored into a scratch database twice, from the NAS folder and from the
Drive copy through an HBS restore job, and the row counts matched. The
encryption password must be kept outside the NAS: HBS does not ask for it when
restoring from its own job, so that test does not prove it is remembered. The
connection string holds the password and stays out of Git.

## 2026-09-18 — Item Pictures: a Second Allegro Call per Offer, Best-Effort

**Decision:** `AllegroClient` gained `fetch_offer_image(offer_id)`, calling
`GET /sale/product-offers/{offerId}` and returning the first entry of its
`images` array — confirmed to exist by expanding the real response sample on
developer.allegro.pl before writing any code, since the checkout-form
resource the import already reads has no picture field at all.
`AllegroAdapter.fetch_orders` calls it once per distinct `offer_id` on the
page (not once per line item) and sets `OrderItemCreate.image_url`, a new
nullable column on `order_items` (migration `c3e9a1f5b276`). Unlike
`fetch_checkout_forms`, this method never raises: a 404, a 403, a network
error or a non-JSON response all just return `None`, logged as a warning.
The order page shows the picture as a small thumbnail next to the item name,
scaling up in place on hover.

**Rationale:** A missing picture is not a reason to fail an otherwise-valid
order, so the leniency already established for optional fields
(`buyer_message`, `seller_note`) extends here too — the difference is that
this failure mode is a second network call rather than a malformed value in
a payload already in hand. Deduplicating by `offer_id` within one page
matters because the same offer commonly appears across several orders; without
it, a page of 100 orders could mean 100 extra calls instead of however many
distinct offers actually sold. Whether the application's current authorization
carries the scope this endpoint needs is unverified - `GET
/sale/product-offers/{offerId}` is public product data and should not need
more than what listing orders already required, but this is confirmed only
by trying it against the sandbox, not by reading documentation alone; if it
returns 403, every item simply keeps no picture until that is resolved, since
the method was built not to raise. The thumbnail scales in place on hover
(one `<img>`, CSS `transform`) rather than opening a second, separately-
fetched preview image, which keeps the implementation to CSS only; the
tradeoff is that the enlarged image can clip against `.order-items-scroll`'s
scrollbar on a narrow screen, judged acceptable since the item name stays
readable there regardless.

Verified with the client's own test double (`httpx2.MockTransport`) covering
the picture, no-picture, 404, 403, network-error and non-JSON-response
cases, the adapter's deduplication across two orders sharing an offer, and
the existing API detail-response test extended to check `image_url`. 221
backend tests passing, ruff clean; frontend `tsc --noEmit`, 32 tests, `npm
run build` all clean. Not checked in a browser or against the real API - the
sandbox check is the next step, and will show directly whether the scope
question above is actually a problem.

## 2026-09-18 — Order List Reshaped Toward BaseLinker's Layout, Narrower Sidebar

**Decision:** The owner asked for the order list organized more like
BaseLinker's, sidebar included. Two columns became one: External ID, Source
and the buyer's email are now a single "Order" cell (external ID linked,
buyer name below it, source badge below that), dropping the raw email from
the list entirely — it is still on the order page. A new "Payment" column
shows `payment_type`/`payment_provider`, already stored per order and now
also returned by `GET /orders` (`OrderRead` gained `customer_login`,
`customer_first_name`, `customer_last_name`, `payment_type`,
`payment_provider` — flat columns on `orders`, so free to add). "Items" and
"Shipping" columns exist too, but empty (an em dash, a placeholder box where
a thumbnail would go): Anvero has neither product images nor carrier data
(`ROADMAP.md`'s "Shipments" item), and the owner asked for the row's eventual
shape to be visible now rather than added as a second layout change later.
`.sidebar.open` narrowed from 250px to 200px (`.app-content`'s margin-left
in `App.css` kept in sync).

**Rationale:** A literal copy of BaseLinker's list is not possible today —
its thumbnails, carrier badges and quick-action icons (print label, print
invoice) all need data or features Anvero does not have, confirmed before
starting rather than guessed. What's shown was chosen by what is genuinely
free: `customer_first_name`/`last_name`/`login` and `payment_type`/
`payment_provider` are already columns on the same `orders` row `GET
/orders` reads, so exposing them costs nothing — unlike `items`, which is a
separate table and would need a join or a second query per page. Dropping
the buyer's email from the list (shown only as a fallback when there is no
name or login) continues the same privacy reasoning as the 2026-09-18 order-
list readability fixes: it is personal data on a screen someone can leave
open, and the buyer's name identifies them well enough for the list to be
useful. The empty Items/Shipping columns are placeholders, not stubs meant
to look functional — no fake action icons, since a button that does nothing
when clicked reads as broken, while an empty cell or a grey box reads as
"not built yet."

Verified with `tsc --noEmit`, `npm run build`, and updated
`OrderRow.test.tsx`/`OrdersPage.drawer.test.tsx` covering the buyer-name
fallback chain (name → login → email) and the payment/placeholder cells.
Backend: `test_the_list_already_carries_the_buyer_name_and_payment_method`
in `test_orders.py`; 212 tests passing, ruff clean. Not checked in a
browser: every screen needs a login, and that check is the owner's.

## 2026-09-18 — The Seller's Own Allegro Note Is Imported Too

**Decision:** `GET /order/checkout-forms/{id}` — the same resource the
import already reads — carries a `note.text` field: the seller's own note on
the order, written in Allegro's own panel, distinct from `messageToSeller`
(the buyer's note). It is now mapped to a new `seller_note` column, alongside
`buyer_message`, and shown in the order detail drawer as its own card with a
yellow tint, so it is never confused with the buyer's (blue) message.
Read-only, like every imported detail: a re-import refreshes it, and nothing
in Anvero writes it back.

**Rationale:** The owner asked whether a note added to an order on Allegro's
side could be pulled in, the way the buyer's message already is. The field's
existence was confirmed against `developer.allegro.pl`'s own response sample
for this endpoint (Mobbin is blocked for this session's browser, so the
public REST API docs were checked directly) rather than assumed. Since the
import already fetches the full checkout form, this is the same shape of
change as `buyer_message` was: a mapper field, a nullable `Text` column
(migration `a7f3c9e2b418`), and a schema/model/frontend field carried
through unchanged — no new API call, no new permission.

## 2026-09-18 — Three Interface Ideas Built Early, While Allegro Production Waits

**Decision:** With production Allegro blocked on the owner's own steps
(`ROADMAP.md`, item 1), three incremental interface ideas were pulled forward
instead of waiting for the post-MVP visual pass: status changes directly from
the order list, icons on the status-history timeline, and the order detail
view as a slide-over drawer above the list instead of a full-page navigation.
Chosen by the owner, from a short list gathered by browsing public design
references (Dribbble, since Mobbin blocks this session's browser with a 403).

**Rationale:** This is not the redesign `DECISIONS.md`'s 2026-09-17 entry
postpones — each change is additive and keeps the current look, wiring a
capability the backend already has (`PATCH /orders/{id}/status`) or extending
a component that already exists (`OrderHistory.css`'s timeline,
`OrderDetail.tsx`'s page) rather than restyling anything. Doing them now uses
otherwise-blocked time productively without committing to the bigger,
harder-to-reverse visual decisions (Figma prototype, component library) that
are still deliberately on hold.

### Order list: status is a select styled as the existing badge

`OrderRow.tsx`'s status cell is now a `<select>` (`.status-select` in
`index.css`, combined with the existing `.badge-*` class for its color)
instead of a plain span, wired through `OrderList` to
`OrdersPage.handleStatusChange`, which calls the existing
`ordersApi.updateStatus` and refetches the list. Changing status no longer
means opening the order. The three warning/marketplace-status badges next to
it are unchanged.

### Status history: an icon per event's `to_status`

`OrderDetail.tsx`'s status-history timeline marker (`.status-history-item`,
`OrderHistory.css`) was a plain colored dot; it is now a small circle showing
an emoji for the status the entry moved *to* (🆕/✅/🚚/📦/✖), using the same
emoji-as-icon convention the dashboard's stat cards already use
(`Dashboard.tsx`). Purely visual; the underlying data and the badges next to
it are unchanged.

### Order detail: a slide-over, not a page

*Superseded on 2026-09-24: the order is a page of its own again, see "Design agreements" below. What follows is kept as it was written.*

`/orders/:id` is now nested under `/orders` (`App.tsx`) and rendered through
`OrdersPage`'s own `<Outlet>`, so the list stays mounted - its scroll
position and filters survive opening and closing an order. `OrderDetail.tsx`
renders as a backdrop + panel sliding in from the right (`.order-drawer-*` in
`index.css`), closable by its own button, the Escape key, or clicking the
backdrop, all going through `navigate(-1)` rather than a hardcoded
`/orders` so whatever filters were active are still there. Because the list
no longer remounts (and so no longer refetches) when an order's status
changes from inside the drawer, `OrdersPage` passes its `refetch` down via
`useOutletContext` (`OrdersOutletContext`), and `OrderDetail` calls it after
a successful status update - otherwise the row behind the drawer would show
a stale status until the next unrelated refetch. `OrderDetailsPanel.tsx` and
the status-history section inside the drawer are unchanged.

Verified with `tsc --noEmit`, `npm run build`, and a new
`OrdersPage.drawer.test.tsx` covering the nested-route composition (list and
drawer both present), closing via button and Escape, and the refetch-on-
status-change wiring - deliberately the most-tested of the three, since it is
the one restructuring routing rather than only adding to a component. Not
checked in a browser: every screen needs a login, and that check is the
owner's, per `ROADMAP.md`.

## 2026-09-18 — CSS Values Named Once, Not Redesigned

**Decision:** `index.css`'s `:root`/`:root.dark` gained tokens for values that
`App.css` and `styles/*.css` already repeated identically across several
files: `--color-accent` (the teal used for buttons, links and active nav),
`--color-surface-alt` (a soft panel background), `--color-divider` (a soft
border/divider, with its dark value pointing at the existing `--color-border`
since every one of its dark overrides except Sidebar's already matched it),
`--color-heading`, `--color-muted-strong`, `--radius-md`/`--radius-lg`, and
four semantic colors (`--color-success/error/warning/info`) shared by the
order-status badges and the toast types, which already used the same hex
values. `Dashboard.css` additionally gained its own `.dashboard`-scoped
tokens for the five status colors, each of which was written out twice in
that one file (the stats/status-breakdown section and the recent-orders
list).

**Rationale:** `ROADMAP.md`'s interface section asks for exactly this: names
for the values already in use, so a later restyle changes one token instead
of every call site, without redesigning anything now. That constraint drove
every substitution: a value was only replaced with a theme-aware token where
an explicit override already existed for that exact selector and property in
the other theme (so the override keeps winning regardless of what the base
rule's token resolves to), or where the value had no theme-specific override
at all (so a plain token, or none, could not change it). Several near-
duplicate values were deliberately kept apart instead of merged, because they
were not actually the same value to begin with: `#212529` (now
`--color-heading`) is not `--color-text`'s `#1a1a2e`; `#6c757d` is not
`--color-muted`'s `#6b7280`; `#e9ecef` (now `--color-divider`) is not
`--color-border`'s `#e5e7eb`, though its *dark* counterpart turned out to
already match `--color-border` everywhere except Sidebar.css, which uses
`#333` and keeps its own explicit override for that reason. A handful of
`#0d7377` (the light-mode teal) uses were left hardcoded on purpose because
no dark-mode override for that selector ever existed — those elements have
always rendered the same teal in both themes, and pointing them at
`--color-accent` would have made them switch to its dark value, a real visual
change disguised as a rename.

Verified with `tsc --noEmit`, the full test suite, `npm run build` (identical
CSS bundle size before and after), and the login page in a browser in both
themes — the only page that needs no login, per `ROADMAP.md`'s "Every screen
is behind a login" note. The authenticated pages are unverified visually; the
owner checks those.

## 2026-09-18 — Order List: Status Badges Wrap, the Email Column Truncates

**Decision:** In the orders table only (`.orders-table` in `index.css`, set on
the `<table>` in `OrderList.tsx`), the status cell's badges sit in a flex
container that wraps (`.status-cell` in `OrderRow.tsx`) instead of the cell's
inherited `white-space: nowrap`, and the customer-email cell has a 220px
`max-width` with `text-overflow: ellipsis`, with the full address still
available via a `title` attribute on the cell.

**Rationale:** `th, td { white-space: nowrap }` is global, so a status cell
holding up to three badges (status, cancellation warning, marketplace status)
and an unbounded email column together could force a row wider than the
viewport, scrolling the whole table sideways even with a single order in it —
the fix scopes narrowly to `.orders-table` rather than changing the shared
rule, since the item table in `OrderDetailsPanel.tsx` has no such problem and
wasn't touched. Truncating the email rather than hiding it outright keeps it
reachable (hover or keyboard focus shows the title), which is enough given
the concern was screen space, not the address being visible at all — the
screen is already behind a login. Verified with `OrderRow.test.tsx`; not
checked in a browser, since every screen requires a login and that step is
the owner's (`ROADMAP.md`, "Interface" section).

## 2026-09-18 — Frontend Tests Are Vitest + React Testing Library

**Decision:** `frontend/vite.config.ts` gains a `test` block (jsdom
environment, `src/testSetup.ts` for cleanup and jest-dom matchers); `npm run
test` runs Vitest. Tests sit next to the code they test (`session.test.ts`
beside `session.ts`), not in a parallel `tests/` tree, and import
`describe`/`it`/`expect` explicitly rather than turning on Vitest's globals.

**Rationale:** Vitest reuses the project's own Vite config and plugin
pipeline (JSX, path resolution), so nothing needs a second bundler
configuration the way Jest would have; `ROADMAP.md` already named it as the
natural fit. React Testing Library is its ecosystem's standard for asserting
on rendered output rather than component internals. Explicit imports over
globals keep `noUnusedLocals`/`noUnusedParameters` meaningful in test files
and match the rest of the codebase's style of not relying on ambient globals.
React Testing Library's automatic per-test cleanup depends on `afterEach`
being a global, which this setup does not enable, so `testSetup.ts` calls
`cleanup()` explicitly — without it, a component from one test stayed mounted
into the next.

The first tests were chosen for where a silent regression would be worst:
`auth/session.ts` (the try/catch around `localStorage`, including the
private-mode/blocked-storage path) and `types/order.ts`'s
`hasCancellationWarning`, `marketplaceStatusDiffers` and
`marketplaceStatusText`, which are the rules behind the 2026-09-17
marketplace-status decision — pure functions, easy to get subtly wrong, with
a decision on record that explains why each edge case (a cancellation
suppressing the other badge, a missing field reading as "nothing to show")
is the way it is. `OrderRow.test.tsx` renders the same rules to check the
badges actually appear, as a first component test.

## 2026-09-18 — Backend Lint Findings Cleared; FastAPI's `Depends`/`Query` Allowlisted

**Decision:** `backend/pyproject.toml` now exists, holding one setting:
`[tool.ruff.lint.flake8-bugbear] extend-immutable-calls` lists
`fastapi.Depends`, `fastapi.Query`, `fastapi.Path` and `fastapi.Body`. The
other findings (unsorted imports, three `subprocess.run` calls without
`check=`, one broad `except Exception` in `generate_sample_data.py`) were
fixed or, for the broad except, given an explicit `# noqa: BLE001` with a
one-line reason. `ruff check backend/` is now clean.

**Rationale:** All 16 `B008` findings were FastAPI's own dependency-injection
pattern — every endpoint calls `Depends(get_db)` or `Query(...)` as an
argument default, which is what the framework documents and requires. Ruff's
bugbear rule cannot tell that apart from the mutable-default-argument bug it
exists to catch unless told; rewriting working endpoint signatures to dodge a
false positive would have made the code worse, not better. `extend-immutable-
calls` is bugbear's own mechanism for exactly this, so it keeps B008 useful
for any other function while clearing the noise. The three `subprocess.run`
calls are test helpers that already assert on `result.returncode` themselves,
so `check=False` documents that on purpose rather than by omission. The
`except Exception` in the sample-data script is a CLI script's top-level
safety net around a whole run, not a place narrowing to specific exceptions
would help; a `noqa` with a reason was chosen over silencing the rule
project-wide.

Ruff is still not run from the pre-commit hook or from CI, so this only
clears the existing backlog — nothing yet stops a new finding from landing
unnoticed.

## 2026-09-18 — Checks Run on GitHub Actions for Every Push

**Decision:** A GitHub Actions workflow runs on every push and pull request:
the backend tests on SQLite and, in a separate job, on PostgreSQL 17 together
with the migrations up, down to base and up again; and the frontend
type-check and production build. The local pre-commit hook stays.

**Rationale:** The hook guards only a clone where `bootstrap.ps1` enabled it,
and it is skipped by `--no-verify`. Work here comes from several machines and
from both Claude Code and Kiro, so the one place every change passes through
is GitHub. Both databases are tested because they behave differently where it
has already mattered: the enum types a downgrade left behind, and timestamps
returned with or without a zone, showed up only on PostgreSQL. The migration
cycle runs there for the same reason. The frontend job builds as well as
type-checks, since a build can fail on what `tsc` accepts. Node 22 is used
because it is the oldest maintained line `package.json` allows, so a machine
on it is covered; the main machine runs 24. The repository is public, so the
minutes cost nothing.

## 2026-09-17 — The Interface Is Postponed, Not Settled

**Decision:** The visual design is a task for later, after the system works
the way it has to: production Allegro, an import that runs unattended, and
somewhere to run it with backups (`ROADMAP.md`, items 1–3). Until then the
interface is left as built — plain CSS, dark sidebar, blue and teal accents —
and only its legibility faults are fixed. What the redesign should aim at,
including whether the Figma dashboard prototype and the premium-SaaS
direction in `AI_HANDOFF.md` are taken up, is decided when that work starts,
not now.

(Supersedes an earlier wording of this entry, written the same day, which
treated the built interface as final. It was never acted on.)

**Rationale:** The interface does need work — the owner's call — but not
before the things that decide whether Anvero is usable at all. Styling a
system that still cannot import unattended or survive a lost laptop is effort
spent on the visible part of the wrong problem, and the shape of the screens
will keep moving while shipments and an automatic import are added, so
anything designed now would be redesigned anyway. Settling the target later
also costs least: by then the daily work will have shown which screens matter
and how they are actually used, which is exactly what a prototype needs to be
judged against. Meanwhile, nothing claims the current look is the intended
one, so no one has to defend it.

## 2026-09-17 — The Marketplace Status Is Shown, Not Applied

**Decision:** Every import records the marketplace's own status twice: mapped
to Anvero's vocabulary in `orders.marketplace_status`, and unmapped, in the
marketplace's own words, in `orders.marketplace_status_label`. The Anvero
`status` is still only set from the marketplace when the order is first seen.
The order page and the order list show the unmapped value whenever the mapped
one differs from ours, and nothing acts on the difference.

**Rationale:** The first sandbox order made the gap concrete: it was moved to
PROCESSING on Allegro, and Anvero went on showing NEW with nothing to say why
— the operator would have to open Allegro to find out. Syncing the status
instead was rejected for the reason it was rejected before: it silently undoes
a decision the operator made and recorded in the history. Following the
marketplace only until the operator first touches an order was considered and
dropped as well, because whether a status was ever set by hand is a subtle
rule to have to hold in your head when reading a list. Showing both keeps one
owner for the status and still makes the divergence visible, the same shape as
the existing cancellation flag. A cancellation keeps its louder warning and
suppresses this quieter marker, so the same fact is not reported twice.

Showing the mapped value alone was tried first and was not enough: the
sandbox order sat in READY_FOR_SHIPMENT on Allegro while Anvero displayed
CONFIRMED, which is also what PROCESSING maps to, so the marker could not
answer the question it existed to answer. The unmapped value is stored as
Allegro sends it rather than translated, because a table of our own labels
would need maintaining and would drift from the words in Allegro's panel —
the very thing the operator is comparing against. Adding an Anvero status
between CONFIRMED and SHIPPED was the alternative and was dropped: it is a
decision about how the business works, not about the integration, and it
would spread through the enum, the filters, the statistics and the interface.

*Superseded 2026-09-21:* the status now follows the marketplace; see "The Anvero Status Follows Allegro".

## 2026-09-17 — Allegro Calls Require the Application's Own User-Agent

**Decision:** Every request to Allegro, the authorization and token
endpoints included, carries `ALLEGRO_USER_AGENT`: the header generated for
the application on the developer portal, sent verbatim. Without it the
integration counts as not configured and sends nothing, exactly as with a
missing client id.

**Rationale:** Allegro's API terms require each application to identify
itself with its own User-Agent of the form `Name/Version (+URL)`, and the
portal warns that calls without a valid one get the application's key
blocked. The HTTP library's default header would have been sent on the very
first sandbox call. Refusing to call at all is cheaper than a blocked key.
The value comes from configuration rather than being assembled in code
because Allegro matches it against the registered application and asks that
it not be modified; the documentation URL points at the public repository,
the page an outside administrator can actually open.

## 2026-09-17 — Allegro Is Authorized by Device Flow, Token Written to `.env`

**Decision:** The one-time Allegro authorization is a script,
`scripts/authorize_allegro.py`, using the OAuth device flow. It writes the
refresh token straight into `ALLEGRO_REFRESH_TOKEN` in `backend/.env` and
never prints it. The flow itself lives in
`app/integrations/allegro/authorization.py`, next to the client.

**Rationale:** The device flow needs no redirect URI and no callback server,
only a link the seller opens and confirms, which fits a local application
with no public address. Printing the token and asking for it to be pasted
would leave it in the terminal's scrollback and invite pasting it into the
wrong place, such as a chat; writing it where the import already reads it
avoids both. `.env` stays the seed rather than the database, so the existing
chain logic applies unchanged: a new token in `.env` replaces the stored
chain ("Rotated Allegro Refresh Tokens Live in the Database"). Keeping the
HTTP flow in the integrations package lets it be tested with the same mock
transport as the client, and leaves the script to printing and file writing.

## 2026-09-17 — Logs Carry No Values: SQL Parameters Hidden, Query Strings Dropped

**Decision:** The database engine always runs with `hide_parameters=True`,
and SQL echo is its own setting, `SQL_ECHO`, off by default, instead of
following `DEBUG`. The uvicorn access log records request paths without
their query strings.

**Rationale:** `DEBUG=true` is the `.env.example` default, and it turned on
an echo that printed every statement with its values: buyers' names,
addresses, phone numbers and emails, and each rotated Allegro refresh token as
it was stored. That contradicted what `DATABASE.md` and `INTEGRATIONS.md`
promise, and it had to go before real Allegro data arrives. Hiding the values
at the engine rather than only switching echo off also covers database error
messages, which carry values and end up in tracebacks. The access log leaked
the same data another way: searching orders for a buyer's email puts it in
the URL. The statements and paths alone are enough to see what ran; when a
value is really needed, it belongs in a debugger, not a log.

## 2026-09-17 — PostgreSQL Is Connected; the Tests Follow TEST_DATABASE_URL

**Decision:** The main machine runs on PostgreSQL 17, in a database `anvero`
owned by a role `anvero` rather than by the `postgres` superuser. The test
suite runs on PostgreSQL whenever `TEST_DATABASE_URL` is set, in a separate
database `anvero_test`, and on SQLite otherwise. `.env.example` still defaults
to SQLite.

**Rationale:** Only running the code on PostgreSQL could show whether it
works there, and it found a bug SQLite never could: rolling back the orders
migration left its enum types behind, so migrating up again failed. Tests
that ran only on SQLite would let the next such difference through, so on a
machine with PostgreSQL they run there, and so do the service tests that used
to create their own in-memory SQLite. The test database is separate, and the
suite refuses to use the application's, because the tests drop every table.
A dedicated role limits what a leaked `.env` exposes to Anvero's databases.
SQLite stays the default so a fresh clone still runs with no database server,
per the 2026-09-17 SQLite entry below.

## 2026-09-17 — Frontend Moves to Vite 8 and React Router 7

**Decision:** The four `npm audit` findings were fixed by upgrading to the
current majors, Vite 8 (with `@vitejs/plugin-react` 6) and React Router 7,
rather than to the oldest release that clears them. The frontend now needs
Node.js 20.19+ or 22.12+.

**Rationale:** Neither finding had a fix within the installed majors. The
Vite ones are development server issues (another website reading the dev
server's responses through esbuild; on Windows, reading files outside the
project past `server.fs.deny`), which matter here because the dev server runs
on a working machine while its browser visits other sites. The React Router
ones (an open redirect through a backslash in a link target; a server
rendering issue this app does not use) had low exposure: the only redirect
target the app builds comes from router state, not from the URL. Vite 7
would also have cleared them, but it is the previous major, and taking it
would mean a second migration soon for no saving: both need the same Node
version, and the app's Vite configuration is small enough that the move to
Rolldown in Vite 8 changed nothing in it. React Router 7 keeps the v6 API
this app uses; none of its behaviour changes (relative links inside splat
routes, state updates in transitions) touch code here.

## 2026-09-17 — Order Details Are Stored; Unreadable Details Do Not Block an Order

**Decision:** Orders store their items, buyer, delivery (with pickup point),
payment and invoice. Items and addresses are child tables, matching the
`order_item` and `address` targets in `DATABASE.md`; the one-per-order
details are columns on `orders`, as `customer_email` already was. The
marketplace owns all of them, so a re-import replaces them. A detail an
import cannot read is left out and logged by field name, and the order is
imported without it.

**Rationale:** MVP item 3 is an order view with items, customer, shipping
and payment, and until now the import read all of it and threw it away.
Leniency is the opposite of the rule for required fields, and deliberately
so: an order missing its email or total cannot be handled at all, but an order
missing a phone number can still be packed and shipped, and dropping it over
that would hide real work. A `customer` table is not introduced because it
means deciding when two orders share a buyer, which nothing needs yet.
Payment type is stored as a checked string rather than a PostgreSQL enum
type, so adding a marketplace's payment methods does not need a migration.
The buyer's own address and personal identity number are not stored:
delivery and invoice addresses are what a seller uses, and personal data with
no use should not be kept.

## 2026-09-17 — The Login Token Is Kept in localStorage

**Decision:** The frontend stores the access token in `localStorage` and
sends it as a bearer header. Any 401 from an authenticated request clears it
and ends the session for the whole app.

**Rationale:** It survives reloads and new tabs for the token's working-day
lifetime, which is what makes one login per day true. The cost is that any
script running on the page can read it. That is acceptable while the app
renders no third-party scripts and no user-supplied HTML; if either changes,
move to an httpOnly cookie, which also needs CSRF protection. Reacting to a
401 globally, rather than per screen, means an expired token sends the user to
the login page instead of leaving error messages across the app.

## 2026-09-17 — Accounts Are Created by Script; Logins Last a Working Day

**Decision:** There is no registration endpoint; `scripts/create_user.py`
creates accounts. A login token lasts `ACCESS_TOKEN_EXPIRE_MINUTES`, default
480. The API refuses to start unless `SECRET_KEY` is at least 32 characters
and not a known placeholder, and `bootstrap.ps1` generates one per machine.
Chosen by the project owner for registration and session length.

**Rationale:** With open registration, anyone who can reach the API could give
themselves an account, so protecting the orders endpoints would protect
nothing. Eight hours means one login per working day while a stolen token
still dies by evening; tokens cannot be revoked, so longer would widen that
window. The signing key shipped as `CHANGE_ME`, with an empty default, and
anyone who knows the key can sign a token for any user — enforcing it was a
precondition for the login meaning anything.

## 2026-09-17 — Order Date Is Its Own Column; Days Are Business-Timezone Days

**Decision:** Orders have `ordered_at` (when the buyer placed the order)
separate from `created_at` (when the row was made), and filters, sorting and
`this_week` use `ordered_at`. Timestamps are stored and returned in UTC,
always with the zone attached. Calendar dates in filters are days in
`BUSINESS_TIMEZONE`, default `Europe/Warsaw`.

**Rationale:** Imported orders were dated at import, so a backfill of a year's
orders made all of them "this week" and unfindable by date. Overwriting
`created_at` with the purchase time would have lost when the row was created,
which `DATABASE.md` already anticipated needing. Separately, SQLite returns
timestamps without a zone and the API passed them on that way, so browsers
read UTC as local time and every date in the interface was two hours early.
And a filter for "11 September" used UTC midnight, putting the day boundary at
02:00 in Poland. A business timezone setting, rather than the viewer's
browser zone, keeps the answer to "orders from that day" the same for
everyone.

## 2026-09-17 — Marketplace Cancellations Warn, They Do Not Change Status

**Decision:** When an import finds an existing order cancelled on its
marketplace, the Anvero status is still left alone, but the order gets
`marketplace_cancelled_at`. Until the operator sets the status to `CANCELLED`
the order is flagged in the import output, on the dashboard, in the order list
(with a filter) and on the order page. Chosen by the project owner.

**Rationale:** Code review showed the 2026-09-16 decision had a gap: it let a
cancellation vanish entirely, so an operator could ship an order the buyer had
cancelled. Overwriting the status would fix that but break the rule that the
status is the operator's. A warning keeps the rule and makes the conflict
impossible to miss. It is deliberately not auto-dismissed for orders already
shipped, since those still need a return or refund.

*Superseded 2026-09-21:* the status now follows the marketplace; see "The Anvero Status Follows Allegro".

## 2026-09-17 — Rotated Allegro Refresh Tokens Live in the Database

**Decision:** Each refresh token Allegro issues is written to
`integration_credentials` immediately, in its own commit, and read back on the
next run. `.env` only seeds the chain; a stored SHA-256 fingerprint of that
seed tells a re-authorization (different `.env` token) apart from the normal
case, so the fresh token replaces the stale chain.

**Rationale:** Allegro invalidates a refresh token about 60 seconds after it
is used and returns a replacement. The client used to discard the replacement
and read `.env` again, so every import after the first failed and needed a
manual re-authorization. The database was chosen over a token file because
it already holds the data the credential belongs to and is the start of the
`integration` entity in `DATABASE.md`. If the replacement cannot be stored the
run stops with an explicit error, since the old token is already dying.

A consequence for multi-machine work: each machine's database holds its own
chain, so imports should run from one machine.

## 2026-09-17 — Pre-Commit Checks as a Git Hook

**Decision:** Tests and type-checking run from a git pre-commit hook in
`.githooks/`, not from a Claude Code hook.

**Rationale:** Code was committed that did not type-check, and a setup script
was committed that had never run. The check has to catch that whoever
commits: work here alternates between Claude Code and Kiro, and a Claude Code
hook would not see Kiro's commits. The hook checks only the side a commit
touches, so documentation commits are not slowed down.

## 2026-09-17 — SQLite Is the Default Local Database

**Decision:** `backend/.env.example` sets `DATABASE_URL` to a local SQLite
file. PostgreSQL remains the target and stays in the file as a commented
alternative.

**Rationale:** `.env` is git-ignored, so on a new machine it is created from
`.env.example`. Pointing that at PostgreSQL meant a fresh clone failed until a
database server was installed and configured, and even then it would have run
a PostgreSQL migration path that has never been exercised. SQLite lets the
project run from a clean clone with no setup. This does not settle the
production database; connecting PostgreSQL is still the open Sprint 2 item.

## 2026-09-16 — An Import Never Overwrites the Anvero Status

**Decision:** When an import meets an order Anvero already has, it refreshes
the fields the marketplace owns and leaves `status` alone. The marketplace
status is applied only the first time an order is seen.

**Rationale:** `MVP.md` calls the status internal, it is set by hand, and
every change is recorded in the status history. A sync that overwrote it
would silently undo an operator's decision and leave a history entry the
operator did not make. The cost is that a parcel marked sent on Allegro does
not move Anvero by itself — visible, and preferable to destroying local work.

*Amended 2026-09-17:* cancellations are now flagged as a warning; see the
entry "Marketplace Cancellations Warn, They Do Not Change Status".

*Superseded 2026-09-21:* the status now follows the marketplace; see "The Anvero Status Follows Allegro".

## 2026-09-16 — Import Runs as a Script, Not an Endpoint

**Decision:** Allegro import is `scripts/import_allegro.py`, not
`POST /integrations/allegro/import`.

**Rationale:** The orders endpoints carry no authentication. An
unauthenticated route that makes outbound calls to a third party is an
obvious thing to abuse, and rate limiting is not the right answer to it. This
becomes an endpoint once auth is wired into the orders API.

*Update 2026-09-17:* the orders API now requires a login, so the reason for
keeping this a script is gone; the endpoint itself is a separate change.

*Update 2026-09-17 (later the same day):* the endpoint now exists,
`POST /api/v1/integrations/allegro/import`, behind the same login as every
orders endpoint, plus two things a script never needed. A non-blocking
`threading.Lock` refuses a second import with `409` while one is running:
Allegro rotates the refresh token on every use, so two imports refreshing it
at once would race, and the one that loses is left with a token that is
already dead. And the endpoint is rate limited (6/minute/IP) because it makes
outbound calls to a third party on the caller's behalf — the same reasoning
that kept this out of the API in the first place, just answered with a limit
instead of no route at all now that a login gates who can call it. Both the
script and the endpoint build their `AllegroClient` through
`app/services/allegro_import.py`, so there is exactly one place that wires
the database-backed token store; a second copy would read the current token
but have nowhere shared to persist a rotation.

## 2026-09-16 — Order Total Read from `summary.totalToPay`

**Decision:** `total_amount` maps from Allegro's `summary.totalToPay.amount`.

**Rationale:** `lineItems[].price` is a unit price and excludes delivery, so
summing it understates the order and multiplying by quantity still misses
delivery and surcharges. `payment.paidAmount` is what has been paid so far,
which is zero on an unpaid order and fails the domain model's requirement
that a total be positive. Confirmed against Allegro's documentation rather
than inferred.

## 2026-09-16 — No Status Transition Rules Yet

**Decision:** Any order status may be set from any other. `PATCH
/orders/{id}/status` does not enforce a state machine.

**Rationale:** The valid transitions for this business have not been
established, and operators need to correct mistakes — including moving an
order back out of a terminal status. Guessing a state machine now would
block legitimate corrections and would have to be unpicked later. The place
to add one is `OrderService.update_order_status`, noted in the code.

## 2026-09-16 — Status History Records No Author

**Decision:** `order_status_history` stores the transition and its timestamp,
but not who made it.

**Rationale:** The orders endpoints carry no authentication, so there is no
user to attribute a change to. Adding a nullable column that nothing
populates would look like a working feature. The column belongs with the
auth dependency, in one change.

*Superseded 2026-09-17:* the orders API now requires a login and the history
records `changed_by_user_id`, added in the same change as the login check.

## 2026-09-16 — Shared `order_status` Enum Type

**Decision:** `orders.status`, `order_status_history.from_status` and
`to_status` all reference one `Enum` object, and the history migration
branches on dialect to reference the existing type rather than recreate it.

**Rationale:** On PostgreSQL an `Enum` is a real database type. Declaring it
per column makes Alembic emit `CREATE TYPE order_status` a second time, which
fails against a database where the orders table already created it. The
branch is unverified: only the SQLite path has been run.

## 2026-08-02 — Modular Monolith from the Start

**Decision:** We build a single application with clear modules, instead of microservices.

**Rationale:** The first version should be easy to run and develop by a small team. Module boundaries preserve the possibility of later component extraction.

## 2026-08-02 — PostgreSQL as Target Database

**Decision:** We design the data model for PostgreSQL.

**Rationale:** Suitable for relational order data, provides reliability, and leaves room for development.

## 2026-08-02 — Integrations as Adapters

**Decision:** Allegro and ERLI have separate modules, returning a common domain format.

**Rationale:** Limits the rest of the system's dependency on external API details.

## 2026-08-02 — No Docker in Sprint 1

**Decision:** We run the local environment natively.

**Rationale:** Reduces the entry barrier; containers will be added when they become genuinely needed.

## 2026-09-21 — Interface language: own small i18n, Polish default

**Decision:** UI text lives in typed dictionaries (`frontend/src/i18n/messages.ts`, English and Polish) behind a dependency-free store; the language is chosen per browser (localStorage) and defaults to Polish. Counted messages use `Intl.PluralRules` (Polish needs four forms). Tests start in English.

**Rationale:** Two languages and one team do not justify a library; the compiler and a parity test guarantee Polish covers every English key. Error messages that come from the backend are not translated (they stay English) — translating them needs error codes in the API, a separate change.

## 2026-09-21 — Scheduled imports: an opt-in loop in the backend, off by default

**Decision:** The backend can start an Allegro import itself every `ALLEGRO_IMPORT_INTERVAL_MINUTES` (an asyncio task in the FastAPI lifespan running the same `run_import` as the button, in a worker thread). It is 0 (off) unless set. How each import ended (time, counts, error) is stored on `integration_credentials` and shown on the orders page, which reloads its list when a newer import appears.

**Rationale:** A scheduler inside the process needs no extra service, and sharing `run_import` keeps one lock and one record for both triggers. It is off by default because the lock is per process while the database is shared by several machines, and Allegro rotates the refresh token on every use: two backends importing on their own would invalidate each other's token. Enabling it in the environment, not in the database, ties it to the one machine meant to run it.

**Consequences:** Imports happen only while that backend runs, so it must be hosted somewhere that stays up (`ROADMAP.md` item 3). There is no leader election; turning the setting on for two backends against one database is a misconfiguration. Not exercised against Allegro here: this machine has no connected account, so the scheduled path was checked up to "skips when not configured", and `run_import` itself by tests.

## 2026-09-21 — Hosting: containers on the NAS, images from GitHub, reached over Tailscale

**Decision:** The application runs as two containers (API, and nginx serving the interface and forwarding `/api`) in Container Station beside the PostgreSQL one. Images are built by GitHub Actions after Checks pass on `main` and published to `ghcr.io`; the NAS only pulls. The port is open on the home network and through Tailscale, not to the internet, and served over plain HTTP.

**Rationale:** The scheduled import needs a process that stays up, and the NAS already is one, next to the database. Building in CI means the NAS, with its modest processor, only pulls, and what it runs has passed the same tests as everything else. Tailscale already encrypts the way in from elsewhere, so a certificate and an internet-facing login page would add work and risk (the page fronts customers' names and addresses) without a need. This supersedes "No Docker in Sprint 1" for deployment; development stays native.

**Consequences:** The backend migrates the database on every start, so an image never runs ahead of its schema (and a bad migration blocks startup). Secrets live in the compose file inside Container Station on the NAS, not in Git. Images are built for both amd64 and arm64 because the NAS's processor was not checked. Not yet built or run: `DEPLOYMENT.md` is the first attempt's script.

## 2026-09-21 — Shipments are read per order, and their tracking refreshed on every import

**Decision:** Parcels (carrier, waybill) and the carrier's latest tracking status are stored in `order_shipments` and read only for orders Allegro reports as sent or delivered, one extra call each; tracking is asked in batches per carrier. Every import also re-reads the tracking of parcels of shipped orders that are not yet delivered. Both are best effort: a refusal or failure never fails the import, and parcels that could not be read are left as they were. The tracking status is shown, and never changes the order's own status.

**Rationale:** The checkout form has no tracking numbers, so there is no way to get them without a call per order; limiting it to orders that have left keeps the cost small. Refreshing tracking separately is needed because a carrier moving a parcel does not change the order, so the import that fetches only changed orders would leave the first status showing forever. The order's status stays the marketplace's fulfillment status alone, so two sources cannot disagree about it.

**Consequences:** More Allegro calls per import (one per newly sent order, plus batches of 20 waybills). The endpoints' scope is not documented and was not tried: if Allegro refuses, shipments simply stay empty and the log says so. Carriers Allegro cannot track never get a status. Tracking history exists for 60 days, so older parcels are not refreshed.

## 2026-09-21 — Fees: stored as the marketplace's own entries, tied to orders by its order id

**Decision:** The marketplace's billing entries are stored one row each in `billing_entries`, by the marketplace's id, never updated, and read by their own sync point with a one-day overlap. They are tied to an order by `(source, order_external_id)` with no foreign key, and served as a sub-resource, `GET /orders/{id}/billing`, with their sum. Reading them is best effort like shipments.

**Rationale:** Entries are a stream of events that exist independently of orders: one may arrive before its order, or name none, so a foreign key would reject or lose them, and storing them whole keeps them available for account-level questions (advertising, subscriptions) later. Skipping ids already stored makes overlapping reads free and the overlap protects against late postings. A sub-resource, like the history, keeps the order's own response and its list unchanged.

**Consequences:** One more read per import. The billing scope is not known to be granted, in which case the card stays empty and the log says why. What the history includes beyond fees is unverified, so the total is labelled net fees, and no margin is shown, since the cost of goods is not known to Anvero.

## 2026-09-24 — Build Anvero further, modelled on AlleIntegrator; what is in and out

**Decision:** Anvero keeps being built rather than replaced by AlleIntegrator or Ritevo, taking AlleIntegrator's screens as the model. The owner triaged its features against how the business works; the result, in order, is the feature plan at the end of `ROADMAP.md`: A) work queues, a "to make today" list, search, Erli import, safe mode, status and tracking written to Allegro, an application status page; B) labels through "Wysyłam z Allegro", buyer messages, invoices through an external program plus fees and margin, returns and claims, the owner's own courier contract; C) later conveniences; D) optional add-ons (offers, stock, suppliers, own KSeF issuer and more).

**Rationale:** The business sells on Allegro and Erli, 10–50 orders a day, with most goods made to order: so no stock keeping is needed, and a production list matters more than a warehouse. Invoicing is an external program's job (a KSeF issuer is large and carries legal risk), so Anvero only queues, triggers and uploads. Queues come before any write to Allegro because they touch only Anvero's data; safe mode comes before the first write so a mistake on the real account shows as "would send".

**Consequences:** Erli moves from "only if selling there" to stage A4. The dispatch deadline has to be imported for the "at risk" sort. The invoicing program is not chosen yet; comparing them is the first step of stage B3. Group D is kept as optional ideas, not rejected.

## 2026-09-24 — A "ready to ship" status, and work queues defined by the backend

**Decision:** Anvero's statuses become New → In progress (`CONFIRMED`, relabelled) → Ready to ship (`READY_FOR_SHIPMENT`, new) → Shipped → Delivered, plus Cancelled, one for one with Allegro's fulfillment statuses up to shipping. Four work queues are defined once, in the repository, and serve both the list filter (`GET /orders?queue=`) and the dashboard counts: to make (`NEW`/`CONFIRMED`, paid or paying later), unpaid (waiting and owing payment before shipping), to ship (`READY_FOR_SHIPMENT`, paid) and late (to make or to ship, past `dispatch_by`). A queue opens sorted by the closest dispatch deadline; the whole list stays newest first.

**Rationale:** The owner makes most goods to order, so "still to make" and "made, waiting for the courier" are different work, and one `CONFIRMED` could not tell them apart; Allegro already does, and writing statuses back (feature plan A6) needs the same distinction. The owner chose the new status over reading the difference out of the marketplace label (`API.md` says not to branch on it). Payment decides the queues because an unpaid order should not be made yet: cash on delivery and deferred payment never count as unpaid, and an order with no payment information at all (entered by hand) is not parked as unpaid where nobody would look.

**Consequences:** PostgreSQL's `order_status` type gained a value (downgrade rebuilds the type). Orders Allegro already called `READY_FOR_SHIPMENT` were moved to it by the migration where the operator's status still matched Allegro's, with no history entry. `dispatch_by` comes from Allegro's documented `delivery.time.dispatch.to`, not yet seen in a real payload; without it an order is simply never late and sorts last among the at-risk.

## 2026-09-24 — The "to make" list groups by the seller's code, computed on request

**Decision:** `GET /orders/production` builds the list from the to-make queue on every request, in Python, grouping order items by `sku`, else `offer_id`, else `name`. Nothing is stored and nothing is ticked off: an order leaves the list when its status moves to Ready to ship.

**Rationale:** The seller's code is the one identity shared by Allegro and Erli listings of one product, so both channels' orders land on one line; the listing and then the name keep items without a code from vanishing or merging with others. At 10–50 orders a day the queue is small enough that a query plus grouping in code is simpler than SQL aggregation, and works the same on SQLite and PostgreSQL. Using the status as the "done" marker avoids a second, parallel state to keep in step.

**Consequences:** Items without a SKU are only grouped per listing, so the same product in two listings shows twice until the listings carry a code. Partial progress (3 of 5 made) is not recorded anywhere.

## 2026-09-24 — The same buyer: the same email, or the same login on the same marketplace

**Decision:** An order's "other orders of this buyer" are those with the same `customer_email`, or the same `customer_login` on the same `source`. Search matches the buyer, items, city, pickup point and waybill through `EXISTS` subqueries.

**Rationale:** There is no customer table yet (`DATABASE.md`), and a marketplace may hand out a masked email that is not stable for one buyer, while its login is; a login is only unique within one marketplace, so it is compared per source. Matching the two channels' accounts of one person would need a customer record, which nothing needs yet. `EXISTS` keeps one row per order, so the count and the page agree however many items match.

**Consequences:** A buyer using different emails and different marketplaces appears as two buyers. Search runs several `ILIKE`s with a leading wildcard, which no index serves; fine at this size, worth revisiting at tens of thousands of orders.

## 2026-09-24 — Erli: the order search rather than the inbox, and a stand-in email

**Decision:** The Erli adapter reads orders with `POST /orders/_search`, sorted by update time and paged by Erli's cursor, through the same `OrderImportService` and sync point as Allegro. The sync point lives on an `ERLI` row of `integration_credentials` that stores only the API key's fingerprint. An order Erli returns before it has assigned the buyer's proxy email is imported with the stand-in `order-<id>@no-email-yet.erli.pl`. Amounts are read as grosze.

**Rationale:** Erli's inbox is an event stream that has to be acknowledged, a second mechanism beside the one Allegro already uses; the search by update time gives the same result with the existing service, and repeating a window is harmless. The email is required in Anvero, and skipping an order until it changes again could hide a paid order for days; a stand-in on a subdomain that receives no mail is visible and replaced by the next import that sees the real address. Keeping the key itself out of the database leaves `.env` the only place it is.

**Consequences:** Built from the documentation only and not yet run. If Erli does not touch `updated` when it fills in the email, the stand-in stays until the order next changes. Grosze is inferred (Erli's documentation says it only for campaign costs); the first real order must confirm the totals. No button or schedule yet: `scripts/import_erli.py` runs it.

## 2026-09-24 — Safe mode: one door for every marketplace write, closed by default

**Decision:** Every change Anvero makes on a marketplace goes through `MarketplaceWriter.write` (`app/services/marketplace_writes.py`), which reads the safe mode setting on each call. While it is on, the write is recorded in `marketplace_writes` as `DRY_RUN` and nothing is sent; with it off, the write is sent and recorded as `SENT` or `FAILED` with the marketplace's answer. Safe mode is on unless an operator switches it off in Settings, which asks for confirmation and records who did it. A banner on every page says when it is on.

**Rationale:** Writing to Allegro and Erli (feature plan A6 onwards) changes what real buyers see and are told. A switch that holds everything back lets the owner watch, in the log, exactly what Anvero would send before anything is, and stop it again at once. Putting it in one place, rather than a check in each feature, means a new kind of write cannot forget it. Stored in the database rather than `.env`, because it is the owner's decision made in the interface, and it applies to whichever backend makes the write.

**Consequences:** A fresh or migrated database starts in safe mode. Code that calls a marketplace client's write methods directly would bypass it; every write must go through the writer, which a reviewer should check. The log keeps every payload, which may include buyers' data once messages are sent.

## 2026-09-24 — Writing to Allegro: the last change made in Anvero wins

**Decision:** A status set by hand on an Allegro order is sent to Allegro as its fulfillment status, and a tracking number typed in is sent as a shipment, both through `MarketplaceWriter` (safe mode). The owner chose the rule for two changes at once: the last change made in Anvero wins. Anvero records when the operator set the status (`orders.status_set_at`), and an import does not move the status for a marketplace change whose `updatedAt` is older than that; a later marketplace change still wins. When a status is really sent, `marketplace_status` is set to it, so the next import does not read Anvero's own change as Allegro moving. `CANCELLED` is never sent. A failed send leaves the change in Anvero and is shown with Allegro's reason. A write waits for a running import (same lock), since both refresh the rotating token.

**Rationale:** Without the timestamp an import already in flight when the operator acts would overwrite the newer choice with an older snapshot; with it, only a genuinely newer marketplace change wins, which keeps the earlier rule "status follows the marketplace when it moves" for everything the operator has not just decided. Cancelling an Allegro order through the fulfillment status refunds no one, so it stays an action on Allegro. Keeping the local change on a failed send respects the operator's decision and makes the failure visible rather than silently reverting.

**Consequences:** Erli is not written to yet. Parcels typed in are flagged `added_in_anvero` and kept by imports that do not list them (for example while safe mode holds them back). Nothing has been sent to Allegro yet; the scope and the carrier ids are unverified (`INTEGRATIONS.md`, "Writing to Allegro").

## 2026-09-24 — The status page reads what Anvero holds; it never asks the marketplace

**Decision:** The application status page (`GET /status`, feature plan A7) judges each marketplace from what Anvero already stores: whether an account is connected, when Allegro issued the stored refresh token (new column `integration_credentials.token_issued_at`, plus Allegro's three months), how the last import ended, and this backend's in-memory schedule. There is no "test the connection now" call. Every import, the two scripts included, now notes its outcome through one helper (`app/services/import_outcome.py`), so the page sees imports by any route.

**Rationale:** The only live check of Allegro is refreshing the token, and Allegro rotates it on every refresh: a status page doing that would compete with imports for the lock and spend a rotation for every look. The last import already is a live check made minutes ago when the schedule runs, and its error says what went wrong. Before this, the scripts left no note, so an Erli import (script only) and a manual Allegro backfill were invisible.

**Consequences:** The verdict is only as fresh as the last import; with no schedule, "working" means "worked last time". The schedule shown is this process's: a backend that does not run the schedule reports it off even while another backend imports on the same database (its imports still show as the last import), and "configured but not running" is flagged when the interval is set here but the loop is not alive. Token expiry for rows that existed before the migration is estimated from the row's last change until the next rotation.

## 2026-09-24 — Labels: one standing label per order, the delivery method read live

**Decision:** A shipment bought through Wysyłam z Allegro is a write like any other: it goes through `MarketplaceWriter`, so safe mode records it as `DRY_RUN` and buys nothing. An order has at most one label that is being created or is created; another needs the first cancelled (or refused). The delivery method id is read from Allegro's order at the moment of buying, not imported. What was bought lives in its own table, `shipping_labels`, not in `order_shipments`; its waybill is added to the order as a tracking number, which also sends it to Allegro. The sender and the usual parcel are settings in `app_settings`, entered in the interface. Cash on delivery is refused for now.

**Rationale:** A label costs money and a second one for the same parcel is money lost, so the default is to refuse rather than to allow duplicates; an order needing two parcels is rare for this business and can wait for multi-parcel support. Reading the method live avoids a migration and a re-import of every order, and uses what Allegro will charge for now. `order_shipments` is rewritten by every import, which would lose the shipment-management ids needed to reprint or cancel. Cash on delivery needs the seller's bank account and an amount check that is not worth building before the plain case works.

**Consequences:** Buying needs Allegro reachable even in safe mode (the method is read first). If Allegro links the shipment to the order by itself, the tracking number Anvero adds may be refused as a duplicate: recorded as a failed write, harmless. Nothing has been bought for real; the Sandbox run is the next step (`INTEGRATIONS.md`).

## 2026-09-24 — Courier pickup: one carrier per pickup, slots from Allegro's proposals

**Decision:** A courier is ordered from the Labels page for chosen bought parcels: Anvero asks Allegro for pickup proposals for those parcels on the day they are ready, the operator picks one slot, and ordering it goes through `MarketplaceWriter` (safe mode). One pickup covers parcels of one carrier only; a parcel is in at most one pending or ordered pickup, and a refused pickup lets go of its parcels. Asking for proposals is treated as a read and does not go through safe mode. Cancelling a pickup is not built.

**Rationale:** A courier comes from one carrier, and grouping by carrier keeps the proposals simple to show while their real shape is unknown; the rule can relax once a real answer shows whether Allegro mixes carriers. Refusing a second pickup for the same parcel avoids ordering two couriers for one parcel. Proposals change nothing on Allegro, so holding them back in safe mode would only make the flow impossible to try.

**Consequences:** The operator orders one pickup per carrier. A pickup ordered by mistake has to be cancelled on Allegro for now. Everything is from the documentation and fakes until the Sandbox run (`INTEGRATIONS.md`).

## 2026-09-24 — No cash on delivery

**Decision:** The business does not ship cash on delivery, so Anvero will not build it for labels: an order whose payment is cash on delivery is refused a label, with a message to check it on Allegro, and no bank account or amount handling is added. This replaces "refused for now" in the labels decision above.

**Rationale:** The owner's answer on 2026-09-24. Building it would mean storing the seller's bank account and checking amounts for a case that should never occur.

**Consequences:** Stage B1 is complete in code. If such an order ever arrives (the offer's settings allowing it by mistake), the refusal is the signal to fix the offer on Allegro.

## 2026-09-24 — Buyer messages: a unified inbox over Allegro's Message Center, built without its OpenAPI spec

**Decision:** Started plan B2, one inbox across marketplaces (`message_threads`, `messages`). Allegro's threads are read into it (`POST /integrations/allegro/messages/sync`, its own button, sharing the import's lock and token), a thread can be put aside, and a reply goes out through `MarketplaceWriter` like a status or a tracking number. `developer.allegro.pl` was blocked by this session's network egress, unlike every other Allegro feature so far, which was built by reading its real documentation; this one is instead built from Allegro's Message Center announcement and search-indexed excerpts, flagged in `INTEGRATIONS.md`, "Buyer messages", down to which fields are confirmed by more than one source and which are guessed by analogy. A message's direction (buyer or seller) is decided by comparing its author's login to the connected seller's own, since no field of its own is confirmed to carry it. Erli is not read: its published API has no messaging endpoint that could be found.

**Rationale:** Building on an unread specification, rather than waiting for network access or refusing the feature, follows the same practice already used for shipments, tracking and billing entries here — real fields where more than one source agrees, the rest flagged and left for the first real response to confirm, tested against fakes shaped like the assumption. A thread compares its own `lastMessageDateTime` and read flag against what is stored to decide whether its messages need reading again, so a sync with nothing new costs one page of summaries; assumed, not confirmed, to sort newest activity first, which the early stop depends on. The reply going through `MarketplaceWriter` keeps the one rule already in place: nothing reaches a real buyer until safe mode is switched off, and the message is kept in Anvero (`created_in_anvero`) whatever becomes of sending it, so the operator's own record does not depend on it.

**Consequences:** Nothing has been sent to a real buyer yet - safe mode has been on throughout, as it was for the first status and tracking-number writes. The messaging scope's real name, the shape of one message, and whether threads truly sort newest-first are all unconfirmed until a real response or the published spec is read; the mapper and this file say so. Starting a new thread from Anvero, attachments, marking a thread read back to Allegro, and a schedule are left for later. Erli buyer messages stay outside Anvero until its API is checked again.

## 2026-09-24 — Erli's key is entered in Settings and kept in the database; Settings is grouped by purpose

**Decision:** The Erli API key is entered in Settings and stored in `app_settings` (key `erli_api_key`, plain text, no migration), taking precedence over `ERLI_API_KEY` in `backend/.env`, which remains as the fallback. It is saved only after Erli has accepted it (one order search with it), never sent back (only its last four characters are), and can be forgotten. A button imports Erli's orders through the same lock as Allegro's import. The Settings page is reorganised: a menu of sections beside cards laid out in a grid over the whole width, grouped as sales channels (Allegro, Erli), shipping (sender and default parcel) and general (safe mode, language).

**Rationale:** The database is shared between machines (`DEVELOPMENT.md`) and Erli's key does not rotate, so entering it once serves every machine, where `.env` would need it copied to each. It is stored as plain text for the same reason Allegro's client secret is (`INTEGRATIONS.md`): the database is as private as `.env`, and encrypting it would need a key that has to be kept somewhere just as private. Checking before saving turns a mistyped key into an error now instead of a failed import later. One lock for both marketplaces because the import button of either can be pressed while the other runs; the lock is cheap and the imports are short, so a second click waiting is not worth its own machinery.

**Consequences:** The key is readable by anyone with database access, as Allegro's secret is. Forgetting it does not stop the environment's key from applying. Erli still has no schedule and no live connection test beyond saving. Nothing about the adapter's correctness changed: it has still never seen a real response.

## 2026-09-24 — Message sync on its own schedule, sharing the import's lock

**Decision:** Reading Allegro's Message Center can run by itself every `ALLEGRO_MESSAGE_SYNC_INTERVAL_MINUTES` (default 0, off; an asyncio task in the FastAPI lifespan running the same `run_message_sync` as the button, in a worker thread). It is a schedule of its own, apart from the order import's, with its own interval and its own in-memory state, and takes the same lock. The generic loop moved out of the order import's scheduler into `run_schedule`, which both use. `GET /status` reports it as `allegro.message_schedule`, with the warning `message_schedule_stopped` when it is set but not running in this backend.

**Rationale:** Messages want a shorter interval than orders (a buyer waiting for a reply notices minutes, not a quarter of an hour), and they may not be wanted at all where orders are, so one shared interval would have forced both. The lock stays shared because both refresh the same rotating token, and the same rule follows: on for exactly one backend per database. A sync that finds nothing new costs one page of thread summaries, so a short interval is cheap on Allegro's side.

**Consequences:** A failed sync is logged and the next one tries again; its outcome is not stored, so Status shows only when the schedule last ran, not whether that run worked. Storing it (as order imports do on `integration_credentials`) is left until the messaging calls have been seen to work against the real API, which they have not been: a schedule on an unverified endpoint would fail quietly every interval. Nothing enables it by default, in the compose file included.

## 2026-09-24 — Returns and claims: a read-only queue with deadlines, actions left for later

**Decision:** Plan B4 starts as a queue that only reads. Customer returns, disputes and claims are read from Allegro into one table, `after_sales_cases`, each with an `action` (decide, reply, claim the commission back, or nothing) and a `due_at` worked out when it is stored. The Returns and claims page lists what waits, closest deadline first; the order shows an alert card; the dashboard shows a reminder. Nothing is changed on Allegro: accepting or rejecting a claim, rejecting a return, replying in a dispute and applying for the commission are not built. The returns' deadlines (14 days to decide, 45 to claim the commission) are counted from the day the return was declared, and a claim's comes from Allegro. A refunded return's commission stops being an action once its 45 days are over; a claim left undecided stays one, since Allegro accepts it when the time passes.

**Rationale:** The owner ordered B4 as a queue with deadlines and an alert on the order: what must not be missed comes before the means to act on it, and a missed claim deadline costs the claim (Allegro treats it as accepted) where a wrongly rejected one costs a dispute, so the first step is to see them all. Every action here has a legal or financial effect on a buyer; each should go through safe mode and be built one at a time, with the owner's answers on when to accept, so none was guessed. Allegro's API gives claims a deadline but returns none, so a return's is the early end of what the law allows: an alert that comes too soon is harmless, one that comes too late is not. `action` and `due_at` are stored, not derived on every read, because the queue sorts and filters by them; the rules are one function, so a wrong figure is one edit and the next sync corrects every row. The order is named by the marketplace's id and joined at read time, as messages do, since the case may be read before the order is imported.

**Consequences:** The 14 and 45 days, whether the 45 count from the declaration, and whether warehouse returns need the seller are unconfirmed until a real read. Whether the application carries `allegro:api:disputes` is unknown; without it disputes and claims fail with a clear error and returns still read (they need only the orders scope). There is no schedule: the queue is as fresh as the last press of the button, which is the price of not reading Allegro on an unverified endpoint every few minutes. The migration adds one table; run `alembic upgrade head` on each machine.

## 2026-09-24 — Design agreements: the order opens as a page, the list carries items, the menu carries counts

**Decision:** Agreed with the owner in the design document (Claude Docs, "Anvero — ustalenia designu", 24 September) and built the same day:

- **The order is a page of its own again**, reversing "Order detail: a slide-over, not a page" (2026-09-18). `/orders/:id` is a sibling of `/orders` in `App.tsx`, shown beside the menu on the whole right side; `OrdersPage` no longer renders an `<Outlet>` and `OrdersOutletContext` is gone. A link to an order carries, in router state (`OrderLinkState`), where "back" goes (`closeTo`: the list's URL, filters and page included) and the order of the orders on that page (`orderIds`). "Back" is a plain link to `closeTo` (or `/orders` when opened directly); next and previous arrows walk `orderIds`, replace the history entry so "back" stays one step, and stop at the ends of the page. The Dashboard, To make and Labels pages already passed `closeTo` and keep working. The Escape key and the body scroll lock of the drawer are gone.
- **`GET /orders` carries each order's items in short** (`name`, `sku`, `quantity`, `image_url`), loaded for the page in one `selectinload`, so the Items column of the list stops being a placeholder (up to three items with picture and quantity, then "N more"). Prices, ids and the other details stay out of the list (`docs/API.md`). `OrderListItem` extends `OrderRead` only for the list, so the buyer's other orders and every other use of `OrderRead` are unchanged.
- **The menu shows what waits**, beside the sections it leads to: orders to ship (red when any is past its dispatch deadline), the to-make queue, returns and claims waiting (red when any is past its deadline) and unread buyer threads. `useSidebarCounts` reads them from `GET /orders/stats`, `GET /after-sales/summary` and `GET /messages/threads?unread_only=true`, every minute and on each change of page; each fails on its own and a badge that cannot be filled in is left out. Unpaid orders are in the Orders badge's tooltip only.
- **The theme stays as it is**: light until the operator picks dark with the menu's button, remembered per browser, never following the system or the hour. `App.theme.test.tsx` pins it.
- **Authors** of marketplace writes are shown on the order (the API already carried them).

**Rationale:** An order is worked on (label, items, fees, messages, history), and a panel over the list is too narrow for that; a page gives the room and matches "one screen, one task". The list stays useful without the drawer because its filters live in the URL, so going back restores them; the price is that the list is fetched again on return, which is also why the "refetch behind the drawer" wiring could go. The list has to say what was bought for the operator to pack from it, and the alternative to one extra query per page would have been one per order. Counts in the menu answer "what must I do now" from any page, the design document's main rule for alerts.

**Consequences:** The list's scroll position is not restored on return (the page remounts); the arrows walk only the current page of the list, so the first and last orders of a page have one arrow off. The menu's message figure is the count of unread threads, not of threads waiting for an answer: how long before an unanswered message counts as waiting is still open in the design document. Every read of the counts adds three requests per minute and per page change. `OrdersPage.drawer.test.tsx` became `OrdersPage.test.tsx`. The buyer's other-orders card passes the same state on, so the arrows still work when the other order is on the same page and are hidden when it is not.

## 2026-09-24 — Interface languages: one registry, so a new language is a file and a line

**Decision:** Polish and English stay, as agreed, and adding a language no longer touches code. `frontend/src/i18n/languages.ts` is the one place that lists them: code, the language's own name, the locale for dates, numbers and plurals, and its dictionary. `Language`, `LANGUAGES`, the stored-choice check, the language pickers (login page, menu, Settings) and the tests all read it. To add one, copy `pl` in `messages.ts` into a file of its own, translate it, and add one line to `LANGUAGE_REGISTRY`. The menu's button steps to the next language (a toggle with two); Settings has the full list. The dictionary tests run for every registered language: every English key present, no orphans, the same `{placeholders}`, and, for counted messages, exactly the plural forms the locale has (`Intl.PluralRules(...).resolvedOptions().pluralCategories`), where they used to require Polish's four.

**Rationale:** The owner may sell Anvero on other markets (Czech, Hungarian, Romanian were named), so the third language should cost a translation, not a refactor. Taking the plural forms from the locale makes the parity test correct for languages the code has never seen. Missing keys still fall back to English at runtime, but the tests demand every key, so a half-finished language cannot be merged unnoticed.

**Consequences:** Backend error messages stay English (2026-09-21). Dates and numbers follow the locale automatically; the currency is whatever the order carries. A language with a right-to-left script would need layout work this does not include. Polish stays the default (`DEFAULT_LANGUAGE`); the browser's own language is not consulted. A third language has not been added yet, so the picker and the menu's stepping button are only tested with two.

## 2026-09-24 — A test label drawn by Anvero, and tracking numbers that link to the carrier

**Decision:** The Labels page has a "Test label" button that opens a sample A6 PDF made by Anvero itself (`GET /labels/test-pdf`, `services/sample_label.py`), and every tracking number in the interface links to the carrier's own tracking page when the carrier is known (`types/tracking.ts`, `components/TrackingLink.tsx`).

- The sample is written as a one-page PDF by hand, with the standard Helvetica fonts and no library, so nothing is added to `requirements.txt`. It has a frame and corner squares, a 100 mm ruler, lines one to four dots wide at 203 dpi, a solid black block and text from 6 to 12 pt, and prints the sender and default parcel saved in Settings without Polish letters (those fonts have none). It does not call Allegro, buy anything or depend on safe mode.
- A tracking link opens in a new tab with `noopener noreferrer`. Carriers recognised: InPost, DPD, DHL, Poczta Polska, UPS, GLS, FedEx; the id is read before the name; a carrier not in the list, Allegro's own included, keeps the number as text.

**Rationale:** A real label costs money and only comes from an Allegro account, so it cannot be the first thing tried on a printer; the sample answers the questions that come before any parcel (does the PDF open, is A6 printed at its true size, are margins kept, is fine print sharp) whenever they are asked, with safe mode on. Fine lines and a ruler were chosen because a thermal printer's usual faults are scaling by the print dialog and blurred narrow bars. Links save copying the number into the carrier's site, which is the most repeated small task of answering a buyer.

**Consequences:** The sample proves the PDF pipeline and the printer, not the purchase: buying a real label through Wysyłam z Allegro is still unverified (`PROJECT_STATUS.md`). It is not a barcode a scanner could read. The tracking addresses were not opened with a real number and a carrier can move its page; a wrong one shows as a dead link, never as a wrong parcel. No link is offered for Allegro's own carrier or one Anvero does not know, which shows as text.

## 2026-09-24 — Deleting an order is soft: the row is kept, hidden and restorable

**Decision:** An operator can delete an order from the list (a trash button on a row, and a button on the order's page, each asking first), but the row is not erased: `orders.deleted_at` and `deleted_by_user_id` are set (`DELETE /orders/{id}`, migration `b8e3d5a7c246`). A deleted order is in no list, count, queue or dashboard figure, is not brought back or changed by an import, cannot be given a status, tracking number or label, and is not polled for tracking. The list has a "Deleted" chip beside the work queues (`GET /orders?deleted=true`) where each row has a Restore button, and the order's own page still opens, saying when and by whom it was deleted and offering to restore it. An order with a label being bought or bought cannot be deleted (cancel the label first). No purge is offered.

**Rationale:** The two rules that decide it: an import matches on `(source, external_id)` and would create a really erased order again on its next run, and Anvero's number is "given once, never reused" (`DATABASE.md`), so an erased order would leave a hole the accountant may ask about. Hiding is also what the operator wants when they say delete (a test or sandbox order, a duplicate), and it is undoable, where an erasure of a real order, with its labels, fees and messages attached by marketplace id, is not. The label rule is because a bought label is money spent on a parcel: hiding the order would hide the parcel that is on its way. Who deleted it is kept like who changed a status.

**Consequences:** Orders that should be gone for good stay in the table; there is no screen to purge them, and doing it needs the database. A deleted order still has its labels' rows, its cases and its messages, which refer to it by id; the Labels page and the after-sales and inbox pages therefore may still name it. The menu's counts, the dashboard and the to-make list leave it out. After deleting from the order's page the page stays open (with the restore button) rather than going back to the list. The migration adds two nullable columns; run `alembic upgrade head` on each machine.

## 2026-09-24 — Buyer messages are decoded from HTML, and the inbox is searched by nick

**Decision:** Allegro's Message Center hands messages over as HTML text, so `zam&oacute;wienie` reached the inbox with its entity. `map_message` now decodes it once, drops invisible characters (`&zwnj;`, zero-width spaces) and turns no-break spaces into spaces (`app/core/text.py`), and data migration `c5f1a8d3e7b9` did the same to the messages and thread excerpts already stored. The inbox has a search box above its tabs: `GET /messages/threads?search=` keeps the threads whose buyer's login, order id, last message or any message contains the text, case-insensitively, across the tabs (a set-aside thread is found and marked), and the page waits 300 ms after the last key before asking. The endpoint's `limit` (default 200) is now a parameter, up to 1000.

**Rationale:** The first real sync brought 595 threads and 4137 messages, 1309 of them with entities, so Polish text looked broken in the list and the thread. Decoding at the mapper, where the text enters, keeps the database and the search clean; decoding only for display would have left `zamówienie` unfindable by searching for `zamówienie`. The list showed only the newest 200 of 595 threads, so a conversation of a few weeks ago could not be reached at all; searching on the server reaches every one, and the nick is what an operator knows about a buyer. A search ignores the tabs because "I do not remember if I put it aside" is the usual case for looking someone up.

**Consequences:** Decoding is done once, so a buyer's literal `&lt;` (sent as `&amp;lt;`) stays what was typed. The migration cannot be undone (decoding loses which characters were entities), and the stored text of a reply typed in Anvero, which was never HTML, is unchanged by it. Search is a substring match over messages, not a full-text index: fine for thousands of messages, worth revisiting at hundreds of thousands. Without a search the list still shows only the newest 200 threads. Threads are still not linked to their orders (`INTEGRATIONS.md`, "Buyer messages").

## 2026-09-24 — Open orders are read again every import; parcels are read from the start; the list scrolls sideways, grows a picture and pages properly

**Decision:** Agreed with the owner after a review of the order list, and built the same day:

- **An import reads every open order again**, beside the ones the window names: the orders in seller status `NEW`, `PROCESSING`, `READY_FOR_SHIPMENT`, `READY_FOR_PICKUP` and `SUSPENDED` (`fulfillment.status`, one request per value). They count as updated only when their status moved. A failure reading them is logged and the import goes on. The Allegro import also runs by itself, every 15 minutes, on this machine (`ALLEGRO_IMPORT_INTERVAL_MINUTES=15` in its own `.env`; exactly one backend per database may have it).
- **Parcels are read for every order that is neither new nor cancelled**, not only for orders already sent. A label bought in "Wysyłam z Allegro" gives the order a parcel while Allegro still calls it `PROCESSING`; on 2026-09-24 12 open orders had one that Anvero did not show.
- **The orders table scrolls sideways with a bar stuck to the bottom of the window** (`HorizontalScroll`): its own scrollbar is hidden and a second one as wide as the table follows it. `.app-content` no longer has `overflow-y: auto`, which made it the scroll container of everything sticky in it (`overflow-x: clip` and `min-width: 0` instead).
- **Item thumbnails in the orders list and the to-make list show a large picture (320 px) beside the pointer** (`ItemThumb`), drawn on the page so no table cuts it off.
- **Paging**: a choice of 20, 50, 100 or 200 orders a page, remembered in the browser (an address that names a size wins), a field to go straight to a page beside First, Previous, Next and Last (`Pagination`). Changing the size stays on the page holding the first order that was showing.

**Rationale:** The status and parcels an operator sees have to be what Allegro shows, or the list is not the thing to work from. Allegro does not reliably count a parcel being created as a change of the order, so an incremental import alone could leave an order as it was first read for as long as nothing else touched it; re-reading what is still open is bounded (the open orders are tens, not thousands) and needs no event journal. A sticky bar was preferred to a scrollable frame because the page keeps scrolling as one, with the bar always in reach.

**Consequences:** Every import now makes about five list requests plus one shipments request per open order, and the pictures of their items again (a second call per offer). The order's Anvero status still follows Allegro's own: an order whose parcel exists but that Allegro has not marked sent stays "in progress" (`PROCESSING`), which is what Allegro says; whether Anvero should show "ready to ship" from `lineItemsSent = ALL` is left to the owner. A parcel bought through Allegro has carrier `ALLEGRO`, so its waybill is not a link to a carrier's page. The tests of the status page no longer depend on the machine's own schedule settings.

## 2026-09-25 — Quick button for orders in progress, the buyer's login in the list, and a narrower to-make list

**Decision:** Asked for by the owner after using the list on real orders:

- **A quick button "In progress"** (Anvero status `CONFIRMED`, with its count from `GET /orders/stats`) sits right after "All", ahead of the work queues. Each quick button (All, In progress, a queue, Deleted) shows one thing and clears the others, including a status set in the filter panel; the panel follows a status chosen with the button, so a later search does not put the old one back.
- **The order cell of the list shows Anvero's number, then the buyer's login, then the name**, and no longer the marketplace's own order id (which is the tooltip of the number and stays on the order's page). With no login the name shows alone, and the email only when there is neither.
- **The to-make page has the same quick buttons** (All, New, In progress: the statuses the queue holds) **and a search for some orders**: `GET /orders/production` takes `status` and `search`, where several orders can be named with commas (`AN-000041, AN-000043`, a login, a name, a product's code). What is shown lives in the address, so an order opened from the list closes back to it as it was narrowed.

**Rationale:** "In progress" is the status asked for most on Allegro, and reaching it through the filter panel took three actions. The login is what an operator knows a buyer by, and a marketplace's order id is what they look at least. The to-make list is made from the paid orders that wait, so being able to cut it to the orders being packed now (or to one status) turns it from the whole workshop's list into today's batch. Reusing the order list's own search keeps one meaning of "find this order" across the application.

**Consequences:** "In progress" covers Allegro's `PROCESSING` and `SUSPENDED`, which Anvero does not tell apart. A search on the to-make page finds orders by any of the list search's fields, so a product's name brings in the whole order that has it, including its other items. The status buttons of the to-make page carry no counts. Nothing about the order list's paging, sorting or the deleted view changed.

## 2026-09-25 — Parcels of Allegro's own delivery are followed on Allegro's tracking pages

**Decision:** A tracking number whose carrier is `ALLEGRO` is a link to Allegro's public tracking page (`allegro.pl/allegrodelivery/sledzenie-paczki` for an `AD...` number, One's `allegro.pl/kampania/one/kurier/sledzenie-paczki` for the others), given the number as `numer`. The rule comes first in `types/tracking.ts`, and applies to numbers that start with a letter: a name such as "Allegro Kurier DPD (AD)" holds the word DPD, and a purely numeric number is a real carrier's (InPost through Allegro).

**Rationale:** After the tracking links (2026-09-24) only InPost's worked: the other 15 of the owner's 45 parcels are Allegro's own services, whose numbers are Allegro's and unknown to DPD or ORLEN Paczka, which say those parcels are followed in Allegro only. Allegro's tracking pages are the one place they can be looked up without an account.

**Consequences:** Whether Allegro's pages read the number from the address is not confirmed (allegro.pl answers no automated request, so it could not be tried, and only one search result named the parameter, for One's page); if they do not, the link still lands on the page that asks for the number. Anvero's own status for these parcels comes from Allegro's tracking API and is unaffected.

## 2026-09-25 — Settings and Integrations across the page, with the channels in their own colours

**Decided (owner, 2026-09-25, from mockups: Integrations A, Settings S1; channel colours kept):** the two pages
were the only ones set in a centred column, apart from the rest of the application, and were plain white. Now:

- **Across the whole width, left-aligned, like every other page.** The 960/1100px centred column is gone.
- **Integrations:** a blue strip for the update interval (one line: "… every [15] min", Save at the right); then a
  tile for each integration with a bar across its top in the channel's colour, a lettered mark, a pill for how it
  stands (Connected green, None grey, Finish setup amber; the sender's is "Set" once it is) and two lines: how it
  stands, and when it last imported or what it is for. The chosen tile has a border in its colour, and opens its
  settings in a card below whose band is tinted the same.
- **The channel colours** are tokens, `--channel-allegro|erli|inpost` (with `-bg` and `-fg` for a band, and
  values for dark mode) and the tone classes `tone-allegro|erli|inpost|sender` (`theme.css`); Allegro orange,
  Erli blue, InPost yellow, the sender in the accent colour. The order list's A and E marks use the same tokens.
  These colours are the brands' own, taken from memory, not checked against their guidelines.
- **Settings:** the two cards side by side (one column when narrow): appearance and language (blue band) and the
  safe mode (green band while it is on, amber when it is off, its state in a pill in the band).

Not done: the safe mode is still switched with its button and confirmation, not a slide switch as in the mockup.

## 2026-09-25 — The to-make list by day, with products ticked off

**Decided (owner, 2026-09-25, from mockups A and B combined, ticks in the database, per product):** the
"Do wykonania" page was one long table with the same deadline (with seconds) in every row and no way to
say what had been made. Now:

- **Groups by the day of the deadline**, in local time: past due (red), today (amber), tomorrow, each later day
  by its weekday and date, and no deadline last. A line goes by the earliest deadline among its orders, as it
  already did, so a product needed on two days is under the earlier. A late line says when it was due.
  Each group's band says how much of it is made (`1/4 made · 10/29 pcs`) and turns green when all is.
- **Ticking a product off** (the whole row is clickable, or its box): `PUT /orders/production/checks`, kept in
  the new table `production_checks` by the product's key, so it shows on every computer and to everyone; the
  tick shows at once and is undone with a message if it could not be saved. Figures for products and pieces
  made, of all there are, and a bar, sit above; "Hide made" (kept in the browser) shortens the list.
- **A tick is for a quantity.** A product counts as made while the list asks for no more than the quantity it
  was ticked for, so an order that arrives later and raises the number brings it back. Ticked in a narrowed
  view (a status, a search) it is ticked for that view's quantity only. Ticks older than 90 days are deleted
  whenever another is made. The tick is per product, not per order: taking a finished piece to the most
  urgent order is still the operator's call.
- **On paper** the page prints as it is, the boxes empty or ticked, to tick with a pen; the filters and the
  bar do not print. The deadline column is gone (the group says it); the layout folds to small grids under
  768px.

Not done: the list does not refresh by itself, so a tick made on another computer shows after a reload or a
change of filter; no history of who made what (`checked_by_user_id` is kept, and not shown).

## 2026-09-25 — One import button, an automatic update every 15 minutes for every channel, and a compact order list

**Decided (owner, 2026-09-25):** the owner found that automatic updates did not run, that the import button
covered only Allegro, and that the order list was too spread out to see many orders at once. They chose
variant A of three mockups for the list and "one button for all" for the import. Now:

- **Why nothing updated by itself:** the schedule was off unless `ALLEGRO_IMPORT_INTERVAL_MINUTES` was set in
  a machine's own `.env`, on the one backend meant to have it (the NAS, not deployed yet); this machine's had
  none. Erli had no schedule at all. This supersedes "off by default, on for exactly one backend" above.
- **One interval for every channel, 15 minutes by default,** kept in `app_settings`
  (`import_interval_minutes`), set in Integrations ("Automatyczna aktualizacja", `GET/PUT
  /integrations/schedule`; 0 is off, otherwise 5 to 1440, since Allegro limits how often it may be asked). It
  drives the Allegro orders import, the new Erli orders import and the Allegro message reading, in one loop
  (`services/schedule.py`) that reads the interval every half minute, so a change needs no restart and a
  shorter interval applies at once. The two per-channel environment intervals became one default,
  `ALLEGRO_IMPORT_INTERVAL_MINUTES` (15); `ALLEGRO_MESSAGE_SYNC_INTERVAL_MINUTES` is gone (ignored if still in a
  `.env`).
- **Backends take turns instead of "exactly one".** With the schedule on by default, a laptop and the NAS
  would both import and Allegro's rotating token would be raced for. A lease, one `app_settings` row
  (`scheduler_lease`) renewed every half minute and taken with a conditional write, lets one backend run the
  jobs; the others wait (`standby` on the status page, not a problem) and one takes over after two minutes of
  silence, or at once when the holder stops cleanly. `SCHEDULER_ENABLED=false` keeps a process out of it (the
  test suite uses it). A backend that was off, and finds the last import (by anyone) older than the interval,
  catches up a minute after it starts; otherwise its first run is one interval after the last import.
- **One import button** on the order list imports from every connected channel, one after the other (the
  backend runs one import at a time), says what each brought, and goes on to Erli if Allegro fails; under it,
  each channel's last import and "automatically every N min". The list reloads when an import of either
  channel finishes by itself.
- **The order list is compact** (mockup A): a row is two lines, about 53px instead of about 135px. Columns:
  order (marks, number, country; its date under it), buyer (the name, the nick under it, and the source as one
  coloured letter, A for Allegro and E for Erli), items (the first, with a thumbnail, and "+N more" with all in
  the tooltip), amount (with the payment method under it), status (with the icons and time in status under it),
  shipping (with the dispatch deadline under it) and the delete button. The payment and date columns are gone.

**Not done / limits:** the Erli import has still never run against a real Erli. The first run of the schedule
on this machine is unseen until fifteen minutes have passed (it was verified on a scratch database that the loop
starts, holds the lease and reports its next run). Reading messages on a schedule is now on by default too; it
only reads. An interval saved in Integrations lives in the shared database and so applies to every machine.

## 2026-09-25 — Inbox by day with waiting times, Status as a summary, tiles and a timeline

**Decided (owner, 2026-09-25, from mockups W2 for the Inbox and S1+S3 for Status):** the Inbox was a plain
list with a big empty pane and the Status page a wall of rows with no answer to "is anything wrong?". Now:

- **Inbox:** the tabs carry how many each holds (the other tab's count is one extra request, and the page
  carries on without it if that fails); conversations are grouped Today / Yesterday / Older by calendar day; an
  **unread** conversation shows how long it has waited (amber under a day, red after); one with an order has a
  blue chip; the open conversation is a card beside the list (the list narrows to two lines a row) whose head
  has the buyer, the wait, a link to the order (`/orders?search=<the marketplace's number>`), Put aside and close.
- **Status:** one bar (the worst state of the marketplaces that are set up; ones that are off are ignored) listing
  what needs attention with a link to Integrations; a tile each for Allegro, Erli and Anvero with the rest under
  "Details"; a timeline of the last imports, the last reading of messages and the last five changes sent or
  held back (`GET /marketplace-writes?limit=5`, and the page goes on without it if that fails).

**Limits, deliberately:** the waiting time is shown only for unread conversations, because the list does not say
who wrote last and `read` is mirrored from the marketplace (opening a thread in Anvero does not change it). The
timeline is a recent picture, not a history: only each source's last import is stored. The backend is unchanged.

## 2026-09-25 — Settings on rows, Integrations as tiles

**Decided (owner, 2026-09-25, from three mockups each):** the two pages had a menu of sections beside
their cards that repeated what the page already showed, a subtitle stranded at the right edge, and cards of
very unequal height (two tiny ones beside a tall one; Allegro's long form beside a cut-off Erli card). Now:

- **Settings (mockup A):** one centred column, no menu. A card "Appearance and language" with each setting
  on a row (what it is and what it does on the left, its control on the right), and the safe mode card,
  its heading carrying whether it is on and its log folded away with the number of entries.
- **Integrations (mockup C):** a tile for each integration (Allegro, Erli, InPost, Sender and parcel), each
  with a dot and a line of how it stands ("Connected as swift_hands · Production", "API key set (…lyLu)",
  "Not connected"), so all four are seen at once; the chosen tile opens its settings in a panel below.
  The choice is kept in the address (`/integrations?integration=erli`), so it can be linked to and survives a
  reload. The tiles are read from each integration's own endpoint and fail on their own; a settings card that
  saves something tells the page (`onChanged`), which reads the tiles again. Only the chosen card is mounted,
  so unsaved typing in another is lost when switching.
- `SettingsLayout` and its menu are gone. The page header keeps its subtitle under its title.

Not done: the InPost status is not in `GET /status`, so the tiles ask its endpoint directly; a tile does not
show the last import.

## 2026-09-25 — One look for the whole application: the order page's style, everywhere

**Decided (owner, 2026-09-25):** the colour and the type chosen for the order page (grey canvas, white
rounded cards with tinted title bands, 14px text in a dark ink, small labels in bold capitals) are the
style of the **whole** application, and every page is brought to it. The owner also pointed out that the
dropdown looked unlike the buttons and tables: every page had styled its own buttons, fields and
dropdowns, so no two matched. Now:

- **The values are shared.** Colours, radii and the 14px base are tokens in `index.css`
  (`--color-canvas`, `--tone-*`, radius 8px / card 10px), each with its dark value set once; the
  card, its band, the tones, page titles, tables in a card and the pill tabs are in the new `theme.css`,
  loaded after every page's stylesheet. `docs/STYLE_GUIDE.md` says all of it, and is what a new page follows.
- **Controls are defined once**, with `:where()` so a page can still differ on purpose: an outlined
  button (the filled accent one is `type="submit"`), one field, and one dropdown with its own arrow (the
  browser's is switched off, which is why a page's `select` rule must not write `background:`). The
  per-page rules that restyled inputs, selects and their focus were deleted (about a dozen stylesheets).
- **Every page is on the canvas:** the page header is the same on every page (title on the canvas, 1.5rem
  bold); the Dashboard's figures, charts and recent orders, the Status page, the filters panel, the
  settings and integration cards, the label pick-up panel, the inbox and every table are cards; their bands
  are toned (blue: the thing itself, teal: shipping and integrations, green, amber or red for how a part of
  the application is doing).
- **Tabs are one style:** pills with the chosen one filled, replacing three different tab looks.
- **A card's title row** may be a `card-head` when it holds a button.

**Not done:** the menu's own look (it keeps its light grey and its width), the login page's card is only
moved onto the canvas, and no page was reworked in structure. This supersedes "the order page only" in
the colour and type notes below.

## 2026-09-25 — The order's page is laid out like BaseLinker's: what matters first, the rest folded

**Decided (owner, 2026-09-25, after a mockup):** the order page was one long column of
cards of equal weight, led by a list of eleven fields (a UUID and three technical dates
among them). It is now:

- **A header card:** star and flag, the order number, the buyer, the channel, the country,
  when it was placed, one button for the **usual next step** (New, In progress, Ready to
  ship, Shipped, Delivered: "Mark as ..."), the rare actions (delete, restore) under a
  "..." menu, and a row of steps showing where the order stands. Any other status,
  cancelled included, is still set from the Status field of the "Order" card. The button
  takes one step at a time (the first of the two versions in the mockup); the steps are
  not clickable.
- **A bar of what needs attention**, only when there is something: a dispatch deadline
  (late, or under a day away), an unpaid order, the buyer's message and the seller's note
  (each opens in the same small window as in the list, from the order already loaded), the
  internal note (a link to the foot of the page). An ordinary order has no bar.
- **Two columns:** items, the delivery and invoice addresses (each with a copy button), and
  shipping on the left; payment (a green mark once paid), the order's facts and the buyer
  on the right. Below 1000 px one column.
- **One shipping card** instead of three: the parcels sent, and one way of making another
  at a time in tabs, shown only where they can apply (a label bought through Allegro for an
  Allegro order, InPost for a locker order, a tracking number typed in always); with only one
  way there are no tabs. The existing cards are embedded, not copied (`CardShell`).
- **Folded sections**, all closed at first, with a count or a figure beside each name:
  status history, marketplace fees, the buyer's other orders, what was sent to the
  marketplace, technical data (the identifiers and the technical dates).
- **An internal note**, a new field written in Anvero only (`internal_note`,
  `PATCH /orders/{id}/note`), at the foot of the page for now: the owner will decide later
  whether it stays there or moves up.

**Colour (owner chose variant C of four mockups, 2026-09-25):** the page sits on a grey
canvas (`--color-canvas`) under white, rounded cards, and every card's title is a band tinted
for what the card is: blue for the order itself (items, facts, buyer), teal for sending it
(shipping, delivery, invoice), green or red for the money (paid or not; plain when unknown or
paid later), amber for the notes and for a return waiting on the seller. The steps run green
for done, solid teal for now, grey for what is left; the payment amount and the order total are
headlines. Only the order page: the list and the other pages stay as they were until the owner
has judged this one. No shadows: the cards are told apart by the canvas and their bands.

**Type (owner, 2026-09-25: "more distinct, maybe a little smaller"):** the order page is 14px
(the rest of the application stays at 16px) and sets `--color-text`, `--color-muted` and their
kin darker inside `.order-page` only, so nothing else moves. Small labels are capitals, bold,
letter-spaced; values are semibold; the page's title is 1.5rem bold. Controls inherit the
page's font instead of the browser's smaller default. All of it is in the last block of
`OrderPage.css`, so it can be tuned in one place.

**Not done:** the buyer's message thread on the order (Allegro's public thread schema does
not name the order, `INTEGRATIONS.md`), clickable steps, an "actions" menu with more in it.

## 2026-09-25 — Integrations are a page of their own; the theme and the language are chosen in Settings only

**Decided (owner, 2026-09-25):** the bottom of the menu carried a theme button and a
language button that were hardly ever used and crowded a folded menu; both now live only in
Settings, and everything about Allegro, Erli, InPost and the shipping details for labels
moves from Settings to a new **Integrations** page (`/integrations`). Settings keeps the
safe mode, the appearance and the language: the safe mode guards writes to every
marketplace, so it belongs to the application, not to one integration. Both pages are one
component, `SettingsLayout` (the menu of sections and the cards), given different groups (since replaced, see "Settings on rows, Integrations as tiles").
The message keys keep their `settings.group...` names, and the cards their `settings-...`
ids, so nothing that linked to them broke. The sender and default parcel count as an
integration: they are only used for labels bought through Wysyłam z Allegro.

## 2026-09-25 — Ideas from BaseLinker: ticking orders, marks, a menu that shows statuses, a menu that folds properly

**Decided (owner, 2026-09-25):** after comparing the order list with BaseLinker's,
take these into Anvero, as one change:

- **The folded menu makes room.** The page's left margin was fixed at the open
  menu's width, so folding the menu left an empty strip. The menu's state now lives
  in the layout (`useSidebarOpen`, kept in `localStorage` as `sidebar.open`) and the
  page's margin follows it; the two widths are the CSS variables
  `--sidebar-width-open` and `--sidebar-width-closed`, in one place instead of two
  files "kept in sync". Below 768 px the menu is a 70 px strip that unfolds *over*
  the page (it used to become the full width, folded or not) and folds again when a
  link is followed; unfolded beside the page on a wide window, folded on a narrow
  one until the operator chooses.
- **The picture on hover in an order's details is the list's.** It was scaled in
  place by CSS and cut off by the table's scroll box; it now uses `ItemThumb`, which
  draws it on the page.
- **Ticking orders and acting on them together** (`BulkActionsBar`): set one status
  on all, star, flag or take a mark off. A status change is one request per order,
  one after another, through the existing `PATCH /orders/{id}/status`, so each still
  goes through safe mode and the marketplace write; no bulk endpoint. A failure of
  one is reported, and the rest go on. Labels are not in the bar: the Labels page
  already prints many at once.
- **Marks:** `starred` and `flagged` on the order (two plain booleans), set with
  `PATCH /orders/{id}/marks`, filterable from two quick buttons. Star and flag are
  independent so that "important" and "come back to this" do not fight over one mark.
- **The list says more at a glance:** the delivery country (as its code: Windows
  draws flag emoji as bare letters), how long the order has been in its status
  (`status_changed_at`, new column, shown as "3 days ago" with the date on hover),
  and small icons for paid / not paid, a parcel sent, an invoice wanted, a buyer's
  message and a seller's note. "Paid" follows the same rule as the "unpaid" queue.
- **The message and note icons open their text** in a small window over the list. The
  list carries only whether there is a message or a note (up to 4000 characters each,
  for every order of a page), so the text is fetched from `GET /orders/{id}` when the
  icon is pressed and nothing about the API changes. A fetch closed before it answers
  does not open the window again.
- **The menu shows statuses and channels** under Orders, on an orders page only,
  with how many each holds and a link to the list narrowed to it. Not BaseLinker's
  custom statuses in groups: Anvero's six statuses are fixed, and the work queues
  already are the quick buttons.

**Not done, on purpose:** custom statuses and groups, saved filter sets, a global
search box in the header, adding an order by hand. Shift-click range ticking.

## 2026-09-25 — InPost parcels are made through ShipX by Anvero itself

**Decision:** Anvero makes InPost parcel locker shipments and prints their labels through InPost's ShipX API (`services/inpost_shipments.py`, `integrations/inpost/client.py`), in bulk from the Labels page and one by one on the order. Token, organization and environment are entered in Settings and kept in `app_settings`, environment `sandbox` by default. Creating goes through `MarketplaceWriter` (safe mode), an order has at most one shipment that is not cancelled, and a number InPost returns is added to the order like any tracking number, which pushes it to Allegro.

**Rationale:** The owner makes InPost labels for Allegro orders in the Manager Paczek and prints them there. ShipX cannot list or print shipments made in the Manager Paczek, so printing them from Anvero is not possible; making them in Anvero is, and replaces the trip to the Manager Paczek. Making a parcel costs money and sends a real one, so it is held to the same safe mode as every other write, and the sandbox is the default until the owner has seen it work.

**Consequences:** Parcels the Manager Paczek made stay outside Anvero's InPost list (their numbers still import from Allegro). An order that already has a tracking number is refused a new parcel, to avoid two parcels for one order. Locker deliveries only; courier shipments, insurance and cash on delivery are not built. The connection has not run against InPost: the batch labels request, the shipment status words and whether `sending_method` is needed are unconfirmed until a sandbox token is tried.


## 2026-09-26 — Erli's pictures are read from its product, like Allegro's from its offer

**Decision:** `ErliClient.fetch_product_image(external_id)` calls `GET /products/{externalId}` and returns the first of the product's `images` (`[{"url": ...}]`); `ErliAdapter` sets `OrderItemCreate.image_url` from it, one call per distinct product in a page. `externalId` is what the order's item already carries as `offer_id`. It never raises: a picture that cannot be read leaves the item without one, as with Allegro (`fetch_offer_image`).

**Rationale:** Erli's order items carry no picture, so Erli orders showed a blank where Allegro's showed a thumbnail. The product endpoint is in Erli's published description and, tried against the real service on 2026-09-26, answered 200 with `https://i.erli.pl/...webp` addresses.

**Consequences:** Orders imported before this have no picture until they are read again: a plain import reads only what changed, so a backfill (`python scripts/import_erli.py --days N`) fills them. The import makes one more request per distinct product.


## 2026-09-26 — An import also asks for the orders Anvero holds as open, by id

**Decision:** After the window and the list of open orders, `OrderImportService` asks the adapter (`fetch_orders_by_id`, Allegro's `GET /order/checkout-forms/{id}`) for every order whose last marketplace status is still open (`NEW`, `CONFIRMED`, `READY_FOR_SHIPMENT`; `OrderRepository.open_external_ids`), not deleted in Anvero, and not read already in this run. They count as updated only when their status moved, like the open orders. A refusal or failure is logged and the import goes on; a single order that cannot be read is skipped.

**Rationale:** On 2026-09-26 nine orders sat as "ready to ship" in Anvero that Allegro had already marked `SENT`, some for two days. Once an order is `SENT` the per-status lists of open orders (`OPEN_FULFILLMENT_STATUSES`) no longer name it, and Allegro does not count a change of the handling status as a change of the order, so the window missed it as well: the two mechanisms of 2026-09-24 covered orders that stay open, not the moment they stop being. Confirmed against the real API before the change (`READY_FOR_PROCESSING` / `SENT` for all nine), and after it one import moved all nine.

**Consequences:** One more request per open order every import (about 25 today), plus their shipments. An order the operator set by hand still stands until the marketplace moves again. Erli has no such call yet: its search is by update time, and none of its orders has been seen stuck.


## 2026-09-26 — A sent order becomes delivered when its carrier says every parcel arrived

**Decision:** At the end of a sync, `OrderImportService._settle_delivered` moves every order still `SHIPPED` (not deleted, of the importing marketplace) to `DELIVERED` when it has at least one parcel and every parcel's `tracking_status` is `DELIVERED` (`OrderRepository.shipped_orders_delivered`). The move is recorded in the status history with no author and is **not** written back to the marketplace. A parcel that is `RETURNED`, still on its way, or unknown keeps the order `SHIPPED`; so does an order with no parcel.

**Rationale:** The Anvero status follows the marketplace's (`The Anvero Status Follows Allegro`), but Allegro's seller status never says "delivered": it stays `SENT` (`PICKED_UP` is only for collection in person). The delivery was known to Anvero all along, in the parcels' tracking, and nothing used it: on 2026-09-26 40 of 43 "shipped" orders had every parcel delivered, so the "Shipped" list mixed what was on its way with what had long arrived. Erli already reports its own delivered status, so nothing changes there.

**Consequences:** The marketplace's own status is kept beside (`marketplace_status` stays `SENT`), so the next import sees no move and does not undo it. Writing `DELIVERED` back would send Allegro `PICKED_UP`, which is wrong for a courier delivery, hence no write. An order set to `SHIPPED` by hand is settled too once its parcels are delivered. One import moved the 40.


## 2026-09-26 — Pictures Anvero already holds are not fetched again

**Decision:** The adapters take an optional lookup of the pictures stored per offer (`known_images`, answered by `OrderRepository.images_by_offer(source, offer_ids)` and wired in `build_allegro_import_service` and `build_erli_import_service`). `attach_item_images` (`integrations/mapping.py`, one function for both adapters) asks it once for a page's offers, reuses what it has and fetches only the offers with none, once each. The newest stored picture of an offer wins.

**Rationale:** An import reads every open order again, and each read asked Allegro for the offer's picture again: 106 of an import's 133 requests on 2026-09-26, all to `GET /sale/product-offers/{offerId}`, a resource with a limit of its own (3500 a minute; 9000 overall per Client ID). Nowhere near the limit, but it was most of the traffic and most of the time an import took, for pictures that hardly ever change. The same import made 27 requests afterwards, none for pictures.

**Consequences:** A picture is fetched once per offer and then kept: if the seller changes an offer's photo, orders imported before keep the old one and new orders of that offer get it only if no stored order of it has one (an item with no picture is not held, so it is asked for again). An offer whose picture could not be read is retried on the next import.


## 2026-09-26 — The dashboard is where a session starts; the app status is a tab of Settings

**Decision:** After logging in, and at `/`, the application opens the Dashboard (the old welcome page, `Home.tsx`, is gone). The Dashboard is rebuilt around the day's work, as chosen by the owner from three mockups ("A: today" with the deadline list of "C"): four large tiles linking to the list narrowed to each: the orders in progress (status `CONFIRMED`, which the owner preferred to the "to make" queue, since it counts unpaid ones too) and the to-ship, unpaid and late queues (the late one red when it holds anything); the orders waiting to be made or sent with the nearest dispatch deadline, with the item's picture; the recent orders as a small table; and in a column beside them one "Needs attention" card (an order cancelled on the marketplace, returns and claims, unread messages, a problem in the app status), the week's figures and each channel's share. The header carries the import button with the per-channel import chips (the same `ImportBar` as the order list) and a chip saying how the app stands. The Status page leaves the menu and becomes the "App status" tab of Settings (`/settings?tab=status`; `/status` redirects there). While the status has something needing attention, the menu shows a dot beside Settings.

**Rationale:** The owner wants to see "what and how" at once after logging in, and does not look at the status every day. The old dashboard led with two rows of identical tiles, the second of all-time totals, and gave each warning its own banner. Moving the status out of the menu must not hide a broken import, hence the dot in the menu and the chip on the dashboard.

**Consequences:** No API change: the deadline list merges `GET /orders?queue=to_make` and `?queue=to_ship`, both sorted `at_risk`, and keeps the five with the nearest `dispatch_by`; the status comes from `GET /status` (`useAppHealth`, read every minute and on each page change, like the menu's counts). The breakdown by status and the all-time order count are no longer on the dashboard (the list's shortcuts under Orders have the counts by status). The hints under the queue tiles are fixed sentences; figures such as "5 due today" would need new counters in `/orders/stats`.


## 2026-09-27 — The to-make list prints on A4

**Decision:** The To make page's print styles name their page (`@page production`, `size: A4 portrait`, 12 mm margins) and put `.production-page` on it when printing.

**Rationale:** Printed with no page size, the browser used the default printer's paper, which on the owner's machine is the label printer's, so the list came out on a label. A named page keeps the size to this page: labels are PDFs opened in a tab of their own and keep theirs.

**Consequences:** The paper size cannot be changed in the print dialog for this page; a browser without named pages (Chrome before 85) falls back to the printer's default.


## 2026-09-27 — The status history ends with the status the order came in with

**Decision:** `GET /orders/{id}/history` appends one entry after the transitions: the status the order came into Anvero with (`from_status: null`, dated `created_at`, no author, the order's own id), shown as "Imported from Allegro as In progress". It is worked out when asked, not stored: every transition records the status it left, so the first status is the oldest row's `from_status`, or the current status when there is none. The buyer's other orders on an order's page get column headings, the status one named "Its status".

**Rationale:** An order imported straight into "In progress" had an empty history ("0"), and right under it the buyer's other orders showed a "Delivered" badge with nothing saying whose it was; the owner read it as this order's history.

**Consequences:** The history is never empty, and its count on the order page is at least 1. Being derived, it needed no migration and covers every existing order at once; a status changed without a history row would make it wrong, and none does (`OrderRepository.update_status` is the only writer of `orders.status`). `from_status` is now nullable in the API (`API.md`).


## 2026-09-27 — A Finance page, from the fees Anvero already reads

**Decision:** A Finance page (`/finance`, in the menu after the inbox), chosen by the owner from three mockups ("A: report of the period", with the orders table of "C" opened from the fees figure). Periods: this month, last month, 7, 30 and 90 days, each compared with the period of the same length just before. The summary shows sales, marketplace fees with their share of sales, what is left, and what is left per order; the fees by kind with the change; sales and fees by channel; and the check of Allegro's fees against what it took from the proceeds (`PAD`), with when the fees were last read and, for the month so far, a forecast. The fees figure opens the period's orders with commission, delivery and other fees, the share and what is left, sortable by that share. A Products tab shares each order's fees among its products. Three read-only endpoints, `GET /finance/summary`, `/orders` and `/products` (`API.md`); `app/services/finance.py` computes them.

**Rationale:** The billing entries were already read into `billing_entries` and shown only per order. On the owner's data the fees of September came to 939.43 zł and Allegro took exactly that from the proceeds, so the check can be made from Anvero's own data instead of retyping Allegro's total, as AlleIntegrator asks. The Products tab showed at once what the orders alone hide: 45 hearts at 1.30 zł paid Allegro's minimum commission, 0.49 zł each, 37.7% of their price.

**Consequences:** Two bases, stated on the page: the summary counts fees by the day booked (so it matches Allegro, and includes fees of orders placed earlier or of none), the tables by the orders placed in the period (so each row says what that order left). Their fee totals differ by the fees of older orders. `PAD` is the only settlement type known; another would be counted as a fee (or a credit) until added to `SETTLEMENT_TYPES`. Only `PLN`. Erli's fees, rebates and payouts, Allegro's payouts, product costs and advertising are not built yet: Erli's API has them all (`/billing/company/entries`, `/billing/company/rebates`, `/payments/payouts/_search`, `/campaigns/campaigns-summary`), Allegro's payouts need `/payments/payment-operations`.


## 2026-09-27 — Erli's fees and payouts; settlements marked on the entry

**Decision:** The Erli import reads Erli's billing account (`/billing/company/entries`) into `billing_entries` and its payouts (`/payments/payouts/_search`) into a new `payouts` table, riding on the billing sync point. What each entry is comes from Erli's own dictionary (`/dictionaries/billingEntryTypes`, read every import): `plusCharges` and `minusCharges` are fees, `plusPayments` settlements, the rest is not stored. Whether an entry is a settlement is now a column, `billing_entries.is_settlement` (migration `d8b3f1a6c925`, which marks Allegro's `PAD` rows), set by the adapter, instead of a list of type codes in the finance code. The Finance page shows each channel's payouts, and its check compares the fees and settlements over everything held rather than within the chosen period.

**Rationale:** Erli's account is a ledger, not a list of fees: rebates set aside, blocked amounts and campaign money move through it too, and counted as fees would be wrong twice over. Erli says itself what each kind is, so a kind it adds later is sorted without a change here. Within September the owner's Erli fees (124.13 zł) and settlements (145.11 zł) differ because Erli took the fees of late August in early September; over all that is held (31 July to 26 September) they are equal to the grosz, 205.30 zł, as Allegro's are (939.43 zł).

**Consequences:** Run `alembic upgrade head` on each machine (the shared database was migrated on 2026-09-27). The first read of Erli's billing went back 120 days by hand; a machine starting afresh reaches back `ERLI_INITIAL_IMPORT_DAYS` (7). Erli's fees in a month can far exceed what its orders in Anvero sold: Anvero holds Erli orders only from 13 September, while the fees go back to July, and Erli charges the seller for its delivery (`SHIP`, 77.83 zł in September against 127.03 zł of sales). Allegro's payouts are still not read.


## 2026-09-27 — Erli's older orders imported; delivery set apart on the Finance page

**Decision:** Erli's orders were imported 90 days back by hand (`scripts/import_erli.py --days 90`, 10 created), so each Erli fee held has its order. The Finance summary reports, per marketplace, what the buyers paid for delivery (`delivery_paid`) beside the delivery fees booked (`delivery_fees`); the page shows a Delivery card (paid, charged, and whether it comes out even or what the seller pays on top) and the fees' share of sales without delivery beside the share with it.

**Rationale:** The owner found Erli's fees too high: 124.13 zł against 127.03 zł of September's sales. Half of those fees (62.18 zł) were for four orders of 1–11 September that Anvero did not hold, since the Erli import had started on 13 September. And Erli's delivery fee (`SHIP`) equals to the grosz what the buyer paid for delivery, so it is money passing through, while Allegro Smart charges the seller for parcels the buyer did not pay for (in 22 of 31 orders with a delivery fee the buyer paid nothing).

**Consequences:** The imported older orders took the numbers AN-000068 to AN-000077, after the newer ones. September now reads: sales 3,498.10 zł, fees 1,063.56 zł (30.4%), 21.6% without delivery; Allegro 21.0%, Erli 34.1% without delivery, since Erli's commission (about 20% of the whole order, delivery included) is charged on the delivery too. An order not yet shipped has its buyer's delivery counted and the delivery fee not yet booked, so a period can show delivery "left over" that later comes out even.


## 2026-09-27 — Allegro's fees and orders read back to 30 August; the subscription counted

**Decision:** Allegro's billing and order sync points were moved back to 30 August in the database, so the next import (run from the machine that imports Allegro, not by hand elsewhere, since the refresh token rotates) read Allegro's fees and orders from then. The subscription ("Abonament profesjonalny", `SB2`, 199.00 zł on 14 September) is an ordinary billing entry: the Finance summary counts it among the fees by the day booked, like any fee naming no order. On the page, fees of one marketplace with the same name are one row (Allegro books One Kurier under `DXP` and `HXO`), and rows of 0 (Allegro's `SUM`, "Podsumowanie miesiąca") are hidden.

**Rationale:** The owner pays Allegro's subscription and asked for it to count. The billing had been read only from 18 September, so neither the September subscription nor the fees of the orders of 1 to 17 September were held, and Anvero held only 63 Allegro orders; reading the fees alone would have counted 158 orders' fees against none of their sales.

**Consequences:** Anvero now holds 189 Allegro orders. September: sales 8,747.94 zł from 181 orders, fees 2,853.78 zł (23.5% without delivery), subscription included; everything read is settled for both marketplaces. The delivery fees of 32 orders placed in August and sent in early September fall into September, as in Allegro's own statement; their sales are in August, which Anvero does not hold. The imported older orders took numbers after the newer ones.


## 2026-09-27 — Allegro's payouts, read on their own

**Decision:** An import reads Allegro's payouts from `GET /payments/payment-operations` (`group=OUTCOME`), keeping `PAYOUT` (by `payout.id`) and `PAYOUT_CANCEL` (the same id with `:cancel`, negative) in `payouts`. Payouts, Erli's included, are now read in a step of their own after the fees (`OrderImportService._sync_payouts`), from a week before the latest payout stored, instead of riding on the fees' sync point.

**Rationale:** The owner saw Erli's payouts on the Finance page and not Allegro's. Allegro needs a scope of its own for payments (`allegro:api:payments:read`); read with the fees, a refusal would have rolled the fees back and kept their sync point from moving at every import. The latest stored payout is a sync point that needs no column, and reading a week back catches a payout cancelled after it was read.

**Consequences:** Not yet checked against the real account: the first import after a restart shows whether the application has the scope (the log says so if not; then add the scope in Allegro's developer panel and connect the account again). Until a payout is read, the Finance page shows none for Allegro rather than 0. A cancelled payout lowers the period of its cancelling, not of the payout.


## 2026-09-27 — Integrations move into Settings as a tab

**Decision (owner):** The Integrations page is no longer a page of its own: it is the second tab of Settings (`/settings?tab=integrations`, the chosen integration in `&integration=`). The menu entry is removed; `/integrations` redirects to the tab. This replaces the page decided on 2026-09-25 ("Integrations are a page of their own").

**Rationale:** Accounts, keys and the sender are set up once and rarely touched again, so they do not earn a place in the menu; Settings already holds the App status tab on the same reasoning.

**Consequences:** Links to set something up point at the tab. The component `Integrations` stays, without its own heading.


## 2026-09-27 — Non-invoiced sales report, ported from a standalone tool

**Decision (owner):** Port a standalone browser tool the owner built earlier (kept under `temp/`,
out of this repository) into Anvero as a new page, "Raport bezrachunkowy" (own place in the menu,
mockup A — list with a side drawer, chosen from three drawn for the owner). It classifies orders
for the accountant into a non-invoiced sales report. Only the tool's own **approved** business
decisions are ported (`temp/sales-report-v2/BUSINESS_DECISIONS.md`, BD-001/BD-015 and BD-002):

- A complete company invoice (name, street, postal code, city, country and tax id on the invoice
  address) excludes the order as `COMPANY`, never open to a manual override.
- An order the marketplace shows cancelled or suspended, never paid in full, excludes as
  `OUT_OF_SCOPE`.
- Everything else is `MANUAL_REVIEW`: the tool's own 24-decision register (`06_DECISIONS_REQUIRED.md`
  in it) leaves the report's definition, the amount source, currency, NIP handling, duplicates and
  returns unresolved, and its code must not guess them either.

An operator can override a `MANUAL_REVIEW` or `OUT_OF_SCOPE` row (`sales_report_overrides`, kept
by `(source, order_external_id)` like `billing_entries`), and export the result as CSV.

**Rationale:** The tool's own code (`qualifyV1` in `js/business/rules/rule-utils.js`) actually goes
further than its approved decisions - it auto-includes a paid, sent, uninvoiced-or-personally-invoiced
order as `RETAIL` on its own - but that path has no entry in `BUSINESS_DECISIONS.md`, so by the
tool's own rule ("No Business Rule may be implemented without an APPROVED Business Decision") it
should not have shipped either. Anvero does not repeat that: every order without a decided category
lands in `MANUAL_REVIEW`, so `retail` was 0 in every report at first - until the owner saw how large
that left "for review" and asked for that very rule back; see "PAY-001 approved" below, the same day.

The report reads Anvero's own already-imported orders (no CSV upload yet); the owner also wants an
upload path for orders outside Anvero, and asked to expand which of the tool's 24 open decisions
are approved once this is in use. Both are follow-ups, not part of this decision.

**Consequences:** A new table, `sales_report_overrides` (migration `a2f4c8e1b937`); a new page and
API (`API.md`, "Non-invoiced sales report, ported"). Excel and PDF export, and reading a CSV file
directly, are not built yet. The report's export carries only what accounting needs - order,
source, date, the buyer's login, amount, category, inclusion, reason and rule id - never a name,
address, phone or e-mail (`ROADMAP.md`, "GDPR (RODO): to do").


## 2026-09-27 — PAY-001 approved: paid, shipped, uninvoiced order qualifies as RETAIL

**Decision (owner):** Approve the third rule the ported tool's own code already applied without an entry in its `BUSINESS_DECISIONS.md` register (`qualifyV1`, see "Non-invoiced sales report, ported" above): an order paid in full, in PLN, shipped (Anvero's own status `SHIPPED` or `DELIVERED`), with no invoice or only a named personal one (a name present, never a company name or tax id) qualifies as `RETAIL`, included in the report, on its own (`PAY-001`). Priority stays the ported tool's own: `INV-001` (company invoice) first, then `SEL-001` (cancelled/suspended, unpaid), then `PAY-001`, else `MANUAL_REVIEW`.

**Rationale:** The owner ran the report against Anvero's own September orders and found "do weryfikacji" far larger than what they remembered from using the ported tool day to day. `temp/sales-report-v2/RULE_REFINEMENT_REPORT.md` explains the gap: on the ported tool's real June baseline (614 orders), only 74 needed manual review, because `qualifyV1` already qualified the rest as `RETAIL` - a rule the owner had in fact been relying on, just never formally registered. Anvero now registers it.

**Consequences:** "Shipped" is read off Anvero's own status, not the marketplace's raw `marketplace_status_label` as the ported tool's literal `SellerStatus === "SENT"` did: that label's vocabulary is wider on Anvero (e.g. `READY_FOR_PICKUP`) than the CSV export the ported tool read, which only ever held `SENT`, `CANCELLED` or `SUSPENDED`. Anvero's own status collapses that the same way and is the operator's own last word on an order (`DATABASE.md`, "marketplace_status_label"). `PAY-001` rows are open to a manual override, like `SEL-001`'s and `MANUAL_REVIEW`'s; `INV-001` stays the only rule an override cannot reach.


## 2026-09-27 — Export columns, chosen by the owner

**Decision (owner):** The CSV export's columns are no longer fixed. A picker (mockup D, drawn for the owner) lets an operator choose which columns go into the file and in what order, from every field the order carries. The default, without a choice, is the owner's own: a running number, the order's date, the buyer's name (`customer_first_name`/`customer_last_name`, not the invoice address's name) and the amount actually paid (`paid_amount`, not the amount due) — the same four columns, in the same order, as the accountant's own earlier report (`temp/`, an `orderReport-…_report.csv` read this session: `LP, Data zakupu, Imię i nazwisko, Kwota`). `GET /api/v1/sales-report/columns` lists the full catalog and the default; `GET .../export` takes `columns` (comma-separated keys, in order).

**Rationale:** The buyer's name is more identifying than the login the export carried until now, and the owner asked for it as the new default anyway — the owner's call to make as the report's data controller, not something to withhold on Anvero's own initiative. The picker still flags the more identifying fields (name, e-mail, phone, address) so choosing them stays a conscious act, and every other field (login, NIP, company name, amounts, the report's own classification) is available but off by default.

**Consequences:** The export's personal data is now the owner's own choice per column, not fixed to a login. The chosen columns are remembered in the browser (`localStorage`, `salesReport.exportColumns`), not on the server — a per-operator, per-machine convenience, on or off with its own checkbox. Amounts in the CSV use a comma decimal separator (`62,69`), matching what the accountant already received. Excel and PDF exports, once built, take the same `columns` choice.


## 2026-09-27 — Packing progress, per line

**Decision (owner, from mockup F3):** Mark, on the order's own page, how many of each line an
operator has physically gathered into the parcel for that order - not the "to make" queue
(`production_checks`, per-product across every order, deliberately silent on which order a
finished piece goes to), a separate concern: an order is often assembled from a partly-ready
basket, waiting on the rest. A stepper per line ("N / M"), a card-level progress bar and a
summary ("2 of 4 items packed · 26 of 31 pcs"); a fully packed line is dimmed with a checkmark.
Shared across every computer (`order_item_packing`, `PATCH /orders/{id}/items/{position}/packing`),
the same reasoning as the "to make" list: someone else, or another machine, may finish the order.

**Rationale:** Kept by `(order_id, position)`, never `order_items.id`: a re-import replaces every
item row of an order wholesale even when nothing about the item changed
(`app/services/order_details.py`), so keying by the item's own id would silently wipe an
operator's progress on the very next scheduled sync (every 15 minutes by default). `position` is
the marketplace's own line order and survives a re-import of the same order. Cleared once the
order reaches `SHIPPED`, `DELIVERED` or `CANCELLED`: packing an order that has already gone is
moot, whether an operator moved it there by hand or an import's own auto-follow did - both funnel
through the one chokepoint, `OrderRepository.update_status`, so a single clause there covers both.

**Consequences:** New table `order_item_packing` (migration `b4e6f9c2a831`); run
`alembic upgrade head`. `GET /orders/{id}` now carries `position` and `packed_quantity` on every
item; the on-screen order list is untouched. Never sent to a marketplace. A line the marketplace
later reports at a different quantity keeps whatever was ticked, capped at the new quantity by
`OrderService.set_item_packing`'s own validation on the next write, not retroactively.

**Also (2026-09-27, the owner tried it):** clicking the product name (or its thumbnail) packs
the whole line in one go - `quantity`, not one more - and clicking it again unpacks it; the +/−
stepper is for the odd one left over, not for reaching a many-unit line's total one click at a
time. The cell is a `<button>` now, reset back to plain text and thumbnail with no button chrome
of its own; `ItemThumb`'s zoom-on-hover (`docs/CHANGELOG.md`, "An item's zoom-on-hover covers its
whole row") still works nested inside it.

**Also (2026-09-27, the owner asked):** the "to make" list (`build_production_list`) now deducts
what is already packed from what each product still needs: a unit already packed into a parcel
must already exist, so it no longer needs making. Every order's `OrderItemPacking` rows are
loaded alongside its items (`OrderRepository.list_in_queue_with_items`) and matched by position,
the same key packing itself uses. A product every waiting order's packed count already covers
reaches `quantity: 0` and reads as made (`mark_done`'s own `ticked >= quantity` check passes
at 0 with no tick at all) - it still appears on the list, foldable under "Hide made" like a
manually ticked one, rather than disappearing outright, so packing and a manual tick behave alike.

## 2026-09-27 — Automatic Update Deployment

**Decision:** An application update deployment mechanism is planned, not yet implemented. Two
approaches are being considered: webhook-based (push, triggered by GitHub on a new release) or
polling-based (pull, checking for updates on an interval). The feature will be exposed through
`GET /api/v1/admin/updates/` (read available updates, check current version) and
`POST /api/v1/admin/updates/` (trigger deployment), accessible only to administrators. The UI
will show update status and notifications in the Settings page, with an option to deploy on
demand or on a schedule.

**Rationale:** Automatic updates ensure the system stays patched and gains improvements without
manual intervention at the NAS. The choice between webhook and polling will be made after
evaluating the trade-offs: webhooks are faster and lighter but require the application to be
reachable from GitHub; polling is simpler and works behind firewalls but adds latency and
overhead. The endpoint scope (`/api/v1/admin/updates/`) mirrors the admin protection already in
place for sensitive settings, so authentication and authorization reuse the existing login. Safe
mode applies here: a deployment can be staged and tested before going live.

## 2026-09-27 — First NAS Deployment: Port 8081, Backend Joins the Database's Network

**Decision:** The NAS deployment (`DEPLOYMENT.md`) is reached at
`http://NAS_ADDRESS:8081`, not 8080 as originally planned, and the backend
container is joined to the PostgreSQL stack's own Docker network
(`networks:` in `deploy/docker-compose.yml`), with `DATABASE_URL` pointing at
the database container by name rather than the NAS's LAN address. While at
it, nine leftover `alleintegrator-customer-*` containers and images from
earlier integration testing were removed from the NAS, reclaiming about 1 GB.

**Rationale:** Port 8080 is already bound by the NAS's own `apache_proxy`
service, discovered when `docker compose up` failed with
`address already in use`; 8081 is free and is now the permanent port. The
database connection failed differently: the backend and the database run as
two separate `docker compose` stacks, each getting its own default bridge
network, so the backend could not resolve the database by container name, and
connecting to the NAS's own LAN address from *inside* a container on this NAS
timed out (`ConnectionTimeout`) rather than hairpinning back in, unlike a
real machine on the network reaching the same published port. Joining the
backend to the database's network and addressing it by container name
sidesteps both the missing name resolution and the hairpin problem. This
changes `deploy/docker-compose.yml` itself (port and an added `networks:`
block), not just the NAS's local, gitignored copy, since both fixes would
recur on every fresh deployment otherwise. Left open: which update path the
NAS actually uses going forward (`DEPLOYMENT.md`, "Updating") - this session
updated the running application over SSH from what it described as a git
clone rather than through Container Station and the published GHCR images.
**Resolved the same day:** the NAS's application directory holds only the
compose file (no `.git`, no `build:` context), so `docker compose pull` /
`up -d` against the published GHCR images is the only real update path; the
earlier description must have referred to a different, no-longer-present
location.

## 2026-09-27 — Database Password Rotated, and the Network Join Made to Survive a Recreate

**Decision:** The `anvero` PostgreSQL role's password was rotated (the old
one had been pasted into a chat session and so counted as exposed), and the
NAS's `docker-compose.yml` was patched with the same `networks:` block now in
`deploy/docker-compose.yml` (see above), so that `docker compose up`/
`--force-recreate` on the backend keeps its join to the database stack's
network instead of losing it, which is what had made the previous fix
(a bare `docker network connect`) disappear on recreate and crash-loop the
backend (`failed to resolve host 'anvero-db-db-1'`) until reconnected by
hand. Confirmed by forcing a recreate: both networks (`anvero_default`,
`anvero-db_default`) came back on their own, health passed immediately.

**Rationale:** An assistant performing the rotation deliberately never held
the new password as plaintext - it was generated, applied to PostgreSQL and
written into the NAS's compose file in a single remote step, never in a
command or file the assistant's own tooling could read back. That means the
new password is known only to whoever reads it directly off the NAS (`grep
DATABASE_URL` on the compose file, or Container Station's own view of it),
not to this document or any chat log. Every other machine's `backend/.env`
pointing at the shared database (`DEVELOPMENT.md`, "Shared database on the
NAS") still has the old password and needs updating by hand from that same
read, or it will stop connecting.

## 2026-09-28 — A Product's Fees Are Credited for What the Buyer Paid for Delivery

**Decision:** `FinanceService.products` (the Finance page's Products tab)
now offsets a product's share of an order's delivery-kind fees by what the
buyer paid for delivery (`Order.delivery_cost`), capped at the delivery fee
actually booked for that order - never more, so a marketplace whose delivery
fee is not billed as its own fee is left untouched. Found from a real
example: SKU D2717 (a single cheap item, 8.99 PLN) showed `-4.86 PLN` left
after a `-10.49 PLN` DHL courier fee and `-3.36 PLN` commission, which looked
like the product itself lost money - but the buyer had paid exactly `10.49
PLN` for that delivery (`Order.total_amount` was `19.48`), so the order as a
whole made `+5.63 PLN`. The product view only ever showed the cost side.

**Rationale:** `sales` at the order and summary level already includes what
the buyer paid for delivery (`Order.total_amount`), netting correctly against
the full delivery fee; the Products tab deliberately excludes delivery from
a product's `sales` instead (a shared, order-level charge, not really any
one product's sale), but had been including the *full* delivery fee as that
product's cost regardless - the one place this stayed asymmetric. Crediting
the fee instead of adding to `sales` keeps the "Sprzedaż" column meaning the
product's own price, while "Zostaje" (sales − fees) now agrees with what the
order itself actually left. The cap at what was actually booked matters
because `delivery_cost` is what the buyer paid, which is not always what the
marketplace later bills the seller for it (e.g. a cash-on-delivery
surcharge): crediting beyond that would manufacture profit the fee entries
never showed. Covered by
`tests/api/test_finance.py::test_a_products_delivery_fee_is_offset_by_what_the_buyer_paid_for_it`
and `::test_the_delivery_credit_never_exceeds_the_delivery_fee_actually_booked`
(958 backend tests passing).

## 2026-09-28 — Fixed: orders stuck showing "ready to ship" after Allegro marked them sent

**Decision:** Amends "Writing to Allegro: the last change made in Anvero wins"
(2026-09-24). `OrderImportService._set_by_hand_since` now compares
`orders.status_set_at` against the *importing run's own start time*, not
against the marketplace's `updatedAt` on the checkout form. Found from a real
example: 11 real orders, packed and marked `READY_FOR_SHIPMENT` by hand, whose
label had since gone out through "Wysyłam z Allegro" - Allegro had moved them
to `SENT`, `orders.marketplace_status` already said so, but `orders.status`
never followed, so the list kept showing them as waiting to ship.

**Rationale:** `INTEGRATIONS.md` ("Every later import") already documents that
Allegro's `updatedAt` does not reliably move for a fulfillment-only change (a
parcel created, marked ready, or sent) - that is exactly why the import also
re-asks about every open order regardless of the window. The by-hand guard
used that same unreliable field as its "did Allegro move after the operator's
change" signal, so for the normal pack-then-ship sequence it almost always
saw a stale Allegro timestamp and concluded the operator's change was newer -
permanently, since once `marketplace_status` is updated to match, the next
import's `status_moved` check (comparing against the *previous* import's
`marketplace_status`, per "The Anvero Status Follows Allegro") sees no further
move and never retries. The run's own start time is Anvero's clock, not
Allegro's, and still protects against the race the 2026-09-24 decision was
written for: a fetch already in flight when the operator acts should not
overwrite the newer choice with what it already had in hand.

**Consequences:** The 11 stuck orders were moved to `SHIPPED` directly in the
shared database (`scripts/reconcile_stuck_status.py --apply`, no author on the
history entry, same as the importer's own auto-follow) rather than waiting for
the next import, since fixing the code does not by itself unstick an order
whose `marketplace_status` had already caught up. The script is kept for any
order found stuck the same way later; it only ever moves an order *forward*
along NEW → CONFIRMED → READY_FOR_SHIPMENT → SHIPPED → DELIVERED, never
touches CANCELLED, and never moves one where Anvero's own status is already
ahead of `marketplace_status` (the carrier-delivery auto-advance from
2026-09-26 relies on being left alone). Deployed to the NAS the same day,
alongside the roles/GDPR/updates merge below (`/api/v1/health` there answers
`commit: 286ab9d`). Covered by
`tests/services/test_order_writes.py::test_a_fetch_already_stale_when_the_operator_acted_does_not_undo_it`
and `::test_a_run_started_after_the_operators_change_follows_the_marketplace`
(958 backend tests passing).

## 2026-09-28 — Fixed: disputes and claims needed the beta Accept header

**Decision:** `AllegroClient.fetch_issues` (`GET /sale/issues`) now sends
`Accept: application/vnd.allegro.beta.v1+json`, the same beta header
`fetch_customer_returns` already used. Found from the owner's first real
click of "Wczytaj z Allegro" on the Returns and claims page (plan B4): Allegro
answered `406`, "Request contains invalid data." `developer.allegro.pl`'s own
tutorial for the endpoint confirms every resource under `/sale/issues` is
beta.v1 and needs that header; the code had only ever sent Anvero's default
`application/vnd.allegro.public.v1+json`, built without seeing a real
response (`INTEGRATIONS.md`, "Returns and claims" said as much: "Nothing here
has run against a real account"). The test guarding this
(`test_issues_are_asked_for_by_status_with_the_public_version`) had been
written to match that guess, asserting the header was *not* the beta one -
renamed and inverted to assert it is.

**Rationale:** No way to have caught this without a real response: the
specification excerpt available while it was built did not show the header,
and a fake transport in a test only confirms the code does what it was
written to do. The fix is narrowly the header; the status filter, paging and
the mapping were not touched and read correctly on the first real try.

**Consequences:** Verified live against the owner's real Allegro account
(read-only `GET`, no write): open issues (0), closed issues (10) and customer
returns (10) all came back successfully. This is B4's first real run;
`INTEGRATIONS.md`'s "Unverified" list for it (the 14/45-day rules, whether
`WAREHOUSE_*` returns need the seller, a dispute with no `lastMessage`) still
stands - only the read itself was confirmed, not those business rules against
real cases. Covered by
`tests/integrations/test_allegro_after_sales.py::test_issues_are_asked_for_by_status_with_the_beta_version`
(958 backend tests passing, one renamed).

## 2026-09-28 — Accounts Get a Role and Per-Area Permissions

**Decision:** `users` gets a `role` column (`admin` or `user`, plain strings
like `payment_type` rather than a database enum, since the list of what a
role means can grow) and a new `user_permissions` table (migration
`c2a6f9e3b184`), one row per `(user_id, area)`: `area` is one of `orders`,
`messages`, `after_sales`, `labels`, `finance`, `integrations` - the same six
areas Settings groups the application into - and `level` is `view` or
`manage` (`manage` satisfies a `view` check too). An admin needs no rows: it
passes every check outright. A new `require_permission(area, level)`
dependency (`app/core/permissions.py`) replaces the plain "logged in" gate on
every router except `auth` and `health`; `API.md`'s "Users, roles and
permissions" section lists which area and level each endpoint needs.
Settings gets a "Users" tab, visible only to an admin: a list of accounts on
the left and the one chosen open on the right (`docs/STYLE_GUIDE.md`), where
an admin creates an account (typing its password directly, like
`scripts/create_user.py` already did - there is still no self-service
registration), and sets its role, active state and, for a "user", a grid of
the six areas each with a three-way choice (none, view, manage). The
migration set every account that already existed to `admin`, and
`UserCreate.role` still defaults to `admin` (matching the script's own
`--role` default), so every caller written before roles existed - the whole
test suite included - keeps the full access it always had; only a "user"
account created from the new Users tab, which always sends `role`
explicitly, starts out limited. An admin cannot demote or deactivate the
account that would leave zero active admins (`UserService.update_user`),
checked against every other admin account, not just the ones created this
session.

**Rationale:** The owner asked for two account types (administrator, user),
permissions on the user kind assignable per area of the application, and
several people working from different accounts at the same time; the last
part needed no new work, since logins are independent JWTs with no shared
session lock already. Three permission granularities were on the table (per
area, per exact action, or a flat view/full split); the owner chose per area,
coarse enough that the settings screen stays a short grid rather than dozens
of checkboxes, matching how the application's own pages are already grouped.
Two of Integrations' own endpoints - the Allegro messages and after-sales
syncs - are gated by the `messages` and `after_sales` areas instead of
`integrations`, since triggering them is naturally part of managing those
areas, not the marketplace connection itself; every other Integrations
endpoint, including safe mode, needs `integrations`. A JWT lasts up to eight
hours and cannot be revoked early (`API.md`); the owner accepted that a
deactivated or downgraded account's already-issued token still works until
it expires, rather than building session revocation now. A regression
surfaced during manual verification: replacing a user's whole permission set
in one request, keeping some areas and adding another, violated the
`(user_id, area)` uniqueness before the old rows were gone, because clearing
a SQLAlchemy collection and appending replacements in the same flush queues
the inserts before the deletes; `UserRepository.replace_permissions` now
flushes the clear before appending (test:
`test_replacing_permissions_while_keeping_some_of_the_same_areas`).


## 2026-09-28 — Retention periods and erasure (GDPR)

**Decision (owner, from the plan put to them):** Buyers' personal data is erased once it has no purpose left, by a daily run in the backend and not only by hand: orders five years after the end of the year in which their tax was due (in practice: an order from year Y is anonymized on 1 January of Y+7, Polish time); message threads two years after their last message; after-sales cases two years after they were opened, once closed; what Anvero sent to a marketplace (`marketplace_writes`) two years after it was sent, or with its order. Erasing is anonymizing, not deleting: `anonymized_at` is set on the row (migration `a7d4e2c9f136`), the fields that name, reach or quote a person are emptied (`customer_email` becomes `''`, being required), and numbers, dates, amounts, items and the delivery country stay. An import or sync no longer touches an anonymized order or case; a thread the buyer writes in again is a new contact and kept from then, the old messages staying erased. One buyer's request is answered by `scripts/export_person.py` and `scripts/anonymize_person.py`, found by login or e-mail; erasing on request keeps a company invoice's name, tax id and address while the tax period runs, and the daily run erases those after it. The list's search moves out of the address into the history entry's state. Integration secrets are encrypted when `SECRETS_KEY` is set, plain text otherwise. Reads are not logged; a sales report export with a personal column is.

**Rationale:** The owner chose each period and the automatic run from the options offered. The order period counts from the year the tax was *due*, not the year of the order, because the statute of limitations does (Ordynacja podatkowa art. 70 and 86): counting from the order's year would erase December's orders while their income tax could still be examined, one year early. Anonymizing rather than deleting keeps past figures and reports whole and keeps an import from bringing the order back, which a deleted row could not stop. The run is its own loop, not a job of the import schedule, so switching imports off does not stop data from ageing out, and it needs no lease: anonymizing twice is harmless. The search is often a buyer's name or login, and an address holding it stays in the browser's history and suggestions; the state survives reloads and "back" like the rest. `SECRETS_KEY` is opt-in because every backend sharing a database needs the same key and losing it means authorizing Allegro again: turning it on is the owner's step, with the key in the password manager, not something a deployment should do silently. Reads are not logged because with a few accounts on a private network such a log would be one more copy of who bought what; bulk exports are the way data leaves, so those are.

**Consequences:** `GDPR.md` is the description of what is held, the periods and how a request is answered; `DATABASE.md` and `API.md` carry the new column and field. The retention run writes `retention_last_run` to `app_settings`. `OrderRead.customer_email` is a plain string in responses (an anonymized order's is empty). The first run on the NAS will erase threads quiet for over two years, if any were read from Allegro's history. A restored backup needs the retention run and the erasures answered since then run again; the owner keeps the register of requests outside Anvero.


## 2026-09-28 — Updates from Settings

**Decision (owner chose the look, variant C of three mockups):** The plan of 2026-09-27 ("Automatic Update Deployment") is built as polling, not a webhook. A version is a commit on `main` whose `anvero-backend` and `anvero-web` images are both on GHCR; the backend knows its own from `APP_COMMIT`, baked into the image by the publish workflow, and every 30 minutes reads the newest 20 commits from GitHub's public API and asks GHCR anonymously which is the newest published. An administrator sees a banner above every page ("An Anvero update is available", closable until the next version) that only points at a new Settings tab, Updates, where the versions, the commits in between and the button are. The button asks a third container, `updater` (its own image, `updater/`), to run `docker compose pull backend web` and `up -d --no-deps backend web` against the NAS's own compose file; the page then waits for `/health` to name the new commit and reloads itself. `GET`/`POST /api/v1/admin/updates` are administrator only.

**Rationale:** A webhook needs the NAS reachable from GitHub, which it deliberately is not (`DEPLOYMENT.md`, "Limits"); polling a public repository needs no token and no open port, and half an hour's delay is nothing for an update someone clicks anyway. A commit counts only once its images exist, because that is what can be installed and what passed the checks - a commit on `main` alone could be a failing one, as the three commits of this morning were. The button is only in Settings, not on the banner, so nobody takes the application down for a minute with a slip in the middle of packing. A container cannot recreate itself, so something outside it must; the updater holds the Docker socket, which is root on the NAS, so it is kept to the minimum: no published port, a token of at least 32 characters, two fixed commands, and it never recreates itself (a run would cut itself short). Recreating from the compose file on the NAS, rather than from the Docker API, recreates the containers exactly as Container Station created them.

**Consequences:** Updating needs the published images; a NAS building from a clone gets the banner but its button would recreate from GHCR. Rolling back stays manual (a commit's short hash in place of `latest`, recreate). A new updater image is taken up only by recreating the application by hand. `/health` now carries `commit`, which is public, as the repository is.


## 2026-09-29 — The order page's summary: status in the header, payment folded, an Allegro Smart badge

**Decision (owner, approved from inline mockups on 2026-09-28, second of two rounds):** The merged Płatność/Zamówienie/Wysyłka bar of the first round (`.order-summary-bar`) is gone. The status picker (any status, as before) and its facts - time in the status, the send-by deadline, the marketplace's own status as "Allegro: X" - now sit in `OrderHeader`, on one row under the unchanged step pills, separated by " · "; the save error, the note on what the marketplace did with the change and the "marketplace reports otherwise" note sit under that row. `OrderFactsCard.tsx` is deleted; `OrderHeader` takes `saveError`, `writeNote` and one `onStatusChange` for both the next-step button and the picker (formerly `onNextStep`). Payment moves into the folded sections as "Płatność", right after "Historia statusów", with what was paid as its summary; its body is `OrderPaymentCard` in a new `embedded` form, keeping its paid/unpaid colour class. Wysyłka is its own `.order-card` again between the address cards and the messages; its collapse behind "+ Dodaj kolejną przesyłkę" once a parcel exists (first round) stays. An Allegro Smart delivery shows a "Smart!" pill (Allegro orange on near-black, `smartBadge.tsx`) in the header's badge row, on the Dostawa card beside the carrier badge, and in the order list's shipping cell.

**Data:** Allegro's checkout form carries `delivery.smart` (boolean). The mapper now reads it (`true` only when Allegro says exactly `true`), `Delivery.smart` carries it, and `orders.delivery_smart` (migration `b3e8d1f4a627`, not null, default false) stores it. The list response gets a flat `delivery_smart`, like `invoice_required`, since `GET /orders` carries no `delivery` object. Erli has no such concept and stays false.

**Rationale:** The first round, once filled with a real new order, read as small-caps labels crammed against values. The status is what the operator changes most, so it belongs next to the step road it moves along; payment is rarely acted on from this page, and the list already says whether an order is paid. Smart matters for how the parcel is sent and what delivery costs the seller, so it is shown wherever the carrier is.

**Consequences:** `.carrier-badge` moved to its own `styles/CarrierBadge.css`, imported by both badges, so the list can use it without the order page's stylesheet. Orders imported before this read as not Smart until the next import refreshes them (the importer re-applies details). `API.md` and `DATABASE.md` updated.

**Verified:** backend 1020 and frontend 608 tests, `tsc --noEmit`, the migration applied to the shared NAS development database, the restarted backend's `/openapi.json` carrying `delivery_smart`. **Not verified:** the page in a browser (needs the owner's login) - a Smart and a non-Smart order, with and without a parcel, light and dark; and whether the sandbox or production Allegro actually sends `delivery.smart: true` on a real Smart order.


## 2026-09-29 — Fixed: an Erli order's fees counted Erli's "pobranie opłaty" as a fee

**Found by the owner on AN-000071 (Erli, 28.75 PLN):** the order page's "Opłaty marketplace'u" listed "pobranie opłaty +27.12" beside the real fees (-6.14 in all), so the fees read +20.98 and the order after fees 49.73 PLN instead of 22.61. That entry (Erli's `PAYM`, `fiscalFunction: plusPayments`) is Erli taking fees already booked out of this order's proceeds - often other orders' fees too - and the import already marks it `is_settlement`, which the Finance page leaves out. `GET /orders/{id}/billing` did not: Allegro's own settlement (`PAD`) never names an order, so the gap only showed once Erli's billing was read, since Erli ties its settlement to the order it was taken from.

**Decision:** `OrderRepository.list_billing_entries` leaves settlements out, so the order's fees and their total are fees only (`API.md` says so). Nothing stored changes.

**Verified:** a test with AN-000071's entries; the repository run against the real database gives -6.14 and 22.61 for AN-000071; backend restarted. Not yet looked at in the browser.


## 2026-09-29 — An order's fees name the SKU of the item they are for

**Decision (owner):** Each fee on the order page's "Opłaty marketplace'u" that is for one item - a commission is charged per offer - shows that item's SKU after its name ("naliczenie prowizji · SKU D1563"). `GET /orders/{id}/billing` gives each entry a `sku`, matched from the fee's stored `offer_id` to the order's items; nothing new is stored.

**Rationale:** An order of several items gets several commissions of the same name, and the owner could not tell which was which. The two marketplaces name the item differently: an Allegro fee carries the offer id, the same as the item's `offer_id`; an Erli fee carries `productId`, which the Erli import keeps as the item's `external_id` (its `offer_id` is Erli's `externalId`, a different number). Matching on either covers both; the two id schemes do not overlap.

**Verified:** backend tests, including an Erli-shaped case; against the real database every fee that names an offer found its SKU (0 unmatched across all Allegro and Erli orders), AN-000071's three commissions matching D1618, D1526 and D1563. Not yet looked at in the browser.


## 2026-09-29 — Update history and progress

**Decision (owner asked for both; the form is the assistant's):** Settings, Updates gets an "Update history" table - when, from which version to which, who pressed the button (or "outside Settings"), and the result with how long it took or, for a failed one, what it printed. Pressing "Update" opens a dialog over the whole application with four steps (asking the updater, downloading the new version, restarting the application, new version running), a progress bar and the time elapsed; the application under it is `inert`, so no button, link or field can be used, by mouse or keyboard, until the page reloads into the new version. A failed update says so in the dialog and a Close button gives the application back.

**How it is known:** The history is a table, `app_updates` (migration `ff7e747a62f2`), because the backend that takes the button is replaced during the update and cannot record its end: it writes an open row, and the new backend closes it on its first start when it finds itself on that version. A version reached otherwise (by hand, a first start) is written by the backend that finds it, so the history is whole from the first start of this code on. An open row is closed as failed when the updater reports its run failed after the row began, or after 20 minutes. A start the updater refused is kept as failed. The progress is not measured by the updater, which says only "running" and, at the end, its result; the steps are read from what the page can see: the updater running, then the backend gone or the updater done, then `/health` naming the new commit. The bar moves within a step toward its end, easing off, so it neither stalls nor claims more than has happened. The updater is unchanged, so no new updater image is needed. An update already under way when Settings, Updates is opened (another tab, a reload) shows the same dialog.

**Consequences:** The first update to this version is started by the old backend, which writes no row; the new one then records itself as reached "outside Settings". From then on the button's updates are recorded with who pressed them. The old "the last update failed" note is replaced by the history's own row.

**Verified:** backend tests (the history's service and API), frontend tests (steps, the inert application, failure and closing, following another tab's update, the bar), `tsc`, `alembic check`, the migration applied to the development database. **Not verified:** a real update on the NAS through the dialog - the next push after this one is the first that can show it, and the page itself has not been seen in a browser.


## 2026-09-29 — The logo

**Decision (owner, chosen from about thirty sketches over four rounds, "15b6"):** Anvero's mark is a capital A with sharp, cut-off ends, drawn as a single stroke in light teal (`#2dd4bf`, the accent's dark-mode value) on a dark navy rounded square (`#0f2e3a`, radius 12 on a 48 grid), with an amber dot (`#f59e0b`) where the crossbar would be. It replaces the 📦 emoji beside the name in the sidebar and on the login page, and is the browser tab's icon (`frontend/public/favicon.svg`, plus `theme-color`). The drawing lives once in `components/AnveroLogo.tsx` and once in the favicon file; they must be changed together.

**Rationale:** The owner's choice. What it has going for it: it stays legible at 16 px, which the lighter-stroke candidates did not; the navy square keeps it visible on both the dark sidebar and a light page; and the colours are the brand's own, fixed in both themes, like the carrier badges.

**Consequences:** The wider visual rework (`ROADMAP.md` item 5) is still on hold; this changes the mark only, not any value in `index.css`. The 📦 emoji stays where it means a parcel (the "to ship" queue, a delivered status, the Orders menu item).

**Verified:** the login page in the browser shows the mark and serves `/favicon.svg`; frontend tests and `tsc`. The sidebar needs a login and was not looked at.


## 2026-09-29 — Fixed: a new Allegro order's parcel was never read

**Found by the owner on AN-000217:** Allegro showed a parcel for the order, Anvero none. The order is an Allegro Smart InPost locker delivery still in Allegro's `NEW` handling status: the label was bought on Allegro without the order being marked as being processed first. The import asked Allegro about parcels only for orders "neither new nor cancelled" (2026-09-24, "Parcels are read for every order that is neither new nor cancelled"), assuming a new order cannot have one yet, so it never asked about this one.

**Decision:** Parcels are read for every order that is not cancelled, new ones included. It costs one more request per new order per import, since open orders are read again on every run; a shop has a handful of new orders at a time.

**Verified:** the adapter's tests, including a new order with a parcel. Not yet seen on the real order: AN-000217 shows its parcel after the next import from the machine that runs imports (the NAS), once it runs this code.

## 2026-09-29 — Allegro labels are scaled to fill 4 x 6 in paper

**Decision:** Before a label PDF from `POST /shipment-management/label` is
handed over, `app/services/label_pdf.py` makes each page 4 x 6 in (288 x 432
pt) and scales what the page draws - the paths and images of the carrier's
label, followed into its form XObject, plus 1.5 pt - up to fill it, centred
and clipped to the label. The page's own content is not rewritten: two new
content streams wrap it (a scale, and its undoing), appended with the new page
object as an incremental update. If text starts outside the label's frame,
the forms the page places are taken whole instead, as they clip what they
draw. Anything it does not read - a cross-reference stream, encryption,
inline images, a stream filter other than Flate - leaves the file as Allegro
sent it.

**Rationale:** The first real label (ORLEN Paczka) came on an A6 page with the
label scaled to 95% and set in by 8 pt plus the carrier's own border; printed
"fit to page width" on the owner's 4 x 6 in label printer it filled about 87%
of the width. Allegro's label endpoint offers only `A4` and `A6` pages, so the
fix had to be Anvero's. A first version only cropped the page to the label,
which did not help: Chrome's "fit to page" shrinks a page larger than the
paper but never enlarges a smaller one, so the cropped label printed at its
own size in a corner. The paper size is fixed at 4 x 6 in because that is the
printer the business uses; an A6 printer would get the page shrunk by 4%.
Scaling rather than redrawing leaves the barcode and QR code exactly as
Allegro made them, only larger. No PDF library is added, so the production
machine needs no new package, and the file is only read through its classic
cross-reference table, which is what OpenPDF writes. Tested on synthetic PDFs
laid out the same way and checked by eye on the real label's file (not
committed: it carries the buyer's data).

## 2026-09-29 — An Allegro order's InPost parcel is bought through Allegro only

**Decision:** Anvero's own InPost shipments (ShipX, `inpost_shipments.py`) are
for orders not from Allegro. `refusal()` refuses an Allegro order, so neither
the order page nor a batch from the Labels page can make one, and
`awaiting_parcel()` no longer lists them; the order page shows an Allegro
order no InPost tab, only "Etykieta Allegro" and a number typed in. Erli
locker orders keep the InPost tab, having no other way.

**Rationale:** On 2026-09-29 four InPost parcels for Allegro orders, three of
them Smart, were made from the InPost tab and cost 65.96 zł from the seller's
InPost balance: a shipment made through ShipX is bought on the seller's own
InPost contract at InPost's price, and InPost knows nothing of Smart. Bought
through Wysyłam z Allegro the same parcel is Allegro's, at Allegro's price
(Smart's for a Smart order), which the owner confirmed is what every Allegro
order should use. Hiding the tab alone would have left the batch on the Labels
page able to do the same, hence the refusal in the backend.

## 2026-09-29 — Fixed: InPost labels through Allegro were sent without the seller's agreement

**Decision:** Buying a label reads `GET /shipment-management/delivery-services`
along with the order's delivery method, and sends the `credentialsId` Allegro
lists for that method (`credentials_for()` in `shipping_labels.py`). None
listed: sent without, as before. More than one: refused, naming them.

**Rationale:** Allegro refused the first InPost label with "Brak poświadczeń
InPost", and wrote to the owner the same day that Allegro Paczkomaty InPost
parcels were being sent wrongly (the three made at InPost through ShipX,
billed by InPost rather than at Smart's rates), naming what the API needs:
`deliveryMethodId` `2488f7b7-5d1c-4d65-b85c-4cbcf253fd93` with the
`credentialsId` of the seller's InPost agreement. Reading it from Allegro
rather than storing it in Settings keeps nothing to set up or go stale, at the
cost of one more read per label. Guessing between two agreements could buy on
the wrong one, which costs money, so that is left to the operator.
The letter also names `inpost_locker_allegro` as the ShipX service for these
parcels; it is not used, as Allegro orders no longer make parcels at InPost
at all (the entry before this one).


## 2026-09-29 — UI work moves to Claude Design

**Decision (owner):** Improving the interface is designed in Claude Design before it is built. First the existing look was turned into a design system there (https://claude.ai/artifact/UUeEBotbDsA8UdJ7sWHMwY), from `frontend/src/index.css`, `styles/theme.css`, `docs/STYLE_GUIDE.md`, the logo and the carrier marks at `3cfbdc0`; then a first screen, the order page, as a canvas with a proposal beside today's layout (https://claude.ai/artifact/QJHBPmAH386DKwASmqmG43). Both are private artifacts in the owner's account.

**Rationale:** Screens can be compared and commented on before any code changes, and every design starts from Anvero's real tokens instead of a generic look. This is the start of the visual pass `ROADMAP.md` item 5 held back until the system ran unattended with backups, which it now does on the NAS.

**Consequences:** The code stays the source of truth for values: a token changes in `index.css` first and the design system follows (a re-sync), never the other way round. The system flagged weak contrast on the solid status badges (white on the New, Ready, Shipped, Delivered, Cancelled, Allegro and Erli fills is below 4.5:1, Shipped and Delivered below 3:1), a first candidate for the pass. Nothing in the application changed with this entry.


## 2026-09-29 — The order page in two columns

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/QJHBPmAH386DKwASmqmG43, refined over three rounds):** Under the header, the attention bar and the after-sales card, Pozycje takes the page's full width. Below it two columns: on the left the work on the order (Wysyłka, Wiadomości, the internal note, then the folded sections); on the right a 260px rail of facts (Kupujący, Dostawa, Faktura, Płatność at the bottom). Payment is a card again, in the rail, and leaves the folded sections (`OrderPaymentCard`'s `embedded` form is gone). `OrderAddressCards` renders Dostawa before Faktura. Below 900px the two columns stack, the rail first.

**Rationale:** The owner works on a monitor turned upright (about 1080px wide). A rail beside everything, as first proposed, left the items too narrow for the shop's long product names, so the items get the full width and only what is read, not worked on, goes to the side. The three cards in a row of the earlier layout were cramped at that width.

**Consequences:** The header is unchanged: the canvas's proposal also moved the status facts beside the steps and the any-status picker into the menu, which the owner did not ask for, so it was not built. `.order-details-top` is gone for `.order-columns` / `.order-main` / `.order-rail` (`OrderPage.css`).

**Verified:** frontend tests (611) and `tsc`. Not seen in a browser: the page needs the owner's login.


## 2026-09-29 — Status chips

**Decision (owner, from the order list canvas https://claude.ai/artifact/JmMk1VptHZkoaDXtgYpumF):** An order's status and its channel are tinted chips, dark text on a light shade of the same hue, everywhere a `.badge-*` class is used (the list's status picker, the status history, the buyer's other orders, the order header's channel): New `tone-blue`, In progress a new `tone-violet` (`--tone-violet-bg/-fg` in `index.css`, light and dark), Ready to ship `tone-teal`, Shipped `tone-amber`, Delivered `tone-green`, Cancelled `tone-red`, Allegro and Erli their `channel-*-bg/-fg`. The list's channel letter is the same idea: the channel's tint, bordered in its own colour.

**Rationale:** White on the solid fills read at 2.2 to 4.2:1 (Shipped and Delivered below even 3:1), flagged when the design system was built. The tinted pairs are 5.3:1 or better in both modes, and each status keeps its hue.

**Consequences:** `.badge` now takes `--badge-bg` / `--badge-fg` from its modifier (with a border mixed from the two); a `.badge` with no modifier keeps white text on whatever it sits on. The status picker's arrow is dark grey (light grey in dark mode) instead of white. The design system in Claude Design still shows the old fills until it is re-synced from the code.


## 2026-09-29 — The order list

**Decision (owner, from the same canvas, made denser on the owner's word):** Above the list, the four work queues (To make, Unpaid, To ship, Past deadline) are tiles with their counts. Under them one card holds everything else: the statuses as tabs (All, New, In progress, Ready to ship, Shipped, Delivered) with Starred, Flagged and Deleted at the right of the same row, then the search and filters with the sort beside them, then the table. The Buyer column is gone: under the order number, which never wraps, one quiet line says who bought it and when, by their marketplace nick ("ania_k · 28/09, 16:39"; the owner's choice the same evening, since the shop knows buyers by it on Allegro), the name in its tooltip, the name or the e-mail when there is no nick, and the channel letter sits beside the number. Under the amount, paid or not paid yet where that is known (in green or red, how it is paid in the tooltip), else the payment method as before; the paid/unpaid icon in the status cell is gone as a repeat.

**Rationale:** The owner works on a monitor turned upright; twelve pills in one row wrapped into a block, and the separate buyer column took width the items needed. The queues are what a working day starts from, so they come first; statuses are a filter, so they sit on the list.

**Consequences:** The nav "Work queues" now holds only the four queues, and a nav "Status" the status tabs (tests follow). Starred, Flagged and Deleted stay buttons, not a menu, so they remain one click away.

**Verified:** frontend tests (610) and `tsc`. Not seen in a browser: the list needs the owner's login.


## 2026-09-29 — Fixed: updates that brought a newer version were shown as failed

**Found by the owner:** the last two updates from Settings ended in an error, and the history showed them as failed ("The new version did not start within 20 minutes"). Both had in fact worked: asked for `d643499` and `6c97784`, the NAS came up on `78bd456` and `d6bde40`. The updater pulls the newest published images, not the commit the button named, and a newer one had been published between the last check and the press. The progress dialog waited for `/health` to name exactly the commit asked for, which never came, and the history's open row was closed as failed while the new backend wrote its version down as reached "outside Settings".

**Decision:** An update has arrived when the backend runs any version other than the one it started from, in the dialog (`useUpdateRun`, which now keeps the starting commit) and in the history (`update_history._arrived`); the history row then records the version that actually came up. Pulling the newest images stays: installing something older than what is published would only mean a second update.

**Consequences:** The two rows of 2026-09-29 18:06 and 20:29 in `app_updates` stay as they were written (failed, each followed by an "outside Settings" row for the version that came up); the fix applies from the next update on.

**Verified:** backend tests for both ways the arrival is seen, a frontend test for the dialog, the NAS's `/health` answering `d6bde40` while the history said failed.


## 2026-09-29 — The dashboard

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/RtHYhEL8emq1dtChTBwLaG):** What needs a reaction (an order cancelled on the marketplace, a problem in the app's status, returns waiting, unread messages) comes first, as one coloured bar each, the whole bar a link; with nothing waiting there is no bar and no card. Then the four work queues as tiles, the same four and in the same order as over the order list (To make, Unpaid, To ship, Past deadline), no longer "In progress", a status, in the first place. Then the nearest dispatch deadlines across the page as a dense table (when, in amber for today and tomorrow and red when late; the channel letter and number; the buyer's nick; the first item; Smart or the carrier; the status chip), six instead of five. Then the recent orders, in the same compact form, beside a 260px column with the week's figures and the channels.

**Rationale:** The owner works on a monitor turned upright; in the old layout what needed attention sat low in a side column, and the dashboard's first tile counted something the order list did not, so the same day showed different numbers in two places.

**Consequences:** The dashboard's styles are all under `.dashboard` now: its old unscoped `.queue-tile` rules reached the order list's tiles, which share the class name, once the dashboard had been opened. The channel letter (`.source-mark`) is shared by the list and the dashboard. `dashboard.attentionEmpty` is gone with the empty card.

**Verified:** frontend tests (611) and `tsc`. Not seen in a browser: it needs the owner's login.


## 2026-09-30 — The inbox

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/EwL3qz5B69H3PQK7hZ76rR):** With a conversation open, the list narrows to 18rem (from 24) and the conversation gets the rest. "To handle" and "Put aside" are underlined tabs instead of pills; a row is two short lines, the nick with the channel's letter (as on the order list) and how long the buyer has waited, then the last message cut to one line. Above an open conversation, "The buyer's orders": the open ones (new, in progress, ready to ship), each one line (number, status chip, first item, date, amount) linking to the order, the rest folded behind "+ N earlier". Nicks stay as Allegro gives them: a buyer Allegro shows only as "Client:12345678" keeps that name (the owner's choice).

**How the orders are found:** Allegro keeps one conversation per buyer, not per order, and its thread carries no order (none of the 602 threads in the database has `order_external_id`). So the buyer is matched by nick: the order list's own search (which covers `customer_login`) is asked for the nick, and only the orders whose login is exactly that nick are kept. A "Client:…" buyer has no nick to match, so the strip is not shown for them (about a third of the threads, mostly buyers asking before they buy), nor when nothing is found or the list cannot be read. No backend change.

**Not done:** marking which order a single message is about. Allegro may attach an order to a message, but the import does not read such a field; worth checking in its API before building.

**Verified:** frontend tests (615, four new for the strip) and `tsc`. Not seen in a browser: it needs the owner's login.


## 2026-09-30 — The to-make list

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/CSkXq3juSgom9XZKQrF7jV):** The status filters (as underlined tabs, like the order list's), "Hide made", the search and how much is made share one card at the top; how much is made is one line (pieces, products, orders) over a bar instead of three tiles. In each deadline group a product's row starts with the tick and then the quantity in large type ("×6"), before the picture, name and SKU; the orders stay small chips at the end. A made product shows its quantity on green as well as its name struck through. The groups by deadline, their tones and everything a row does are unchanged.

**Rationale:** At the bench the first thing looked for is how many to make; in the old row it came after the product's name, in smaller type. The monitor is upright, so the figures and the filters take one card instead of two rows.

**Consequences:** The table's columns are tick, quantity, product, orders (the tests address the quantity as the second cell). The "×" is drawn by CSS, so the cell's text stays the number. Printing is unchanged: the filters are left off the paper, the figures and groups print.

**Verified:** frontend tests (615) and `tsc`. Not seen in a browser: it needs the owner's login.


## 2026-09-30 — The labels page

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/3nh6EAifHeSk5n5WRtMSx9):** The two ways to ship and the three views (to print, no courier ordered, all bought) are underlined tabs; the view is no longer a drop-down. Printing and ordering a courier sit in a bar that shows only while something is ticked ("Selected: N", order a courier, print, clear); the test label is a small link by the title. The labels are grouped by carrier, in the list's own order, each group with its count and a button to tick or untick all of it. A row is the order number, the carrier's badge with the buyer and the waybill, whether it is printed as a chip (amber waiting, green printed; when it was bought is the chip's tooltip) and the courier's state as a chip.

**Rationale:** A courier is ordered per carrier, so the group is what gets ticked; the buttons with "0" in them said nothing while nothing was ticked. Dense rows fit the upright monitor.

**Consequences:** The view tabs carry no counts (that would need every view's labels, not only the one shown). With nothing ticked there is no print button at all, rather than a disabled one. The limit of 50 labels at once is unchanged and still reported above the list.

**Verified:** frontend tests (616) and `tsc`. Not seen in a browser: it needs the owner's login.


## 2026-09-30 — Returns and claims

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/PaHeT5BkF7g4EVxjjB1tLS):** The summary is three tiles (waiting for you, overdue in red, due within three days in amber) instead of chips. The views are underlined tabs and the kind is a row of pills (all, returns, claims, disputes) in one card with the cases. A case is one dense row in four columns: the deadline as a chip with the date under it, the kind as a tinted chip with its reference, what to do in bold over the order, nick and reason (then the buyer's text on one line, and the detail), and the status as a chip (teal when it came to an end, red when refused). "Read from Allegro" sits by the title.

**Rationale:** Seven columns did not fit the upright monitor; what to do is the first thing looked for, so it leads the widest column.

**Consequences:** The canvas also showed a fourth tile (open cases) and when Allegro was last read; neither is built, as the summary has no open count and the last read is not stored. The order page's card and `CaseDeadline` are shared and now show the deadline as a chip too.

**Verified:** frontend tests (616) and `tsc`. Not seen in a browser: it needs the owner's login.


## 2026-09-30 — The finance page

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/1kMgPfN17SZ6iFp11VcMax):** The Summary and Products tabs are underlined tabs, and the period is a segmented control at the end of the same line instead of pills in the header. The four figures stay in one row down to phone width (two by two only below 768px), lower than before; the fees figure, the one that opens the orders table, is tinted amber, and what is left stays green. What the fees went on is full width; by channel, delivery and the check against the marketplace follow as narrow cards side by side, the check with a "settled" chip in its head when every marketplace's fees are all taken.

**Rationale:** Below 1100px the page used to fall into one column: the figures two by two and three wide cards of short label and value lines, one under another. On the upright monitor the narrow cards fit side by side.

**Consequences:** Nothing the page computes changed; the Products tab is as it was. The side cards wrap onto more lines when the window is too narrow for three (at least 15rem each).

**Verified:** frontend tests (616) and `tsc`. Not seen in a browser: it needs the owner's login.


## 2026-09-30 — Every colour in the stylesheets is a variable

**Decision (owner):** Anvero may get a second look ("Papier": warm cream, a brick accent, serif titles) that a user picks in Settings next to light and dark, sketched on the Claude Design canvas https://claude.ai/artifact/1tJfJmnRK6JXpe4dJzNSRy. A look changes colours, type, radii and spacing only; the layout of every page stays one and the same for both, so a page is never built twice. As the first step, every colour the stylesheets still wrote as a literal (136, in 16 files) became a variable in `index.css`, and the `:root.dark` rules that only swapped a colour were folded into the dark value of that variable.

**Rationale:** A second look can then be one more set of variable values, as dark mode already is, instead of a second set of rules in every stylesheet.

**Consequences:** New variables: text on a fill (`--color-on-accent`, `--color-on-strong`), the menu (`--color-nav-*`), notices (`--notice-danger|warning|info|note|safe|update-*`), tracking states (`--shipping-*`) and a few single ones (`--color-accent-deep`, `--color-accent-hover`, `--color-danger-*`, `--color-warning-text`, `--color-success-text`, `--color-attention-text`, `--color-info-text`, `--color-fee`, `--color-badge-warning`, `--color-status-off`, `--channel-inpost-on`). Each is the value it replaced in each mode, so where a rule kept one value in both modes its variable does too (for example `--color-danger-text` is `#b91c1c` in dark mode as well); whether those should change in dark mode is a separate question. One deliberate change: text on a solid accent fill is now `--color-on-accent` everywhere, so seven places that had white text on the dark-mode accent (`#14b8a6`, too little contrast) now have the dark text the other accent buttons already had: the print and courier buttons on the labels page, the shipping buttons, the chosen queue tab and its count, and two in the export dialog; the import button's dark text moves from `#1a1a1a` to the same `#0b0b0b`. Brand colours drawn by components (the carriers' badges, the Smart badge, the logo) stay literals: they belong to those companies and do not change with the look.

**Verified:** frontend tests (616), `tsc` and the build. A script resolved every colour declaration before and after in both modes and found no difference besides the ones above; in a browser the menu, banners, submit button and badges were measured in both modes on the login page (the other pages need the owner's login).


## 2026-09-30 — A second look, chosen in Settings

**Decision (owner, from the Claude Design canvas https://claude.ai/artifact/1tJfJmnRK6JXpe4dJzNSRy):** Settings, "Appearance and language", has a Style row (Classic or Papier) above the light/dark row, which is now called Mode. Papier is warm cream, a brick accent, serif titles (Fraunces) over Instrument Sans, larger radii and a larger, lighter page title. The choice is kept in this browser (`theme-look`, beside `theme-mode`) and is a class on the root (`look-papier`) whose values `index.css` sets for light and for dark. The layout of every page is the same in both looks.

**Rationale:** The owner wanted both looks, not one replacing the other, and asked for it now, ahead of the visual pass that `ROADMAP.md` item 5 and the 2026-09-17 entry leave for later; that pass (a component library, new layouts) stays open. Only values differ, so a page is built and tested once; every colour being a variable (the entry above) is what made that one block of values.

**Consequences:** The two faces come from `@fontsource` packages, bundled with the app so no page asks Google for them (no buyer's or operator's IP address goes to Google, and it works offline on the NAS); a browser fetches them only while Papier is on. New variables for what a look changes besides colour: `--font-body`, `--font-heading`, `--page-title-size`, `--page-title-weight`, `--card-title-weight`, `--radius-card`. What Papier does not set (notices, tracking states, channels, the red and amber texts) stays classic. Titles that set their own size (the login card, the order page) now take the title variables; in Classic they have the same values as before.

**Verified:** frontend tests (621, five new), `tsc` and the build. In a browser, on the login page: Papier light and dark resolve to the canvas values, the faces load, the title is Fraunces. Not seen: the pages behind the login in Papier.

## 2026-09-30 — Security audit

**Decision (owner):** A read-only review of the whole application (authorization on every endpoint, login, secrets, injection, the web server, the updater and the image pipeline, dependencies, Git history), and every finding fixed:

- **The image pipeline.** `publish.yml` ran after Checks with `branches: [main]`, which matches a branch's name alone, and Checks also runs for pull requests from forks; the repository is public. A fork's branch named `main` that passed the tests would have been built and pushed as `:latest`, which the updater installs with the Docker socket, as good as root on the NAS. It now publishes only a run started by a push to this repository (`event == 'push'`, `head_repository` is this one).
- **The login rate limit.** The backend trusts `X-Forwarded-For` from anyone (`--forwarded-allow-ips='*'`, fine behind the one proxy that alone can reach it), and uvicorn takes that header's first address; nginx appended to what the client sent, so a client could name a new address on every attempt and guess passwords without limit. nginx now sets the header to the connecting address.
- **Revocation.** `users.token_version`, carried in the token: a new password logs out the tokens issued before it. This replaces the earlier acceptance of "no revocation" (the roles and permissions entry) for the case that matters most, a leaked password. Logging out stays per browser, so logging out on one machine does not log out the others. `API.md` also said a deactivated account's token kept working; every request reads the account, so it never did.
- **Dependencies.** `pyjwt` 2.13.0 to 2.14.0 and `httpx2`/`httpcore2` 2.9.1 to 2.12.0 (16 advisories, none reachable as used: HS256 only, no JWK, no SOCKS, SSE or websockets). A malformed token claim is now a `401` rather than a `500`.
- **Headers.** nginx sends `X-Content-Type-Options`, `X-Frame-Options` and `frame-ancestors`, and `Referrer-Policy: no-referrer` on every response.
- **Refreshing a label or a pickup** needs `labels` `manage`, as refreshing an InPost shipment already did: both write what Allegro answers.

**Found in order:** every endpoint but `/health`, `/` and login needs a login, writes need `manage`, users and updates `admin`; passwords are hashed and an unknown email answers in the same time as a wrong password; no raw SQL, no HTML injection in the frontend, the CSV export guarded against formulas; the updater has no published port, compares its token in constant time and runs two fixed commands; integration secrets are encrypted at rest when `SECRETS_KEY` is set; no secret in the Git history (a `backend/test.db` once committed held an empty `users` table); the NAS is reached on the home network and through Tailscale only.

**Consequences:** On the NAS, confirm that `SECRETS_KEY` is set (it is commented out in `deploy/docker-compose.yml`); without it the Allegro and InPost tokens are plain text in the database and its backups. Keep two-factor authentication on the GitHub account and consider protecting `main`: whoever can push to it can, through the image pipeline and the updater, run code on the NAS.

**Verified:** backend tests (six new, on tokens and the refresh permission) and the frontend checks. Not run: the nginx configuration in its container (no Docker on this machine) and the new condition in `publish.yml`, which the next push to `main` exercises.
