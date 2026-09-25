# API Contract

API is versioned under the `/api/v1` prefix. Communication format: JSON; dates: ISO 8601 in UTC.

Every timestamp in a response carries its zone, as `...Z`. A timestamp sent
without a zone is taken as UTC. Calendar dates used as filters (`YYYY-MM-DD`)
are days in the business timezone, `BUSINESS_TIMEZONE`, default
`Europe/Warsaw` — not UTC days.

## Implemented

| Method | Path | Meaning |
| --- | --- | --- |
| `GET` | `/api/v1/health` | service status |
| `GET` | `/api/v1/orders` | order list with filters |
| `GET` | `/api/v1/orders/stats` | aggregate figures for the dashboard |
| `GET` | `/api/v1/orders/production` | the to-make queue by product: what to make and how many, and which are made |
| `PUT` | `/api/v1/orders/production/checks` | tick a product on that list off as made, or take the tick away |
| `GET` | `/api/v1/orders/{id}` | one order with its details: items, buyer, delivery, payment, invoice |
| `DELETE` | `/api/v1/orders/{id}` | take the order out of every list; it is kept, and an import leaves it alone |
| `POST` | `/api/v1/orders/{id}/restore` | put a deleted order back |
| `PATCH` | `/api/v1/orders/{id}/status` | status change, also sent to Allegro (safe mode permitting) |
| `POST` | `/api/v1/orders/{id}/shipments` | add a tracking number, also sent to Allegro (safe mode permitting) |
| `GET` | `/api/v1/orders/{id}/history` | status change history |
| `GET` | `/api/v1/orders/{id}/buyer-orders` | the same buyer's other orders, newest first, at most 20 |
| `POST` | `/api/v1/orders` | create an order — local testing until marketplace ingestion exists |
| `POST` | `/api/v1/auth/login` | obtain a JWT; rate limited to 5 attempts per minute per IP |
| `GET` | `/api/v1/users/me` | current user |
| `GET` | `/api/v1/settings/safe-mode` | whether safe mode is on, and who last switched it |
| `PUT` | `/api/v1/settings/safe-mode` | switch safe mode on or off |
| `GET` | `/api/v1/marketplace-writes` | what Anvero sent to a marketplace, or held back in safe mode |
| `GET` | `/api/v1/status` | the application status page: connections, last imports, the schedule |
| `GET` | `/api/v1/settings/shipping` | the sender and the usual parcel, for labels |
| `PUT` | `/api/v1/settings/shipping` | store them |
| `GET` | `/api/v1/orders/{id}/labels` | the order's labels bought through Wysyłam z Allegro, newest first |
| `POST` | `/api/v1/orders/{id}/labels` | buy the order's shipment (safe mode permitting) |
| `POST` | `/api/v1/orders/{id}/labels/{label_id}/refresh` | ask Allegro again about a label still being created |
| `POST` | `/api/v1/orders/{id}/labels/{label_id}/cancel` | cancel a bought shipment (safe mode permitting) |
| `GET` | `/api/v1/orders/{id}/labels/{label_id}/pdf` | the label, A6, as a PDF |
| `GET` | `/api/v1/labels` | bought labels across every order, for printing many at once |
| `POST` | `/api/v1/labels/pdf` | several labels as one A6 PDF |
| `GET` | `/api/v1/labels/test-pdf` | a sample A6 label drawn by Anvero, to check that a label shows and prints |
| `POST` | `/api/v1/pickups/proposals` | when a courier could come for chosen parcels on a day |
| `POST` | `/api/v1/pickups` | order the courier for a proposed slot (safe mode permitting) |
| `POST` | `/api/v1/pickups/{id}/refresh` | ask Allegro again about a pickup still being confirmed |
| `GET` | `/api/v1/integrations/allegro` | the Allegro connection's state, never a secret |
| `PUT` | `/api/v1/integrations/allegro/settings` | store the Allegro application's credentials |
| `POST` | `/api/v1/integrations/allegro/connect` | start connecting a seller account; rate limited to 10 per minute per IP |
| `GET` | `/api/v1/integrations/allegro/connect/{flow_id}` | has the seller confirmed yet; rate limited to 60 per minute per IP |
| `DELETE` | `/api/v1/integrations/allegro/connection` | forget the connected account |
| `POST` | `/api/v1/integrations/allegro/import` | run an Allegro import; rate limited to 6 attempts per minute per IP |
| `GET` | `/api/v1/integrations/erli` | the Erli key's state (source, last characters, last import), never the key |
| `PUT` | `/api/v1/integrations/erli/settings` | save the Erli API key once Erli has accepted it; rate limited to 10 per minute per IP |
| `DELETE` | `/api/v1/integrations/erli/settings` | forget the key entered in Integrations; the one in `backend/.env`, if any, applies again |
| `POST` | `/api/v1/integrations/erli/import` | run an Erli import; rate limited to 6 per minute per IP |
| `GET` | `/api/v1/integrations/schedule` | how often the backend imports and reads messages by itself, for every channel |
| `PUT` | `/api/v1/integrations/schedule` | set that interval: `{"interval_minutes": 15}`; 0 is off, otherwise 5 to 1440 |
| `GET` | `/api/v1/integrations/inpost` | the InPost connection's state (environment, organization, last characters of the token, default size), never the token |
| `PUT` | `/api/v1/integrations/inpost/settings` | save token, organization and environment once InPost has accepted them; rate limited to 10 per minute per IP |
| `PUT` | `/api/v1/integrations/inpost/template` | change only the default parcel size |
| `DELETE` | `/api/v1/integrations/inpost/settings` | forget the token and the organization |
| `GET` | `/api/v1/orders/{id}/inpost-shipments` | the order's InPost shipments, newest first |
| `POST` | `/api/v1/orders/{id}/inpost-shipments` | make the order's parcel-locker shipment at InPost |
| `POST` | `/api/v1/orders/{id}/inpost-shipments/{shipment_id}/refresh` | ask InPost again about a shipment (its status, and its number once it has one) |
| `POST` | `/api/v1/orders/{id}/inpost-shipments/{shipment_id}/cancel` | cancel the shipment at InPost |
| `GET` | `/api/v1/inpost/orders` | orders a locker parcel could be made for now |
| `POST` | `/api/v1/inpost/shipments` | make parcels for several orders at once (at most 50) |
| `GET` | `/api/v1/inpost/labels` | shipments with a number, oldest first; `printed=false` (default), `true` or absent for all |
| `POST` | `/api/v1/inpost/labels/pdf` | the labels of the given shipments as one A6 PDF; notes them printed |
| `GET` | `/api/v1/after-sales` | returns, claims and disputes: by default what waits for the seller, closest deadline first |
| `GET` | `/api/v1/after-sales/summary` | how many wait, how many are late, how many are due within three days |
| `GET` | `/api/v1/orders/{id}/after-sales` | the cases on one order, open or not, newest first |
| `POST` | `/api/v1/integrations/allegro/after-sales/sync` | read returns, claims and disputes from Allegro; rate limited to 6 per minute per IP |
| `POST` | `/api/v1/integrations/allegro/messages/sync` | read new and changed Message Center threads; rate limited to 6 per minute per IP |
| `GET` | `/api/v1/messages/threads` | the unified inbox: threads across every source, newest activity first |
| `GET` | `/api/v1/messages/threads/{id}` | one thread with its messages |
| `PATCH` | `/api/v1/messages/threads/{id}/aside` | put a thread aside, or bring it back |
| `POST` | `/api/v1/messages/threads/{id}/reply` | reply to a thread, also sent to Allegro (safe mode permitting) |

