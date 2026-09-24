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

## 2026-09-24 — Buyer messages: a unified inbox over Allegro's Message Center, built without its OpenAPI spec

**Decision:** Started plan B2, one inbox across marketplaces (`message_threads`, `messages`). Allegro's threads are read into it (`POST /integrations/allegro/messages/sync`, its own button, sharing the import's lock and token), a thread can be put aside, and a reply goes out through `MarketplaceWriter` like a status or a tracking number. `developer.allegro.pl` was blocked by this session's network egress, unlike every other Allegro feature so far, which was built by reading its real documentation; this one is instead built from Allegro's Message Center announcement and search-indexed excerpts, flagged in `INTEGRATIONS.md`, "Buyer messages", down to which fields are confirmed by more than one source and which are guessed by analogy. A message's direction (buyer or seller) is decided by comparing its author's login to the connected seller's own, since no field of its own is confirmed to carry it. Erli is not read: its published API has no messaging endpoint that could be found.

**Rationale:** Building on an unread specification, rather than waiting for network access or refusing the feature, follows the same practice already used for shipments, tracking and billing entries here — real fields where more than one source agrees, the rest flagged and left for the first real response to confirm, tested against fakes shaped like the assumption. A thread compares its own `lastMessageDateTime` and read flag against what is stored to decide whether its messages need reading again, so a sync with nothing new costs one page of summaries; assumed, not confirmed, to sort newest activity first, which the early stop depends on. The reply going through `MarketplaceWriter` keeps the one rule already in place: nothing reaches a real buyer until safe mode is switched off, and the message is kept in Anvero (`created_in_anvero`) whatever becomes of sending it, so the operator's own record does not depend on it.

**Consequences:** Nothing has been sent to a real buyer yet - safe mode has been on throughout, as it was for the first status and tracking-number writes. The messaging scope's real name, the shape of one message, and whether threads truly sort newest-first are all unconfirmed until a real response or the published spec is read; the mapper and this file say so. Starting a new thread from Anvero, attachments, marking a thread read back to Allegro, and a schedule are left for later. Erli buyer messages stay outside Anvero until its API is checked again.
