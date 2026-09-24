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

The script notes how the import ended exactly as the button does, so Settings
and the status page show it too.

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
| `fulfillment.status: READY_FOR_SHIPMENT` | `READY_FOR_SHIPMENT` |
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
`marketplace_status_label` — e.g. `READY_FOR_PICKUP` rather than `SHIPPED`,
since the table above sends several Allegro statuses to the same Anvero one.

### Dispatch deadline

`delivery.time.dispatch.to` of the checkout form, the end of the window the
seller must hand the parcel over in, is stored as `dispatch_by` and drives the
work queues' "at risk" order and the "late" queue. Read from Allegro's
documentation only: no sandbox order seen so far has shown whether the field
is filled, so until one does, orders may simply have no deadline.
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

### Shipments and tracking

The checkout form carries no tracking numbers, so an import asks for them
separately, for orders whose status maps to shipped or delivered only (one
call each; an order still being packed has none):

- `GET /order/checkout-forms/{id}/shipments`: `shipments[]` with `id`,
  `waybill`, `carrierId`, `carrierName`, `createdAt`, `lineItems`.
- `GET /order/carriers/{carrierId}/tracking?waybill=..`, up to 20 waybills per
  request, grouped by carrier: `waybills[].trackingDetails.statuses[]` with
  `code` and `occurredAt`. The latest status is kept. Allegro keeps tracking
  history for 60 days.

Tracking is asked for parcels of orders that are shipped and not yet
delivered. Because a carrier moving a parcel does not change the order (so an
import that fetches only changed orders never sees it), every import also
re-reads the tracking of parcels still on their way, newest 200 first, and
stops asking about a parcel once it is `DELIVERED` or `RETURNED`, or older than
60 days. A parcel's tracking status never changes the order's own status: the
marketplace's fulfillment status does that.

All of it is best effort. A request Allegro refuses (the application lacking a
scope; the documentation does not name one for these endpoints) ends the
attempt for the rest of that import and is logged once; a failed request costs
that order its parcels, not the import. Parcels an import could not read are
left as they were. The response shapes come from Allegro's documentation, not
from a real response: a carrier Allegro cannot track just gets no status.

### Fees (billing entries)

After the orders, every import reads the seller's billing entries from
`GET /billing/billing-entries` (newest first, 100 a page, all pages; the
parameters used are `occurredAt.gte`, `limit` and `offset`): each has an `id`,
`occurredAt`, a `type` (`id` such as `SUC` for the sales commission, and
`name`), a signed `value` (`amount`, `currency`), sometimes an `offer` and,
for the types that show one, `order.id`, which is the checkout-form id and so
what ties the entry to an order. They are stored by that id in
`billing_entries` and shown on the order as "Marketplace fees", with their sum
and the order's total less them.

- **Its own sync point**, `last_billing_synced_at`: the first read reaches back
  `ALLEGRO_INITIAL_IMPORT_DAYS`, later ones resume from the point less one
  day. The overlap costs nothing, since an entry already stored is skipped, and
  catches one posted late. The point moves only after every page was read and
  stored, and is reset when an account is connected.
- **Best effort.** A refusal (the application needs the
  `allegro:api:billing:read` scope, and the connection may need to be made
  again to grant it) or any failure is logged and the point stays; the import
  itself is unaffected. Until it works the fees card says nothing is recorded.
- **Not verified:** the shape comes from Allegro's documentation, not a real
  response. It is not known whether the history holds only fees and their
  refunds or also other movements of money, so the card calls the sum "fees,
  net" and it is worth checking against one real order before trusting it.
  Fees that name no order (subscriptions, advertising) are stored but not
  shown anywhere yet. No cost of goods is known, so this is not a margin.

### Known limits

- **An unused token chain lapses after three months.** Each rotation grants
  three more, so importing at least that often keeps it alive; otherwise
  authorize again. The stored token sits in plain text in the local database
  file, the same exposure as `.env`.
