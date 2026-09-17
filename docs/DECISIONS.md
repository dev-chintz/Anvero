# Decision Log

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