There is no registration endpoint. Accounts are created on the server with
`scripts/create_user.py`; see `DECISIONS.md`.

## `POST /api/v1/auth/login`

Body: `{"email": "...", "password": "..."}`. Returns
`{"access_token": "...", "token_type": "bearer"}`. Send the token as
`Authorization: Bearer <token>`. It lasts `ACCESS_TOKEN_EXPIRE_MINUTES`,
default 480 (a working day), and cannot be revoked early.

A wrong password, an unknown email and a deactivated account all return the
same `401 {"detail": "Invalid credentials"}`, taking comparable time, so the
response does not reveal which emails have accounts.

## `GET /api/v1/integrations/allegro`

What Integrations shows about the connection:

```json
{"configured": true, "connected": true, "application_complete": true,
 "client_id": "...", "user_agent": "...", "environment": "sandbox",
 "source": "settings", "account_login": "seller_login",
 "last_import_at": "2026-09-21T10:00:00Z", "last_import_created": 3,
 "last_import_updated": 5, "last_import_error": null,
 "auto_import_interval_minutes": 15}
```

The `last_import_*` fields say how the last import ended, whether the button or
the schedule ran it: when, what it stored, or the error if it failed (then
created and updated are null). All are null before the first import and after
the account is connected again. `auto_import_interval_minutes` is how often
the backend imports by itself (the interval from `/integrations/schedule`); 0
means it does not. The Erli status carries the same field.

`GET /integrations/schedule` answers `{"interval_minutes": 15}`: the interval
saved in Integrations, else the environment's default (15). `PUT` saves it (`422`
for anything but 0 or 5 to 1440); the backend's loop reads it every half minute,
so a change needs no restart. It is one interval for Allegro orders, Erli orders
and Allegro messages.

`configured` means ready to import (credentials and a token); `connected` that
a seller account has been connected; `application_complete` that client id,
client secret and User-Agent are all set; `source` is `settings` (entered
there) or `environment` (`backend/.env`). Never returns the client secret, a
token or any part of one. Requires a login, like every endpoint below
`/api/v1` except `/health` and the root.

## `PUT /api/v1/integrations/allegro/settings`

Body: `client_id`, `client_secret` (blank or absent keeps the stored one; `422`
if there is none yet), `user_agent`, `environment` (`sandbox` or
`production`). Returns the same status as above. Changing the client id or the
environment disconnects the account (`connected` comes back `false`), since a
token belongs to one application in one environment. `409` while an import is
running.

## `POST /api/v1/integrations/allegro/connect`

Starts connecting a seller account by the OAuth device flow. Returns
`{"flow_id", "verification_uri", "user_code", "interval", "expires_in"}`: the
seller opens `verification_uri`, logged in, and confirms. `409` if the
application's credentials are not set, `502` if Allegro refused them. Starting
again replaces the sign-in in progress.

## `GET /api/v1/integrations/allegro/connect/{flow_id}`

Returns `{"status": "pending"}` until the seller confirms, then
`{"status": "connected", "account_login": "..."}` and the token is stored.
Asking sooner than `interval` seconds does not reach Allegro. Errors: `404`
unknown or replaced sign-in, `410` expired, `403` declined, `502` Allegro
refused something.

## `DELETE /api/v1/integrations/allegro/connection`

Forgets the connected account and keeps the application's credentials.
Returns the status. `409` while an import is running.

## Returns, claims and disputes: `/api/v1/after-sales`

A case: `{"id", "source", "kind", "status", "is_open", "action", "due_at",
"overdue", "reference_number", "buyer_login", "buyer_email", "opened_at",
"reason", "summary", "detail", "order_external_id", "order_id",
"order_label"}`.

- `kind` is `RETURN`, `CLAIM` (a formal claim, with a deadline) or `DISPUTE`.
- `status` is Allegro's own (`DELIVERED`, `CLAIM_SUBMITTED`, `DISPUTE_ONGOING`...),
  in its own words; `reason` its reason code (`DAMAGED`, `NOT_AS_DESCRIBED`...);
  the interface words both and shows a code it does not know as it is.
- `action` is what the case asks of the seller: `DECIDE` (refund or reject a
  return whose goods are back; accept or reject a submitted claim), `REPLY` (a
  dispute the seller did not write last in), `RECOVER_COMMISSION` (a refunded
  return whose sales commission can still be claimed back) or `NONE`.
