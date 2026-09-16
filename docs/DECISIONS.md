# Decision Log

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