- Shipments and tracking are read only for orders Allegro reports as sent or
  delivered, and are untested against the real API (see "Shipments and
  tracking"). Nothing is written back to Allegro.
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
  `scripts/sandbox_order_from_csv.py` builds on it: given the "import and list"
  CSV the offers were listed from, it finds each offer through
  `GET /sale/offers?external.id=` (using the connected Sandbox account) and
  buys each as a separate buyer account. `--dry-run` only shows what it found.
  It refuses to run unless the connection is the Sandbox one, and, like the
  script it reuses, has never been run against the real page.

### Labels through Wysyłam z Allegro

Built 2026-09-24 from Allegro's documentation of the shipment-management API
and tested on fakes: **nothing has been bought for real**. The flow, on the
order ("Label" card), after the sender is entered in Settings, "Shipping":

1. `GET /order/checkout-forms/{id}`: the order's `delivery.method.id`, read
   live (it decides the carrier and the price, and was never imported).
2. `POST /shipment-management/shipments/create-commands` with a `commandId`
   Anvero makes and `input`: `deliveryMethodId`, `sender`, `receiver` (the
   delivery address, the buyer's email and phone, the pickup point as
   `point`), `referenceNumber` (Anvero's `AN-` number), one `PACKAGE` with
   its dimensions and weight, `labelFormat: PDF`. Through `MarketplaceWriter`:
   the seller is charged, so safe mode holds it back like any write.
3. `GET /shipment-management/shipments/create-commands/{commandId}` until
   `SUCCESS` (`shipmentId`) or `ERROR` (`errors[].userMessage`), for about
   eight seconds; after that the label stays pending and "Check again" asks
   once more.
4. `GET /shipment-management/shipments/{shipmentId}` for the carrier and the
   waybill, which is then added to the order as a tracking number would be
   (`POST /order/checkout-forms/{id}/shipments`).
5. `POST /shipment-management/label` with `pageSize: A6` returns the PDF.
   The Labels page sends several `shipmentIds` at once (at most 50, Anvero's
   own cap: the documentation names none) for one PDF of many labels.
6. Cancelling: `POST /shipment-management/shipments/cancel-commands`, then
   its status the same way.

**Courier pickup**, from the Labels page, for parcels of one carrier:
`POST /shipment-management/pickup-proposals` with `shipmentIds` and
`readyDate` returns the slots (read without safe mode: it only asks), then
`POST /shipment-management/pickups/create-commands` with `shipmentIds` and
`pickupDateProposalId` (through safe mode), then
`GET .../pickups/create-commands/{commandId}` until `SUCCESS` (`pickupId`) or
`ERROR`, as for a shipment. The shape of the proposals is read defensively:
groups under `proposals`, each proposal a slot itself (`proposalId` or `id`,
`name` or `date`) or holding slots in `proposalItems` (`id`, `name`). Which
shape Allegro really sends, whether one pickup may mix carriers, and which
delivery methods get proposals at all are unverified. Cancelling a pickup is
not built.

Unverified until tried on the Sandbox with safe mode off: that the application
carries the `allegro:api:shipments:write` (and read) scope; the exact shape
of the shipment's carrier and waybill (both shapes the documentation suggests
are read); whether Allegro already links the shipment to the order by itself,
in which case step 4's tracking number may be refused as a duplicate, harmless
but noted as a failed write; and the label's `Accept` header. Not built yet:
insurance and several parcels per order. Cash on delivery will not be: the
business does not ship it, and such an order is refused a label. Unverified too: that one label
request takes many shipments and how Allegro lays several A6 labels out.

### Writing to Allegro

Built 2026-09-24, from Allegro's documentation, and **never sent**: safe mode
has been on throughout. Two changes go to Allegro, both through
`MarketplaceWriter`, so with safe mode on they are only recorded:

- **The status** an operator sets: `PUT /order/checkout-forms/{id}/fulfillment`
  with `{"status": ...}` (mapping in `API.md`, "Changes that reach the
  marketplace"). `CANCELLED` is not sent.
- **A tracking number** typed in on the order: `POST
  /order/checkout-forms/{id}/shipments` with `carrierId`, `waybill` and, for
  `OTHER`, `carrierName`. Allegro's answer gives the shipment its id.

Both need the application to carry the `allegro:api:orders:write` scope, which
is enabled for the application on Allegro's developer portal; the device-flow
connection asks for no particular scopes, so it grants what the application
has, and the account may need connecting again after the scope is added. A
403 says so in the log. The carrier ids offered are from memory of Allegro's
list (`GET /order/carriers`) and must be checked on the first real send.

A write takes the same lock as an import and waits up to a minute for one to
finish: both refresh the rotating token, and two refreshes at once would
invalidate one of them. Try it on the Sandbox first: switch safe mode off
there, change one order's status and add a tracking number, and check both on
the Sandbox's own order page.

### Buyer messages

Started 2026-09-24: the unified inbox (plan B2), reading Allegro's Message
Center and replying to a thread through safe mode. **Built without reading
Allegro's published OpenAPI specification**: `developer.allegro.pl` was
blocked by this session's network egress and could not be reached, unlike
every other Allegro feature above, which was built by reading the real
documentation. What follows comes instead from Allegro's own Message Center
announcement (`allegro/allegro-api` issue #4727) and search-indexed excerpts
of the tutorial page, cross-checked against a generated API client's docs on
GitHub where one could be found. Confirmed by more than one of those
sources: the endpoint list below, and that a thread is
`{id, read, lastMessageDateTime, interlocutor: {login, ...}}` and that
`POST /messaging/messages` takes `{recipient: {login}, order: {id}, text,
attachments}`. **Not confirmed, and to be checked before trusting this
further:** the exact shape of one entry of `GET
/messaging/threads/{id}/messages` — assumed to be `{id, text, createdAt,
author: {login}}` by analogy with the confirmed shapes — and the scope name
below. Read `app/integrations/allegro/mapper.py`'s own note on this before
changing the mapping.

Endpoints used, all through the same rotating token as orders:

- `GET /messaging/threads`, paged like billing entries (`limit`/`offset`),
  assumed newest activity first — nothing here confirms Allegro's default
  sort, and the sync (below) depends on it to stop early.
- `GET /messaging/threads/{id}/messages`, paged the same way.
- `POST /messaging/threads/{id}/messages` with `{"text": ..., "attachments":
  []}`: a reply in an existing thread. Starting a new thread from Anvero
  (`POST /messaging/messages`, confirmed above but unused) is left for later;
  today every thread starts on the marketplace.

**Reading.** `POST /integrations/allegro/messages/sync` (a button, not yet
scheduled) reads every thread page, newest activity first, and compares each
against what is stored: a thread whose `lastMessageDateTime` and `read` flag
have not moved is skipped, so a sync with nothing new costs one page of
summaries. A page with nothing new stops the sync, on the assumption that
everything later is stale too. A thread's own fields (`interlocutor_login`,
`order_external_id`, `read`) are replaced on each sync, like an order's
details; its messages are only added to, matched by `(thread_id,
external_id)`, since a message once sent is never edited or withdrawn.
Shares the import's lock (`import_lock`): both refresh the same rotating
token.

**Direction.** Allegro's response is not known to carry a message's
direction (buyer or seller) as a field of its own, so it is decided by
comparing the message's `author.login` to the connected seller's own
(`integration_credentials.account_login`, read once when the account was
connected). Without one to compare against, every message reads as incoming.

**Sending.** A reply goes through `MarketplaceWriter`, like a status or a
tracking number: safe mode holds it back by default, and switching it off is
needed to actually send one — try it on the Sandbox first, same as writing
statuses. The message is kept in Anvero either way (`created_in_anvero`),
whatever becomes of sending it, the same choice `add_shipment` makes for a
tracking number. Needs a scope believed to be `allegro:api:messaging` — seen
in an access token in a GitHub search result, not the developer portal's own
scope list — which the application may not carry yet; a 403 says so in the
log, the same as a missing orders scope.

**Not done:** Erli (its public API has no messaging endpoint that could be
found — see "Erli" below), starting a new thread from Anvero, attachments,
marking a thread read back to Allegro (reading it here does not mark it read
there), a schedule (today only the button runs a sync), and disputes.

## Erli

**Built 2026-09-24 from Erli's published API description only**
(`https://erli.pl/svc/shop-api/doc/`, its OpenAPI file `swagger.json`), and
tested against fakes shaped like it. It has never talked to Erli: no key has
been used and no real response seen. Treat every mapping below as a reading of
the documentation until a real import confirms it.

### Setting it up

1. In the Erli seller panel: My ERLI > Sales on ERLI.pl > Store settings >
   Integration method > Own API integration, generate the API key.
2. Put it in `backend/.env` as `ERLI_API_KEY` (not in Git, never in chat or
   a document). `ERLI_API_URL` defaults to production; Erli's documentation
   says its test environment is on another domain without naming it.
3. From `backend/`: `.\.venv\Scripts\python.exe scripts\import_erli.py`
   (`--days N` for a backfill). There is no button or schedule for Erli yet;
   the status page (Status in the sidebar) shows how the script's last run
   ended.

The key is a plain bearer token and does not rotate. Anvero stores only its
SHA-256 fingerprint, on an `ERLI` row of `integration_credentials` that holds
the sync point and the last import's outcome; a different key starts the sync
over, as a re-authorization does for Allegro.

### What an import fetches

`POST /orders/_search`, sorted by `updated`, 200 a page, each page after the
first starting at the previous page's last `cursor` (Erli makes it unique, so
orders changed at the same moment are not skipped). The first import filters
`created >=` the last `ERLI_INITIAL_IMPORT_DAYS` days; later ones start after
the recorded sync point, like Allegro's. Erli's `/inbox` (an event stream of
new and changed orders) was not used: the order search needs no
acknowledgement step and matches how the Allegro import already works.

### Status mapping

Erli's `status` covers buying (`pending`, `purchased`, `cancelled`,
`returned`); handling is in `deliveryTracking.status` (the parcel) and
`sellerStatus` (set by the seller). In order: `cancelled` → `CANCELLED`;
`returned` → `DELIVERED`; then the parcel: `preparing` → `CONFIRMED`,
`readyToSend`/`waitingForCourier` → `READY_FOR_SHIPMENT`, `sent`,
`readyToPickup`, `pickupTimeExpired`, `deliveryUnsuccessful`, `redirected` →
`SHIPPED`, `delivered`/`returned` → `DELIVERED`; then `sellerStatus`:
`created`/`readyToProcess` → `NEW`, `inProgress` → `CONFIRMED`, `sent`,
`readyToPickup`, `returningToSender` → `SHIPPED`, `received`/`returned` →
`DELIVERED`, `canceled` → `CANCELLED`; anything else → `NEW`. The value it was
read from is kept as `marketplace_status_label`. Status follows Erli when it
moves, exactly as for Allegro.

