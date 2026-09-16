# Integrations

## Allegro

### Why a manual authorization step is unavoidable

Reading a seller's orders requires a token issued in a **user context**.
The `client_credentials` flow reaches public data only, so it cannot be used
here. A human has to authorize the application once; the refresh token that
authorization produces is what the import then runs on.

### One-time setup

1. Register an application at <https://apps.developer.allegro.pl/>.
   Grant it the `allegro:api:orders:read` scope — without it the API answers
   `403` and the import stops with a message saying so.

2. Obtain a refresh token. Either flow works:

   **Device flow** — no redirect URI needed, so it suits a machine that has
   no browser callback:

   - `POST https://allegro.pl/auth/oauth/device`, Basic auth with
     `client_id:client_secret`, form parameter `client_id={client_id}`.
   - Open the returned `verification_uri_complete` and confirm.
   - `POST https://allegro.pl/auth/oauth/token` with
     `grant_type=urn:ietf:params:oauth:grant-type:device_code` and
     `device_code={device_code}`. Poll until it answers `200`.

   **Authorization code flow** — for an application registered with browser
   access:

   - Send the user to
     `https://allegro.pl/auth/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}`.
   - Exchange the returned `code` at
     `POST https://allegro.pl/auth/oauth/token` with
     `grant_type=authorization_code`, `code` and `redirect_uri`, Basic auth.

3. Put the results in `backend/.env`:

   ```
   ALLEGRO_CLIENT_ID=...
   ALLEGRO_CLIENT_SECRET=...
   ALLEGRO_REFRESH_TOKEN=...
   ```

   `.env` is git-ignored. Leaving any of the three empty keeps the
   integration switched off rather than failing at import time.

### Running an import

```
python scripts/import_allegro.py [--limit N] [--offset N]
```

Matching is on `(source, external_id)`, which the database enforces as
unique, so running it twice does not duplicate anything.

Exit codes: `2` not configured, `3` credentials refused, `1` other failure.

This is a script rather than an HTTP endpoint because the orders endpoints
carry no authentication yet; an unauthenticated route making outbound calls
to a third party would be an obvious thing to abuse. It becomes an endpoint
when auth is wired in.

### Status mapping

Allegro tracks two axes and Anvero has one, so the status is derived from
both. A cancelled order is cancelled whatever its parcel is doing, so that
is checked first.

| Allegro | Anvero |
| --- | --- |
| `status: CANCELLED` | `CANCELLED` |
| `fulfillment.status: NEW` | `NEW` |
| `fulfillment.status: PROCESSING` | `CONFIRMED` |
| `fulfillment.status: READY_FOR_SHIPMENT` | `CONFIRMED` |
| `fulfillment.status: SENT` | `SHIPPED` |
| `fulfillment.status: READY_FOR_PICKUP` | `SHIPPED` |
| `fulfillment.status: PICKED_UP` | `DELIVERED` |

`fulfillment` is absent until handling starts; then `status` is used —
`BOUGHT` and `FILLED_IN` map to `NEW`, `READY_FOR_PROCESSING` to
`CONFIRMED`. An unrecognised value maps to `NEW`, so an order Allegro
introduces a new status for surfaces as work to do rather than disappearing.

The marketplace status is only applied when an order is **first seen**. After
that the Anvero status belongs to the operator: it is set by hand and
recorded in the status history, and a sync overwriting it would silently undo
that. See `DECISIONS.md`.

### Field mapping

| Anvero | Allegro |
| --- | --- |
| `external_id` | `id` (checkout form id) |
| `customer_email` | `buyer.email` |
| `total_amount` | `summary.totalToPay.amount` |
| `currency` | `summary.totalToPay.currency` |

`total_amount` comes from `summary.totalToPay` because that is the value of
the whole order. `lineItems[].price` is a **unit** price and excludes
delivery, so it cannot serve as a total, and `payment.paidAmount` is what has
been paid so far — zero on an unpaid order, which the domain model rejects.

An order missing a buyer email or a summary cannot be expressed as an Anvero
order. Those are skipped and logged, so one malformed order does not cost the
rest of the page.

### Known limits

- **The refresh token expires after about 3 months.** Allegro issues a new
  one on each refresh, but the client reads it from the environment and has
  nowhere to write a rotated value back to — persisting it needs the
  `integration` table that `DATABASE.md` describes and that does not exist
  yet. Until then the token has to be renewed by hand, and the import will
  fail with "the application needs authorizing again" when it lapses.
- Only orders are imported. Line items, buyer details, delivery and payment
  are read from the payload but not stored; Anvero has no tables for them.
- One page per run. There is no cursor, so a full backfill means calling the
  script with increasing `--offset`.
- **Nothing here has been exercised against the live API.** The client and
  mapper were built from Allegro's published documentation and are covered by
  tests against recorded payload shapes, not real responses.
