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
| `GET` | `/api/v1/orders/{id}` | order details |
| `PATCH` | `/api/v1/orders/{id}/status` | internal status change |
| `GET` | `/api/v1/orders/{id}/history` | status change history |
| `POST` | `/api/v1/orders` | create an order — local testing until marketplace ingestion exists |
| `POST` | `/api/v1/auth/login` | obtain a JWT; rate limited to 5 attempts per minute per IP |
| `GET` | `/api/v1/users/me` | current user |

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

## Planned

| Method | Path | Meaning |
| --- | --- | --- |
| `GET` | `/api/v1/integrations` | connected sources list |

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
`ordered_at` first.

Each order has two dates: `ordered_at`, when the buyer placed it, and
`created_at`, when the row was created in Anvero. For an imported order they
differ, and filters, sorting and the dashboard's `this_week` all use
`ordered_at`. `POST /api/v1/orders` accepts an optional `ordered_at`; without
it the order is dated now.

Each order carries `marketplace_cancelled_at`: `null`, or when an import first
found the order cancelled on its marketplace. An import never changes the
Anvero status, so an order with this set and a status other than `CANCELLED`
needs the operator's attention. `GET /api/v1/orders/stats` reports how many
such orders exist as `cancellation_warnings`, using the same definition as the
filter above. The warning clears when the status is set to `CANCELLED`.

## `PATCH /api/v1/orders/{id}/status`

Body: `{"status": "SHIPPED"}`. Returns the updated order.

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
- Every `/api/v1/orders` endpoint, reading or writing, requires a login token
  and answers `401` without one. `/api/v1/health` and `/api/v1/` stay public.
- Status change creates an entry in the status history, recording who made it.
