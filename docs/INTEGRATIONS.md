# Integrations

## Allegro

### Why a manual authorization step is unavoidable

Reading a seller's orders requires a token issued in a **user context**.
The `client_credentials` flow reaches public data only, so it cannot be used
here. A human has to authorize the application once; the refresh token that
authorization produces is what the import then runs on.

### Connecting from Settings

The Settings page has an Allegro section that replaces steps 3 and 4 below,
with nothing edited by hand: choose the environment (sandbox or production),
enter the application's client id, client secret and User-Agent, save, and
click **Connect account**. It shows a link and a code; open the link **logged
in as the seller** and confirm, and the page notices (it polls on Allegro's
own interval) and shows `Connected as <login>`. The credentials are kept in
`integration_settings` and used instead of the `ALLEGRO_*` variables of the
same meaning; the token in `integration_credentials`, as before. The secret
is written but never returned by the API, and sits in the database as plain
text, the same exposure as the refresh token beside it. The client id and
secret are still those of the owner's own application (step 1): only that
application can be connected, and it must be registered as one without a
browser callback, since Settings uses the same device flow as the script.

Changing the client id or the environment disconnects the account, because a
token belongs to one application in one environment. Connecting always
forgets where the last sync got to, so the next import starts from the
first-import window. Disconnect forgets the token and keeps the credentials.
A token still set in `ALLEGRO_REFRESH_TOKEN` cannot be forgotten this way:
delete it from `.env` too. The sign-in in progress lives in the server's
memory, so restarting the backend mid-sign-in means starting it again.

### One-time setup