- `due_at` is when the action is due, null when there is no deadline (a
  dispute has none). A claim's comes from Allegro. A return's does not, so it is
  worked out: 14 days from the day the return was declared to decide, 45 to claim
  the commission back, early rather than late (`INTEGRATIONS.md`, "Returns and
  claims"). `overdue` is true when `due_at` has passed while `action` is not
  `NONE`.
- `order_id` and `order_label` name the Anvero order the case belongs to, matched
  by `(source, order_external_id)`; both null when the order was not imported.

`GET /after-sales?view=action|open|all&kind=RETURN|CLAIM|DISPUTE&limit&offset`
returns `{"items": [...], "total": n}`. `action` (the default) lists the cases
whose `action` is not `NONE`, closest deadline first and those without one last;
`open` everything still going on; `all` everything read; the last two newest
opened first.

`GET /after-sales/summary` returns `{"needs_action", "overdue", "due_soon"}`:
the cases with an action, of those the ones past their deadline, and the ones
due within the next three days.

`GET /orders/{id}/after-sales` returns the cases of one order as a list; `404`
for an unknown order.

`POST /integrations/allegro/after-sales/sync` reads customer returns (created in
the last `ALLEGRO_AFTER_SALES_DAYS`, default 90, and back to the oldest one still
open here), every open dispute and claim however old, and the closed ones of that
period, and returns `{"returns": n, "claims": n, "disputes": n}`. It takes the
lock the order import takes: `409` while an import or another sync runs, and when
Allegro is not configured; `502` when Allegro refuses (the application may lack
`allegro:api:disputes` for disputes and claims, or `allegro:api:orders:read` for
returns) or cannot be reached.

## Erli: `/api/v1/integrations/erli`

`GET` returns

```json
{"configured": true, "source": "settings", "key_hint": "…a4f2",
 "last_import_at": "2026-09-24T10:00:00Z", "last_import_created": 3,
 "last_import_updated": 1, "last_import_error": null}
```

`source` is `settings` (entered in Integrations), `environment` (`ERLI_API_KEY` in
`backend/.env`) or `none`; a key entered in Integrations takes precedence. Only the
last four characters of the key ever leave the backend. The `last_import_*`
fields are those of the `ERLI` row of `integration_credentials`, filled by the
button and by `scripts/import_erli.py` alike.

`PUT /settings` takes `{"api_key": "..."}` (surrounding whitespace is trimmed)
and asks Erli for one order with that key before saving it. `422` when Erli
refuses the key, `502` when Erli cannot be asked; in both nothing is saved.
Returns the status. `DELETE /settings` returns it too.

`POST /import` runs the same sync as `scripts/import_erli.py` and returns the
same body as the Allegro import (`cancellation_warnings` included). It takes the
lock the Allegro import takes, so the two never overlap: `409` while either
runs, and `409` when no key is set; `502` on any Erli failure.

## InPost: `/api/v1/integrations/inpost`, `/api/v1/inpost` and the order's `inpost-shipments`

Parcel locker shipments made at InPost (ShipX API) from Anvero, and their labels.
Built from InPost's documentation and tested on fakes (`INTEGRATIONS.md`, "InPost").

`GET /integrations/inpost` returns
`{"configured": true, "environment": "sandbox", "organization_id": "777", "token_hint": "…5678", "default_template": "small"}`.
`PUT /integrations/inpost/settings` takes `{"token": "...", "organization_id": "777",
"environment": "sandbox" | "production", "default_template": "small" | "medium" | "large"}`;
the token may be left out to keep the saved one. The organization is asked of InPost
with that token before anything is saved: `422` when InPost refuses the pair, `502`
when it cannot be asked, and nothing is saved in either case. `DELETE` forgets the
token and the organization but keeps environment and size.

`POST /orders/{id}/inpost-shipments` takes `{"template": "small"}` (optional; the
saved default applies) and returns `{"shipment", "marketplace_write", "tracking_write"}`.
The shipment is a `inpost_locker_standard` one to the locker the buyer chose
(`custom_attributes.target_point`), sized by the template (`small`, `medium`, `large`
are InPost's A, B, C), referenced by Anvero's `AN-` number. It goes through safe mode:
held back, `shipment` is null and `marketplace_write.outcome` is `DRY_RUN`. InPost
buys asynchronously, so the call waits about eight seconds for the tracking number;
a shipment still without one is settled by `/refresh`. Once InPost has a number it is
added to the order as a shipment with carrier `INPOST` (which also sends it to Allegro
through the usual safe-mode write: `tracking_write`). `409` when Anvero would not ask
(deleted or cancelled order, cash on delivery, not an InPost locker, an active InPost
shipment or another tracking number on the order, missing name, e-mail or a phone that
is not nine digits) with the reason as `detail`; `502` when InPost refuses, with its
own words and the fields it names.

`POST /orders/{id}/inpost-shipments/{shipment_id}/cancel` cancels at InPost (safe mode
applies; `shipment.error` holds a refusal).

`GET /inpost/orders` lists `{id, order_label, buyer, target_point, pickup_point_name,
delivery_method, status, dispatch_by}` for orders that are open, for an InPost locker
and have no tracking number. `POST /inpost/shipments` takes
`{"order_ids": [...], "template": "small"}` (1 to 50 orders) and returns
`{"items": [{"order_id", "order_label", "outcome", "message", "shipment"}]}` where
`outcome` is `created`, `held_back`, `refused` (Anvero would not ask) or `failed`
(InPost said no): one order's refusal does not stop the others, and the orders share
one wait for InPost's numbers.

`GET /inpost/labels` lists the shipments that have a number, with the order's label
and the buyer. `POST /inpost/labels/pdf` takes `{"shipment_ids": [...]}` (at most 50)
and returns `application/pdf` in that order: one label as InPost's own single label
address, several through the organization's batch address. A shipment is noted
printed only once the PDF is in hand. `404` for an unknown shipment.

## `POST /api/v1/integrations/allegro/import`

Runs an Allegro sync (the same work as `scripts/import_allegro.py`) and
returns its result. There is no request body. The first sync fetches orders
bought in the last `ALLEGRO_INITIAL_IMPORT_DAYS` (default 7); every later one
fetches only orders new or changed since the last one that finished, all pages
of them. A sync that fails part way does not move that point, so the next one
covers the same ground again; orders are matched by `(source, external_id)`, so
that costs nothing but time. See `INTEGRATIONS.md`, "What an import fetches".

Response:

```json
{"created": 3, "updated": 5, "cancellation_warnings": 1}
```

`cancellation_warnings` counts orders newly found cancelled on Allegro while
still active in Anvero; see the "Marketplace Cancellations Warn" entry in
`DECISIONS.md`.

Rate limited to 6 attempts per minute per IP — it makes outbound calls to
Allegro, so allowing unlimited retries would let a client hammer a third
party through this API. Only one import may run at a time, since Allegro
rotates the refresh token on every use and two imports refreshing it at once
would race; a second request while one is in flight gets `409` immediately
rather than queueing. Scheduled imports (`GET /integrations/schedule`) go
through the same lock and leave the same note of how they ended.

Error responses:

| Status | When |
| --- | --- |
| `409` | Allegro is not configured (`ALLEGRO_CLIENT_ID`/`_SECRET`/`_USER_AGENT`/`_REFRESH_TOKEN` missing), or an import is already running |
| `502` | Allegro rejected the credentials, or any other integration failure (unreachable, non-JSON response, etc.) |

Every error detail is a plain description; none of them include a token,
credential or raw Allegro response.

## `POST /api/v1/integrations/allegro/messages/sync`

Reads Allegro's Message Center: threads whose last message or read flag has
moved since the last sync, and their messages. No request body.

```json
{"threads_synced": 2, "messages_added": 3}
```

Rate limited to 6 attempts per minute per IP, and shares the Allegro import's
lock (both refresh the same rotating token), so `409` while an import or
another message sync is running. Same error shapes as `.../import` otherwise.
See `INTEGRATIONS.md`, "Buyer messages", for what a thread and a message
carry and what is unconfirmed about it.

## `GET /api/v1/messages/threads`

The unified inbox, newest activity first. Query parameters: `source`
(`ALLEGRO` or `ERLI`), `aside` (default `false`: threads set aside are
excluded unless this is `true`), `unread_only` (default `false`), `search`
and `limit` (default 200, at most 1000).

`search` (at most 100 characters) keeps the threads whose buyer's login, order id,
last message or any message contains the text, whatever its case. It looks through
every thread, set aside or not, unless `aside` is given: a buyer is looked up by nick
without remembering where the conversation went. `%` and `_` are searched for as
themselves. Only the newest `limit` threads are listed without a search's help, so a
conversation older than that is reached by searching.

```json
[
  {
    "id": "...", "source": "ALLEGRO", "interlocutor_login": "buyer1",
    "order_external_id": "5e2a4f40-...", "last_message_at": "...Z",
    "last_message_text": "Kiedy wyślecie paczkę?", "read": false, "aside": false
  }
]
```

`order_external_id` is the marketplace's own order id, not an Anvero one -
match it against `orders.external_id` for the same `source` to find the
order, if it has been imported.

## `GET /api/v1/messages/threads/{id}`

One thread with its messages, oldest first:

```json
{
  "...": "as above",
  "messages": [
    {
      "id": "...", "direction": "IN", "author_login": "buyer1",
      "text": "Kiedy wyślecie paczkę?", "sent_at": "...Z", "created_in_anvero": false
    }
  ]
}
```

`404` for an id no thread has.

## `PATCH /api/v1/messages/threads/{id}/aside`

Body `{"aside": true}` or `{"aside": false}`; returns the thread. Local to
Anvero only - nothing is sent to the marketplace.

## `POST /api/v1/messages/threads/{id}/reply`

Body `{"text": "..."}`, up to 4000 characters. Writes the reply to Anvero and
sends it to the marketplace unless safe mode holds it back, through the same
door as a status change or a tracking number (see "Changes that reach the
marketplace" below).

```json
{
  "thread": {"...": "as GET .../threads/{id}"},
  "marketplace_write": {"...": "as GET /api/v1/marketplace-writes"}
}
```

The reply is kept in the thread whatever becomes of sending it - `outcome`
says whether it was sent, held back by safe mode, or refused, and `detail`
why. `409` for a source with no messaging endpoint (only `ALLEGRO` has one
today; see `INTEGRATIONS.md`, "Buyer messages").

## `GET /api/v1/orders/{id}/billing`

What the marketplace has charged, and credited back, for one order:

```json
{
  "entries": [
    {"id": "...", "occurred_at": "...Z", "type_id": "SUC", "type_name": "Prowizja od sprzedaży", "amount": "-8.50", "currency": "PLN"}
  ],
  "total": "-8.50",
  "currency": "PLN"
}
```

`amount` is signed: a charge is negative, a refund of a fee positive. `total`
is the entries added up, in the order's currency (an entry in another one is
listed but not added); `"0.00"` and an empty list when nothing is recorded,
which is also what an order looks like before Allegro has posted its fees, or
while the application cannot read the marketplace's billing (see
`INTEGRATIONS.md`, "Fees"). `404` for an unknown order.

## `GET /api/v1/orders`

All query parameters are optional and combine. Filtering is applied by the
database, so `total` counts every match rather than the returned page.

| Parameter | Meaning |
| --- | --- |
| `skip`, `limit` | pagination; `limit` defaults to 100, maximum 500 |
| `source` | `ALLEGRO` or `ERLI` |
| `status` | `NEW`, `CONFIRMED` (in progress), `READY_FOR_SHIPMENT`, `SHIPPED`, `DELIVERED`, `CANCELLED` |
| `queue` | a work queue, see below: `to_make`, `unpaid`, `to_ship`, `late` |
| `sort` | `newest` (default: `ordered_at` newest first), `oldest`, or `at_risk`: closest `dispatch_by` first, orders without one last |
| `search` | case-insensitive substring of: `external_id`, `customer_email`, the buyer's login, full name, last name, company or phone, the pickup point's id or name, any item's `sku` or name, any address's city, any shipment's waybill; also an Anvero order number in any form a person types it (`AN-000123`, `an-123`, `000123`, `123`). An order matching on several items or addresses is still one result |
| `date_from`, `date_to` | `YYYY-MM-DD`, both inclusive, calendar days in the business timezone, matched on `ordered_at` |
| `cancellation_warning` | `true` returns only orders cancelled on their marketplace whose Anvero status is not `CANCELLED` |
| `deleted` | `true` lists the deleted orders instead of the ones in use (default `false`); see "Deleting an order" |
| `starred`, `flagged` | `true` keeps only the orders the operator has starred / flagged (default `false`, which does not narrow); see "Marks". Both together keep an order that has both |

Response: `{"items": [...], "total": N, "skip": N, "limit": N}`, newest
`ordered_at` first. Each item also carries `customer_login`,
`customer_first_name`, `customer_last_name`, `payment_type` and
`payment_provider` — flat columns on `orders`, so the list gets them at no
extra query cost. It also carries `items`, in short: for each item its `name`,
`sku`, `quantity` and `image_url` (null when there is no picture), in the
order's item order, loaded for the whole page in one extra query. Prices,
ids, `delivery` and the rest of `GET /api/v1/orders/{id}`'s nested detail are
not in the list.

### The list's small facts

Each item also carries what the list draws its icons and its country from, all
flat columns except the country: `status_changed_at` (when the status last
changed, null for an order that has kept its first one, so the list counts from
`ordered_at`), `delivery_country_code` (the delivery address's country, e.g.
`PL`, null when none is recorded; the addresses are loaded for the whole page in
one extra query), `paid_amount` (null when unknown), `invoice_required`,
`has_buyer_message` and `has_seller_note` (whether there is one, never its text),
and the two marks below.

### Marks

`PATCH /api/v1/orders/{id}/marks` sets the operator's own marks: a star for
"important" and a flag for "come back to this". Body: `{"starred": true}`,
`{"flagged": false}` or both; a mark left out stays as it is. Returns the order
with its details. The marks are Anvero's alone: nothing is sent to a marketplace,
`updated_at` and the status history are untouched, and an order that is deleted
can still be marked. `404` for an unknown id. Every order carries `starred` and
`flagged` (`false` until set) in the list and in the detail.

### The operator's note

`PATCH /api/v1/orders/{id}/note` writes the operator's own note on an order. Body:
`{"note": "Ring before sending"}`; `{"note": null}`, an empty text or one of only spaces
takes the note away. At most 4000 characters (`422` beyond that); line breaks are kept.
Returns the order with its details, where the note is `internal_note` (null when there
is none). It is Anvero's alone: unlike `seller_note`, which is the marketplace's and
read-only, it is never sent to a marketplace and no import touches it. It is in
`GET /orders/{id}` only, not in the list. The status history and `updated_at` are
untouched, and an order that is deleted can still be noted. `404` for an unknown id.

### Deleting an order

`DELETE /api/v1/orders/{id}` takes an order out of the application without
erasing it: it sets `deleted_at` (and `deleted_by`, the operator's email) and
returns the order with its details. The row stays, because the marketplace's
next import would otherwise bring the order back, and because Anvero's own
number is never reused. A deleted order:

- is in no list, no total, no queue and no figure of `GET /orders/stats`
  (the dashboard, the queue counts, the to-make list, the buyer's other orders),
  and is listed only by `GET /orders?deleted=true`;
- is still returned by `GET /orders/{id}`, with `deleted_at` set, so its page can
  say so and offer to restore it;
- is skipped by an import (`created` and `updated` do not count it, and nothing
  about it is overwritten) and is not polled for tracking;
- refuses a change: a status change, a tracking number and a label are answered
  `409 Order is deleted; restore it first`.

`DELETE` answers `409` for an order with a label being bought or bought (cancel
the label first), `404` for an unknown id, and `200` for an order already deleted,
changing nothing (the first `deleted_at` and `deleted_by` stay).
`POST /api/v1/orders/{id}/restore` clears both; an order in use is answered `200`
unchanged. `OrderRead` carries `deleted_at` and `deleted_by`, null for an order
in use.

Each order carries Anvero's own number: `order_number`, an integer that is
continuous across every source, given once when the order is created and never
changed or reused, and `order_label`, the same number as it is shown and
searched (`AN-000123`). Clients cannot choose it. The marketplace's own id is
still `external_id`.

Each order has two dates: `ordered_at`, when the buyer placed it, and
`created_at`, when the row was created in Anvero. For an imported order they
differ, and filters, sorting and the dashboard's `this_week` all use
`ordered_at`. `POST /api/v1/orders` accepts an optional `ordered_at`; without
it the order is dated now.

Each order carries `marketplace_status`: what the marketplace's own status
mapped to at the last import, or `null` for an order no import has touched. It
is what the last import compared against: when it moves, `status` moves to it
(recorded in the history with no author), but a status the operator set by hand
stands until it does, so the two can differ — that is the point of returning
it, and the interface shows the difference. Both the list and the detail response include
it.

Beside it, `marketplace_status_label` carries the marketplace's own status
unmapped, e.g. `"READY_FOR_SHIPMENT"`, since several of those map to one
Anvero status. It is passed through as the marketplace sends it and is not a
fixed set of values, so treat it as text to display, not to branch on.

Each order carries `marketplace_cancelled_at`: `null`, or when an import first
found the order cancelled on its marketplace. The import then sets the status
to `CANCELLED`, so an order with this set and any other status is one the
operator has since moved on, and needs their attention. `GET /api/v1/orders/stats` reports how many
such orders exist as `cancellation_warnings`, using the same definition as the
filter above. The warning clears when the status is `CANCELLED` again.

Each order carries `dispatch_by`: the latest moment the parcel must be handed
over, as the marketplace states it, or `null` when it states none.

### Work queues

`queue` narrows the list to the orders waiting on someone, and
`GET /api/v1/orders/stats` returns how many are in each as
`queues: {"to_make": N, "unpaid": N, "to_ship": N, "late": N}`, by the same
definitions. No queue holds an order cancelled on its marketplace.

- **unpaid**: `NEW`, `CONFIRMED` or `READY_FOR_SHIPMENT`, and the buyer owes
  payment before shipping: `paid_amount` is known and below `total_amount`, or
  the order has a `payment_type` and no `paid_amount` at all. Cash on
  delivery and deferred payment never count as unpaid. An order with neither
  a payment type nor a paid amount (entered by hand) is not called unpaid.
- **to_make**: `NEW` or `CONFIRMED`, and not unpaid.
- **to_ship**: `READY_FOR_SHIPMENT`, and not unpaid.
- **late**: in `to_make` or `to_ship` with `dispatch_by` in the past; it
  overlaps both.

## `GET /api/v1/orders/production`

The `to_make` queue (see "Work queues" above) turned around by product, for
the "to make" page. Unpaged: it is the day's work, not the history.

Two optional query parameters narrow it to the orders being made now:

- `status`: keep the orders in one Anvero status (the queue holds `NEW` and
  `CONFIRMED`; any other gives an empty list).
- `search`: keep the orders the order list's search finds (an Anvero number,
  a buyer's login or name, a product's code or name, ...), at most 500 characters.
  Several can be given separated by commas, semicolons or line breaks
  (`AN-000041, AN-000043`), and an order matching any of them counts. A search
  that finds nothing gives an empty list, not the whole one; one made only of
  separators is no search.

Both hold together. `order_count` and every line follow the narrowing, and a deleted
order is never in the list.

```json
{
  "order_count": 2,
  "lines": [
    {
      "key": "sku:MUG-350", "sku": "MUG-350", "offer_id": "123", "name": "Mug",
      "image_url": null, "quantity": 3, "dispatch_by": "...Z", "done": false,
      "orders": [
        {"id": "...", "order_label": "AN-000012", "source": "ALLEGRO", "status": "NEW", "quantity": 1, "dispatch_by": "...Z"},
        {"id": "...", "order_label": "AN-000015", "source": "ERLI", "status": "CONFIRMED", "quantity": 2, "dispatch_by": null}
      ]
    }
  ]
}
```

Items are the same product when they share the seller's `sku`; without one,
the listing (`offer_id`); without either, the `name`. The line's `name` and
`offer_id` are those of the first item met. `quantity` is the sum over its
orders, and an order with the product on two lines is listed once with both
counted. Lines come in the order their product is first needed: `dispatch_by`
is the earliest among the line's orders, lines without any deadline come last,
oldest order first; each line's `orders` are in the same order. `order_count`
counts the queue's orders, including any without items.

`done` says the line is made: it was ticked off (below) for at least as many as it
asks for now, so an order that arrives later and raises `quantity` brings it back.

## `PUT /api/v1/orders/production/checks`

Tick a product on the to-make list off as made, or take the tick away. Kept in the
database, so it shows on every computer and to everyone.

```json
{"key": "sku:MUG-350", "quantity": 3, "done": true}
```

`key` is a line's `key` (1 to 512 characters), `quantity` is how many the list asks
for as it stands on the screen (at least 1), `done` false takes the tick away (also
when there was none). Answers `{"key": "sku:MUG-350", "done": true, "quantity": 3}`.
`422` for an empty or longer key, or a quantity under 1. A tick nobody has touched
for 90 days is dropped whenever another is made. A product ticked in a narrowed view
(a status or a search) is ticked for that view's quantity only, so the whole list may
still show it as not made.

## Safe mode: `GET` and `PUT /api/v1/settings/safe-mode`

`{"enabled": true, "changed_at": null, "changed_by": null}`. Safe mode is on
until someone switches it off; `changed_at` and `changed_by` (an email) say
who last switched it, null while no one has. `PUT` takes `{"enabled": bool}`
and returns the same shape.

While it is on, no change reaches a marketplace: every write Anvero would make
(a status, a tracking number, later messages and invoices) is recorded with
the outcome `DRY_RUN` instead of being sent. It is read afresh on every write,
so switching it on stops the very next one.

## `GET /api/v1/marketplace-writes`

Every write to a marketplace, sent or held back, newest first: `order_id`
(optional) narrows it to one order, `limit` (default 50, at most 500).

```json
[{"id": "...", "created_at": "...Z", "source": "ALLEGRO", "order_id": "...",
  "action": "fulfillment_status", "payload": "{\"status\": \"SENT\"}",
  "outcome": "DRY_RUN", "detail": null, "user": "operator@example.com"}]
```

`payload` is the JSON that was, or would have been, sent, as text. `outcome`
is `DRY_RUN` (safe mode held it back), `SENT` or `FAILED`; `detail` is the
marketplace's answer or the error. Nothing writes to it yet: the first writes
come with feature plan stage A6.

## `GET /api/v1/status`

What the application status page shows. Read entirely from what Anvero holds:
nothing is asked of Allegro or Erli, so it can be called as often as wanted
and never rotates a token (`DECISIONS.md`).

```json
{"checked_at": "...Z", "version": "0.1.0", "safe_mode": true,
 "allegro": {"state": "warning", "problems": ["token_expiring"],
   "application_complete": true, "connected": true, "environment": "sandbox",
   "account_login": "seller_login",
   "token_issued_at": "...Z", "token_expires_at": "...Z",
   "last_import": {"at": "...Z", "created": 2, "updated": 7, "error": null},
   "schedule": {"interval_minutes": 15, "running": true, "standby": false,
                "started_at": "...Z", "next_run_at": "...Z", "last_run_at": null},
   "message_schedule": {"interval_minutes": 15, "running": true, "standby": false,
                "started_at": "...Z", "next_run_at": "...Z", "last_run_at": null}},
 "erli": {"state": "off", "problems": [], "configured": false,
   "last_import": {"at": null, "created": null, "updated": null, "error": null},
   "schedule": null}}
```

`state` is `off` (not set up at all), `ok`, `warning` (works, but needs
attention) or `error` (does not work until someone acts); `problems` says why,
as codes the interface words:

| Code | Level | Meaning |
| --- | --- | --- |
| `application_incomplete` | warning | client id, secret or User-Agent missing (Allegro) |
| `not_connected` | warning | no seller account connected (Allegro) |
| `never_imported` | warning | connected, but no import has run, so the connection is unproven |
| `token_expiring` | warning | the refresh token lapses within 14 days (Allegro) |
| `token_expired` | error | the refresh token has lapsed: connect the account again |
| `last_import_failed` | error | the last import ended in an error, in `last_import.error` |
| `import_overdue` | warning | the schedule runs, but no import finished for three intervals |
| `schedule_stopped` | warning | an interval is set, but the schedule is not running in this backend (and no other backend holds it) |
| `message_schedule_stopped` | warning | the same for reading buyer messages |

`token_expires_at` is `token_issued_at` plus Allegro's three months (taken as
90 days); every import issues a new token, so it only nears when nothing
imports. `last_import` is the last import by any route: the button, the
schedule or either script. `schedule` is this backend's own: another backend
importing on the same database is not seen here, though its imports show in
`last_import`. It lives in memory, so `last_run_at` is null until the first
scheduled run after a start. `standby` is true when another backend holds the
schedule's lease: this one is waiting its turn, which is not a problem. Erli has
a `schedule` of its own (the same interval) once a key is set; null before.

## Labels through Wysyłam z Allegro

`GET`/`PUT /api/v1/settings/shipping`:
`{"sender": {"name", "company", "street", "postal_code", "city",
"country_code", "email", "phone"} | null, "default_package": {"length_cm",
"width_cm", "height_cm", "weight_kg"} | null}`. `company` is optional,
`country_code` two capitals (default `PL`); dimensions in centimetres (at most
350), weight in kilograms (at most 100), as decimal strings. `PUT` replaces
both; null clears one.

A label: `{"id", "created_at", "status", "shipment_id", "carrier_id",
"waybill", "length_cm", "width_cm", "height_cm", "weight_kg", "error"}`.
`status` is `PENDING` (Allegro is still creating the shipment), `CREATED`,
`FAILED` (Allegro refused it, `error` says why) or `CANCELLED`.

`POST /api/v1/orders/{id}/labels` takes the parcel (`length_cm`, `width_cm`,
`height_cm`, `weight_kg`) and returns `{"label": ... | null,
"marketplace_write": {...}}`. It reads the order's delivery method from
Allegro, then sends the create command through safe mode: with safe mode on,
`label` is null and the write is `DRY_RUN`, its payload what would have been
sent; a refused command is a `FAILED` write and no label. Otherwise it waits a
few seconds for Allegro: the label comes back `CREATED` (and the waybill is
added to the order, as `POST /orders/{id}/shipments` would), `FAILED`, or
still `PENDING`, for `refresh` to settle. `409` when the label cannot be asked
for: not an Allegro order, cash on delivery (not shipped by the business), no sender in
the settings, a label already `PENDING` or `CREATED` on the order (cancel it
first), or no delivery method on Allegro's order; `502` when Allegro cannot be
reached.

`POST .../cancel` (a `CREATED` label only, else `409`) returns the same shape;
the label turns `CANCELLED` once Allegro confirms, or keeps `CREATED` with the
reason in `error`. `GET .../pdf` returns `application/pdf`; `409` unless the
label is `CREATED`. Printing is a read: it does not go through safe mode.
Every label has `printed_at`: when its PDF was last fetched, by either route;
null until then.

`GET /api/v1/labels` lists `CREATED` labels across every order, oldest first
(the order they were bought), at most 200. `view` chooses which: `to_print`
(the default: never printed), `no_pickup` (no courier ordered, or only a
refused one) or `all`; anything else is `422`. Each is a label plus
`order_id`, `order_label` (the `AN-` number), `buyer` (the name, else login,
else email), `delivery_method` and `pickup`: the courier ordered for it, or
null (`{"id", "created_at", "status", "pickup_id", "carrier_id",
"ready_date", "proposal_label", "error"}`, `status` being `PENDING`,
`ORDERED` or `FAILED`).

`POST /api/v1/labels/pdf` takes `{"label_ids": [...]}` (1 to 50) and returns
one A6 PDF with those labels in that order, from one request to Allegro, and
notes them printed. `404` if an id is unknown, `409` if any is not `CREATED`
or there are more than 50, `422` for an empty list, `502` when Allegro fails.

`GET /api/v1/labels/test-pdf` returns a sample A6 label as a PDF, drawn by
Anvero itself: a frame and corner squares (to see clipping), a 100 mm ruler (to
see scaling), lines one to four printer dots wide (203 dpi) and a solid block
(to see how fine print and black come out), text from 6 to 12 pt, and the sender
and default parcel saved in Integrations, printed without Polish letters. It buys
nothing, calls no marketplace and does not go through safe mode; it needs only
the login.

### Courier pickup

`POST /api/v1/pickups/proposals` takes `{"label_ids": [...], "ready_date":
"YYYY-MM-DD"}` and returns the slots Allegro proposes, `[{"id", "label"}]`;
an empty list means no courier comes for those parcels that day (a parcel
locker shipment is dropped off, not collected). It changes nothing and does
not go through safe mode. `POST /api/v1/pickups` takes the same plus
`proposal_id` and `proposal_label` (the slot as shown) and returns
`{"pickup": ... | null, "marketplace_write": {...}}`: null with a `DRY_RUN`
write in safe mode, or with a `FAILED` write when Allegro refused the
command; otherwise the pickup, `ORDERED`, `PENDING` (for `refresh`) or
`FAILED` with `error`, whose parcels are then free again. Both refuse with
`409`: more than 50 parcels, a day already past (in the business timezone),
a parcel not `CREATED`, a parcel already in a pending or ordered pickup, or
parcels of more than one carrier (one pickup serves one carrier); `404` for
an unknown label; `502` when Allegro cannot be reached.

## Changes that reach the marketplace

`PATCH /api/v1/orders/{id}/status` and `POST /api/v1/orders/{id}/shipments`
return the order in the shape of `GET /api/v1/orders/{id}`, plus
`marketplace_write`: null when nothing was for the marketplace, otherwise the
entry it made in `GET /api/v1/marketplace-writes` (`DRY_RUN` in safe mode,
`SENT`, or `FAILED` with Allegro's reason in `detail`). A failure to send is
not an error response: the change in Anvero stands, and `marketplace_write`
says it did not reach Allegro.

A status is sent only for an Allegro order, and only when it actually changes:
`NEW` → `NEW`, `CONFIRMED` → `PROCESSING`, `READY_FOR_SHIPMENT` →
`READY_FOR_SHIPMENT`, `SHIPPED` → `SENT`, `DELIVERED` → `PICKED_UP`.
`CANCELLED` is never sent: an Allegro order is cancelled on Allegro.

`POST /api/v1/orders/{id}/shipments` takes
`{"carrier_id": "INPOST", "carrier_name": null, "waybill": "..."}`.
`carrier_id` is one of `INPOST`, `DPD`, `DHL`, `POCZTA_POLSKA`, `UPS`, `GLS`,
`FEDEX`, `ALLEGRO`, `OTHER` (`422` otherwise); `OTHER` needs `carrier_name`.
The parcel is stored on any order; for an Allegro one it is also sent. A
parcel added in Anvero stays on the order when an import does not list it.

`POST /api/v1/messages/threads/{id}/reply` reports the same way, as
`marketplace_write` in its own response rather than nested in an order (a
thread is not one): action `message_reply`.

## `GET /api/v1/orders/{id}/buyer-orders`

The same buyer's other orders, in the shape of the list's items, newest
`ordered_at` first, at most 20; `404` for an unknown order. The same buyer is
the same `customer_email`, or the same `customer_login` on the same `source`
(a login is unique only within one marketplace). An empty list means this is
the buyer's first order in Anvero.

## `GET /api/v1/orders/{id}`

Returns the order with the fields the list has, plus its details:

```json
{
  "id": "...", "external_id": "...", "source": "ALLEGRO", "status": "NEW",
  "customer_email": "...", "total_amount": "149.99", "currency": "PLN",
  "ordered_at": "...Z", "created_at": "...Z", "updated_at": "...Z",
  "marketplace_status": "CONFIRMED", "marketplace_status_label": "PROCESSING",
  "marketplace_cancelled_at": null, "dispatch_by": "...Z",
  "customer": {"login": "...", "first_name": "...", "last_name": "...", "company_name": null, "phone": "..."},
  "items": [
    {"id": "...", "external_id": "...", "offer_id": "...", "sku": "KUB-350", "name": "...", "quantity": 1, "unit_price": "24.99", "image_url": "https://a.allegroimg.com/original/..."}
  ],
  "delivery": {
    "method": "InPost Paczkomat 24/7", "cost": "12.99",
    "address": {"first_name": "...", "last_name": "...", "company_name": null, "street": "...", "postal_code": "...", "city": "...", "country_code": "PL", "phone": "...", "tax_id": null},
    "pickup_point": {"id": "WAW01M", "name": "...", "address": null}
  },
  "payment": {"type": "ONLINE", "provider": "P24", "paid_amount": "149.99", "paid_at": "...Z"},
  "invoice": {"required": false, "address": null},
  "buyer_message": null,
  "seller_note": null,
  "shipments": [
    {"id": "...", "external_id": "...", "carrier_id": "DHL", "carrier_name": null, "waybill": "12345678910PL", "shipped_at": "...Z", "tracking_status": "IN_TRANSIT", "tracking_updated_at": "...Z"}
  ]
}
```

`shipments` are the parcels sent for the order; empty until one is. Unlike the
rest of the details, they are also in each item of `GET /api/v1/orders`, since
the list shows them. `tracking_status` is the carrier's latest code, or null
when none was read (see `INTEGRATIONS.md`, "Shipments and tracking").

Every detail may be null, and `items` may be empty: orders entered by hand and
orders stored before details existed have none. The four objects `customer`,
`delivery`, `payment` and `invoice` are always present, so a client checks
fields, not objects. Addresses (all in the shape of `delivery.address`) and
`pickup_point` are either an object or null. Text is never an empty string:
absent is null.

`unit_price` is per unit after discounts. The item totals plus
`delivery.cost` normally add up to `total_amount`, but marketplace surcharges
and order-level discounts can make them differ. `payment.type` is one of
`ONLINE`, `BANK_TRANSFER`, `CASH_ON_DELIVERY`, `DEFERRED` and `OTHER`.
`paid_amount` null means unknown, `"0.00"` means known to be unpaid.

`GET /api/v1/orders` does not include details; they are for one order at a
time.

`POST /api/v1/orders` accepts the same detail fields, all optional (items
without `id`), and returns the created order in this shape.

## `PATCH /api/v1/orders/{id}/status`

Body: `{"status": "SHIPPED"}`. Returns the updated order with its details, in
the shape of `GET /api/v1/orders/{id}`.

Any status may currently be set from any other, so operators can correct
mistakes. The valid transitions for this business have not been decided; a
state machine belongs in `OrderService.update_order_status` once they are.

Sending the status the order already has is a no-op: it succeeds and records
nothing.

## `GET /api/v1/orders/{id}/history`

Returns the order's status transitions, most recent first:

```json
[{"id": "...", "from_status": "NEW", "to_status": "CONFIRMED", "changed_at": "...", "changed_by": "operator@example.com"}]
```

An unknown order id returns 404, so it is distinguishable from an order that
has never changed status, which returns an empty list.

`changed_by` is the email of the user who made the change. It is `null` for
changes recorded before logins existed, and for a user whose account has been
deleted.

## Conventions

- API identifiers are opaque Anvero identifiers.
- Errors have format `{"detail": "readable description"}` with appropriate HTTP code.
- Every `/api/v1/orders` and `/api/v1/integrations` endpoint, reading or
  writing, requires a login token and answers `401` without one.
  `/api/v1/health` and `/api/v1/` stay public.
- Status change creates an entry in the status history, recording who made it.
