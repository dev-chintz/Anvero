# Decision Log

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