### Field mapping

- Amounts (`totalPrice`, `items[].unitPrice`, `delivery.price`) are integers
  read as **grosze**. Erli's documentation states grosze for its campaign
  costs and never for orders; the first real order must confirm it.
- `user.email` is Erli's proxy address. Erli fills it in shortly after the
  order is created; an order read before that gets the stand-in
  `order-<id>@no-email-yet.erli.pl`, replaced by the next import that sees the
  real one (`DECISIONS.md`).
- Erli names no buyer apart from the delivery address, so the buyer's name,
  company and phone come from it. There is no login.
- Items: `externalId` (the seller's own product id) as the listing, `sku`,
  `name`, `quantity`, `unitPrice` after any rebate.
- Delivery: `delivery.name`, `delivery.price`; the address line is Erli's
  `address` or else street, building and flat; `pickupPlace` becomes the
  pickup point (its `externalId`, e.g. the parcel locker's code).
- Payment: cash on delivery when `delivery.cod`; otherwise online through
  Erli, paid in full when `payment.status` is `COMPLETED` or the order is
  `purchased`, else known unpaid (zero), so it lands in the unpaid queue.
- Invoice: required when `user.invoiceAddress` is present; `nip` is the tax id.
- `comment` is the buyer's message. `deliveryTracking.trackingNumber` and
  `vendor` become a shipment, its `status` the tracking code.
- Erli's order has no dispatch deadline, so Erli orders are never "late".

### Buyer messages

Not built. Erli's published API description (`erli.pl/svc/shop-api/doc/`)
was searched for a messaging or conversation endpoint while building the
unified inbox (plan B2, "Buyer messages" under Allegro above) and none was
found — only order events (`/inbox`) and webhooks (`hooks`). Until Erli
confirms otherwise, the inbox reads Allegro only; an Erli buyer's messages
stay in Erli's own seller panel.
