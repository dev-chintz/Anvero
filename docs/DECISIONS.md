# Decision Log

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

## 2026-09-16 — Import Runs as a Script, Not an Endpoint

**Decision:** Allegro import is `scripts/import_allegro.py`, not
`POST /integrations/allegro/import`.

**Rationale:** The orders endpoints carry no authentication. An
unauthenticated route that makes outbound calls to a third party is an
obvious thing to abuse, and rate limiting is not the right answer to it. This
becomes an endpoint once auth is wired into the orders API.

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
