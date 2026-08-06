# MVP

## Goal

The MVP aims to confirm that Anvero organizes daily order management better than manually switching between marketplaces.

## Scope

1. Local user login.
2. Unified order list with filtering by source, status, and date.
3. Order details view with items, customer, shipping, and payment.
4. Internal order status and change history.
5. Manual addition of sample data and import from first source.
6. Allegro integration adapter prepared so its logic doesn't mix with the rest of the application.

## Out of Scope

- Multi-company and subscription billing,
- Automatic invoice generation,
- Full courier and label handling,
- Inventory synchronization,
- ERLI integration before flow verification on first source,
- Production deployment and Docker.

## Readiness Criterion

The user can review a sample or imported order, find it with a filter, see details, and safely change its internal status.
