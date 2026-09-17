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

This is still a script rather than an HTTP endpoint. It was kept out of the
API while the API had no login, since an open route making outbound calls to
a third party would be easy to abuse; the orders API now requires a login, so
turning the import into an endpoint is a planned next step, not yet done.

### Refresh token rotation

Allegro rotates the refresh token on **every** use: each refresh returns a
new refresh token, valid for three months, and the one just used stops
working about 60 seconds later. The token in `.env` therefore works exactly
once.

The import handles this by storing each rotated token in the database table
`integration_credentials` the moment it is issued, and reading it back on the
next run. `ALLEGRO_REFRESH_TOKEN` only seeds that chain.

After authorizing again, put the new token in `.env` as before. The stored
chain remembers a fingerprint of the token it started from, so a different
token in `.env` is recognised as a fresh authorization and replaces the stale
chain automatically.

**Run imports from one machine only.** The database is per machine, so each
machine keeps its own chain. If two machines start from the same `.env`
token, the first run rotates it and the second machine's copy dies a minute
later. To import from another machine, authorize the application separately
there. Whether Allegro keeps two separate authorizations of one application
valid side by side has not been checked.

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

**Cancellations are the exception that must not go unnoticed.** When an
import finds an order cancelled on Allegro that is still active in Anvero, the
status is left alone but the order is flagged (`marketplace_cancelled_at`):

- the import prints a warning with the number of such orders,
- the dashboard shows a banner linking to them,
- the order list marks the row and can be filtered to just those orders,
- the order page shows a "do not ship" banner.

The flag clears once the operator sets the status to `CANCELLED`. An order that
has already shipped stays flagged, deliberately: it still needs a return or a
refund.

### Field mapping

| Anvero | Allegro |
| --- | --- |
| `external_id` | `id` (checkout form id) |
| `customer_email` | `buyer.email` |
| `total_amount` | `summary.totalToPay.amount` |
| `currency` | `summary.totalToPay.currency` |
| `ordered_at` | earliest `lineItems[].boughtAt`, in UTC |

A checkout form has no single purchase timestamp, so `ordered_at` is the
earliest `boughtAt` among its line items. If none is readable the order is
still imported, dated at import time, and a warning is logged — a wrong date
can be corrected, a dropped order cannot. Unlike the status, `ordered_at` is
refreshed on re-import, as the marketplace owns it.

`total_amount` comes from `summary.totalToPay` because that is the value of
the whole order. `lineItems[].price` is a **unit** price and excludes
delivery, so it cannot serve as a total, and `payment.paidAmount` is what has
been paid so far — zero on an unpaid order, which the domain model rejects.

An order missing a buyer email or a summary, or failing the domain model's
own validation (an email it rejects, a total with more than two decimal
places), cannot be expressed as an Anvero order. Those are skipped and logged
by field name — never by value, since the values include buyer emails — so
one malformed order does not cost the rest of the page.

### Known limits

- **An unused token chain lapses after three months.** Each rotation grants
  three more, so importing at least that often keeps it alive; otherwise
  authorize again. The stored token sits in plain text in the local database
  file, the same exposure as `.env`.
- Only orders are imported. Line items, buyer details, delivery and payment
  are read from the payload but not stored; Anvero has no tables for them.
- One page per run. There is no cursor, so a full backfill means calling the
  script with increasing `--offset`.
- **Nothing here has been exercised against the live API.** The client and
  mapper were built from Allegro's published documentation and are covered by
  tests against recorded payload shapes, not real responses.