1. Register an application at <https://apps.developer.allegro.pl/>
   (sandbox: <https://apps.developer.allegro.pl.allegrosandbox.pl>) as one
   that runs without a browser callback, so it can use the device flow.
   Grant it the `allegro:api:orders:read` scope — without it the API answers
   `403` and the import stops with a message saying so.

2. Generate the application's User-Agent with the portal's User-Agent
   generator: the application, its version (the project's, e.g. `0.1.0`) and
   a documentation URL an outside administrator can open — the repository,
   <https://github.com/dev-chintz/Anvero>, not a `localhost` address. The
   result has the form `Name/Version (+URL)`.

   Allegro requires every API call to carry it and **blocks the application's
   key** over calls that do not. So it is required here too: while
   `ALLEGRO_USER_AGENT` is empty the integration counts as not configured and
   nothing is sent. It is sent verbatim, since Allegro uses it to recognise
   the application; regenerate it rather than editing it by hand.

3. Put the id, the secret and the User-Agent in `backend/.env`, not in a
   chat or a commit:

   ```
   ALLEGRO_CLIENT_ID=...
   ALLEGRO_CLIENT_SECRET=...
   ALLEGRO_USER_AGENT=...
   ```

   For the sandbox, also point both URLs at it. An application exists in
   only one of the two environments, and the other refuses its id:

   ```
   ALLEGRO_API_URL=https://api.allegro.pl.allegrosandbox.pl
   ALLEGRO_AUTH_URL=https://allegro.pl.allegrosandbox.pl/auth/oauth
   ```

4. Obtain the refresh token, from `backend/`:

   ```
   python scripts/authorize_allegro.py
   ```

   It prints a link. Open it **logged in as the seller** whose orders Anvero
   should import — in the sandbox, not the buyer account — and confirm. The
   script polls until then and writes the token to `ALLEGRO_REFRESH_TOKEN` in
   `backend/.env`; it does not print it, so the token stays out of the
   terminal's scrollback. Restart the backend afterwards: settings are read
   when it starts.

   Exit codes: `0` saved, `2` id, secret or User-Agent missing, `3` credentials refused
   or authorization declined, `1` not confirmed in time or other failure,
   `130` stopped with Ctrl+C. Nothing is written unless it succeeds.

   The script runs the device flow (`app/integrations/allegro/authorization.py`):
   `POST {ALLEGRO_AUTH_URL}/device` with Basic auth and `client_id`, then
   `POST {ALLEGRO_AUTH_URL}/token` with
   `grant_type=urn:ietf:params:oauth:grant-type:device_code` and the
   `device_code`, every `interval` seconds, until it answers `200`.

   `.env` is git-ignored. Leaving any of `ALLEGRO_CLIENT_ID`,
   `ALLEGRO_CLIENT_SECRET`, `ALLEGRO_USER_AGENT` and `ALLEGRO_REFRESH_TOKEN`
   empty keeps the integration switched off rather than failing at import
   time.

**Moving from the sandbox to production** means a separate application,
separate credentials, its own User-Agent, and running the script again. The new token replaces
the stored chain on its own (see below), but the orders imported from the
sandbox stay in the database under source `ALLEGRO`, indistinguishable from
real ones. Start production on a clean database, or delete them first.

### Running an import

The Orders page has an "Import from Allegro" button, which calls
`POST /api/v1/integrations/allegro/import`. It is disabled with a
configuration hint when `GET /api/v1/integrations/allegro` reports
`configured: false`, and shows "Importing..." while a request is in flight.
On success it reports how many orders were created and updated as a toast,
and a second warning toast if any were newly found cancelled on the
marketplace. See `API.md` for the request body, response shape and error
codes.

The script still exists and does the same work, through the same wiring
(`app/services/allegro_import.py`), so it and the endpoint cannot drift
apart — that was the risk a second copy of the token-store wiring would have
created; see `DECISIONS.md`, "Rotated Allegro Refresh Tokens Live in the
Database":

```
python scripts/import_allegro.py [--days N]
```

`--days N` ignores the recorded sync point and fetches orders bought in the
last N days (a backfill); the point still moves forward afterwards.

Matching is on `(source, external_id)`, which the database enforces as
unique, so running it twice does not duplicate anything.

Exit codes: `2` not configured, `3` credentials refused, `1` other failure.

**Only one import may run at a time**, from either the script or the
endpoint calling it concurrently against the same database — enforced by a
lock in the endpoint, not by anything the script itself checks. Allegro
rotates the refresh token on every use; two imports running at once would
both try to refresh it, and the one that loses the race is left holding an
already-invalidated token. A second click on the button while one import is
running gets `409` immediately. Running the script by hand while the button
is mid-import is not guarded against — do not do both at once.

### What an import fetches

An import does not read "the latest page"; it asks Allegro for a time window
and pages through all of it, 100 orders at a time:

- **First import** (no sync point recorded yet): orders with a line item
  bought in the last `ALLEGRO_INITIAL_IMPORT_DAYS` days (default 7,
  `lineItems.boughtAt.gte`).
- **Every later import**: orders changed since the recorded point
  (`updatedAt.gte`), which covers new orders and updates to old ones alike.
- The point is the moment the last *complete* import started, less five
  minutes, kept in `integration_credentials.last_synced_at`. It moves only
  after every page was fetched and stored; an import that fails part way
  leaves it, and the next one repeats the same ground (orders match by
  `(source, external_id)`, so nothing is duplicated). Re-authorizing the
  application clears it, since another seller account has another history.
- No sort is requested, so Allegro's default (newest purchase first) applies:
  a purchase time never changes, so paging stays stable while orders are
  updated during the run.
- Stopping after 500 pages (50,000 orders) is an error, not a quiet end, so a
  sync is never recorded as complete when it was not.

### Imports that run by themselves

With `ALLEGRO_IMPORT_INTERVAL_MINUTES` set above 0 the backend runs the same
sync (as the button does) every that many minutes, starting one interval after
it starts. It is off by default, and should be on for **exactly one** backend
per database: the lock that keeps two imports from running at once lives in
one process, and Allegro rotates the refresh token on every use, so two
backends importing on their own would race for it. A run skips quietly when
no account is connected. Every import, by button or schedule, records when it
finished, what it stored or the error, and the orders page shows it and
reloads its list when a new one appears.

### Refresh token rotation

Allegro rotates the refresh token on **every** use: each refresh returns a
new refresh token, valid for three months, and the one just used stops
working about 60 seconds later. The token in `.env` therefore works exactly
once.

The import handles this by storing each rotated token in the database table
`integration_credentials` the moment it is issued, and reading it back on the
next run. `ALLEGRO_REFRESH_TOKEN` only seeds that chain.

After authorizing again (`scripts/authorize_allegro.py` puts the new token
in `.env`), restart the backend. The stored
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

**The Anvero status follows Allegro.** When an import finds that the status
Allegro reports for an order has *moved* since the last import, the Anvero
status moves to it, and the change goes into the status history with no author
(no one made it). What counts as a move is a change in the mapped status
against the one stored as `marketplace_status` at the previous import, not a
difference from the Anvero status: a status the operator set by hand stands
until Allegro itself changes, instead of being reverted every time an import
happens to see the order again. When Allegro does move, it wins over the
operator's status, since Anvero does not write statuses back to Allegro. See
`DECISIONS.md`, 2026-09-21.

Every import also records what the marketplace says in `marketplace_status`,
beside the Anvero one, and Allegro's own value for it, unmapped, in
`marketplace_status_label` — `READY_FOR_SHIPMENT` rather than `CONFIRMED`,
since the table above sends several Allegro statuses to the same Anvero one.
The order page and the order list show the unmapped value whenever the mapped
one differs from the Anvero status, which now means the operator has set
something Allegro has not caught up with.

**Cancellations still get a warning.** An import that takes an active order
to `CANCELLED` because Allegro cancelled it counts it in
`cancellation_warnings` (the import output and the toast after the button).
`marketplace_cancelled_at` records when the cancellation was first noticed; an
order the operator has set back to an active status after that stays flagged
until it is `CANCELLED` again, deliberately: it still needs a return or a
refund.

### Field mapping

| Anvero | Allegro |
| --- | --- |
| `external_id` | `id` (checkout form id) |
| `customer_email` | `buyer.email` |
| `total_amount` | `summary.totalToPay.amount` |
| `currency` | `summary.totalToPay.currency` |
| `ordered_at` | earliest `lineItems[].boughtAt`, in UTC |
| `customer.login`, `first_name`, `last_name`, `company_name`, `phone` | `buyer.login`, `firstName`, `lastName`, `companyName`, `phoneNumber` |
| `buyer_message` | `messageToSeller` |
| `seller_note` | `note.text` — the seller's own note, written on Allegro itself, not the buyer's message |
| `items[].external_id`, `offer_id`, `sku`, `name` | `lineItems[].id`, `offer.id`, `offer.external.id`, `offer.name` |
| `items[].image_url` | the first entry of `images` from `GET /sale/product-offers/{offerId}` — a second call per distinct offer on the page, not part of the checkout form itself; best-effort, so a deleted offer, a missing scope or any other failure leaves it `null` rather than failing the import |
| `items[].quantity`, `unit_price` | `lineItems[].quantity`, `price.amount` |
| `delivery.method`, `cost` | `delivery.method.name`, `delivery.cost.amount` |
| `delivery.address` | `delivery.address` (`zipCode` as `postal_code`, `phoneNumber` as `phone`) |
| `delivery.pickup_point` | `delivery.pickupPoint`: `id`, `name`, `address` |
| `payment.type` | `payment.type`, translated below |
| `payment.provider`, `paid_amount`, `paid_at` | `payment.provider`, `paidAmount.amount`, `finishedAt` |
| `invoice.required` | `invoice.required` |
| `invoice.address` | `invoice.address`, with `company.name`, the first of `company.ids` (or the deprecated `company.taxId`) as `tax_id`, and the `naturalPerson` names |

A checkout form has no single purchase timestamp, so `ordered_at` is the
earliest `boughtAt` among its line items. If none is readable the order is
still imported, dated at import time, and a warning is logged — a wrong date
can be corrected, a dropped order cannot. Unlike the status, `ordered_at` is
refreshed on re-import, as the marketplace owns it.

The detail field names were checked against Allegro's published OpenAPI
specification. `unit_price` is `price`, what the buyer pays per unit;
`originalPrice` is the price before discounts. `buyer.address` (the buyer's
own address, as opposed to where the parcel goes) and
`buyer.personalIdentity` are deliberately not stored: the delivery and invoice
addresses are what the seller needs, and personal data that serves no purpose
should not be kept.

| Allegro `payment.type` | Anvero |
| --- | --- |
| `ONLINE` | `ONLINE` |
| `WIRE_TRANSFER` | `BANK_TRANSFER` |
| `SPLIT_PAYMENT` | `BANK_TRANSFER` (the Polish split payment mechanism) |
| `CASH_ON_DELIVERY` | `CASH_ON_DELIVERY` |
| `EXTENDED_TERM` | `DEFERRED` |
| anything else | `OTHER` |

Details are read leniently, unlike the fields an order cannot exist without.
A detail that cannot be read is left out and the order is still imported: an
optional field that fails validation is dropped and the rest of its part
kept, and a line item missing something it needs (a name, a quantity, a
price) is skipped while the other items are kept. Each case is logged by
order and field name, never by value. On the order page a skipped item shows
as item totals that no longer add up to the order total. A buyer message
longer than 4000 characters is shortened rather than dropped.

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
- Shipments (carrier, tracking number) are not imported; Allegro serves
  them from a different endpoint.
- An import runs only when someone starts it (the button or the script);
  nothing schedules it yet.
- An order bought more than the first window ago, and changed since, arrives as
  a new order the first time it is seen, because `updatedAt` cannot tell "new
  to Anvero" from "new to Allegro".
- An order that cannot be mapped is skipped with a warning and is not retried
  unless Allegro changes it again.
- **Only the sandbox has been exercised.** On 2026-09-17 the authorization,
  the token refresh with rotation, the orders endpoint and the mapping all
  ran against the real sandbox API, from the script and from the button, on
  one order: paid online, one line item, a pickup point and an invoice. A
  cancelled order, several line items and more than one page have still
  never been seen, and production has its own application and credentials.
  `scripts/sandbox_bulk_purchase.py` exists to generate more sandbox orders
  for exactly this (buying one listed offer repeatedly, since Sandbox has no
  bulk-purchase API); untested against the real page as of 2026-09-18, see
  its own docstring before running it.
