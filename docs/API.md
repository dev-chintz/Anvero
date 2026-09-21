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
| `GET` | `/api/v1/orders/{id}` | one order with its details: items, buyer, delivery, payment, invoice |
| `PATCH` | `/api/v1/orders/{id}/status` | internal status change |
| `GET` | `/api/v1/orders/{id}/history` | status change history |
| `POST` | `/api/v1/orders` | create an order — local testing until marketplace ingestion exists |
| `POST` | `/api/v1/auth/login` | obtain a JWT; rate limited to 5 attempts per minute per IP |
| `GET` | `/api/v1/users/me` | current user |
| `GET` | `/api/v1/integrations/allegro` | whether Allegro is configured |
| `POST` | `/api/v1/integrations/allegro/import` | run an Allegro import; rate limited to 6 attempts per minute per IP |

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

Returns `{"configured": true}` or `{"configured": false}` — nothing else.
Never returns a credential, a token or any part of one, even when configured.
Requires a login, like every endpoint below `/api/v1` except `/health` and
the root.

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
rather than queueing.

Error responses:

| Status | When |
| --- | --- |
| `409` | Allegro is not configured (`ALLEGRO_CLIENT_ID`/`_SECRET`/`_USER_AGENT`/`_REFRESH_TOKEN` missing), or an import is already running |
| `502` | Allegro rejected the credentials, or any other integration failure (unreachable, non-JSON response, etc.) |

Every error detail is a plain description; none of them include a token,
credential or raw Allegro response.

## `GET /api/v1/orders`

All query parameters are optional and combine. Filtering is applied by the
database, so `total` counts every match rather than the returned page.

| Parameter | Meaning |
| --- | --- |
| `skip`, `limit` | pagination; `limit` defaults to 100, maximum 500 |
| `source` | `ALLEGRO` or `ERLI` |
| `status` | `NEW`, `CONFIRMED`, `SHIPPED`, `DELIVERED`, `CANCELLED` |
| `search` | substring of `external_id` or `customer_email`, case-insensitive |
| `date_from`, `date_to` | `YYYY-MM-DD`, both inclusive, calendar days in the business timezone, matched on `ordered_at` |
| `cancellation_warning` | `true` returns only orders cancelled on their marketplace whose Anvero status is not `CANCELLED` |

Response: `{"items": [...], "total": N, "skip": N, "limit": N}`, newest
`ordered_at` first. Each item also carries `customer_login`,
`customer_first_name`, `customer_last_name`, `payment_type` and
`payment_provider` — flat columns on `orders`, so the list gets them at no
extra query cost, unlike `items`, `delivery` and the rest of
`GET /api/v1/orders/{id}`'s nested detail, which needs a join the list
does not do.

Each order has two dates: `ordered_at`, when the buyer placed it, and
`created_at`, when the row was created in Anvero. For an imported order they
differ, and filters, sorting and the dashboard's `this_week` all use
`ordered_at`. `POST /api/v1/orders` accepts an optional `ordered_at`; without
it the order is dated now.

Each order carries `marketplace_status`: what the marketplace's own status
mapped to at the last import, or `null` for an order no import has touched. It
is never applied to `status`, which belongs to the operator after the order is
first seen, so the two can differ — that is the point of returning it, and the
interface shows the difference. Both the list and the detail response include
it.

Beside it, `marketplace_status_label` carries the marketplace's own status
unmapped, e.g. `"READY_FOR_SHIPMENT"`, since several of those map to one
Anvero status. It is passed through as the marketplace sends it and is not a
fixed set of values, so treat it as text to display, not to branch on.

Each order carries `marketplace_cancelled_at`: `null`, or when an import first
found the order cancelled on its marketplace. An import never changes the
Anvero status, so an order with this set and a status other than `CANCELLED`
needs the operator's attention. `GET /api/v1/orders/stats` reports how many
such orders exist as `cancellation_warnings`, using the same definition as the
filter above. The warning clears when the status is set to `CANCELLED`.

## `GET /api/v1/orders/{id}`

Returns the order with the fields the list has, plus its details:

```json
{
  "id": "...", "external_id": "...", "source": "ALLEGRO", "status": "NEW",
  "customer_email": "...", "total_amount": "149.99", "currency": "PLN",
  "ordered_at": "...Z", "created_at": "...Z", "updated_at": "...Z",
  "marketplace_status": "CONFIRMED", "marketplace_status_label": "READY_FOR_SHIPMENT",
  "marketplace_cancelled_at": null,
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
  "seller_note": null
}
```

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
