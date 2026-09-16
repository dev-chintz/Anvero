# API Contract

API is versioned under the `/api/v1` prefix. Communication format: JSON; dates: ISO 8601 in UTC.

## Implemented

| Method | Path | Meaning |
| --- | --- | --- |
| `GET` | `/api/v1/health` | service status |
| `GET` | `/api/v1/orders` | order list with filters |
| `GET` | `/api/v1/orders/stats` | aggregate figures for the dashboard |
| `GET` | `/api/v1/orders/{id}` | order details |
| `PATCH` | `/api/v1/orders/{id}/status` | internal status change |
| `POST` | `/api/v1/orders` | create an order — local testing until marketplace ingestion exists |
| `POST` | `/api/v1/auth/login` | obtain a JWT; rate limited to 5 attempts per minute per IP |
| `POST` | `/api/v1/users/register` | register a user |
| `GET` | `/api/v1/users/me` | current user |

## Planned

| Method | Path | Meaning |
| --- | --- | --- |
| `GET` | `/api/v1/integrations` | connected sources list |
| `GET` | `/api/v1/orders/{id}/history` | status change history |

## `GET /api/v1/orders`

All query parameters are optional and combine. Filtering is applied by the
database, so `total` counts every match rather than the returned page.

| Parameter | Meaning |
| --- | --- |
| `skip`, `limit` | pagination; `limit` defaults to 100, maximum 500 |
| `source` | `ALLEGRO` or `ERLI` |
| `status` | `NEW`, `CONFIRMED`, `SHIPPED`, `DELIVERED`, `CANCELLED` |
| `search` | substring of `external_id` or `customer_email`, case-insensitive |
| `date_from`, `date_to` | `YYYY-MM-DD`, both inclusive, matched on `created_at` |

Response: `{"items": [...], "total": N, "skip": N, "limit": N}`.

## `PATCH /api/v1/orders/{id}/status`

Body: `{"status": "SHIPPED"}`. Returns the updated order.

Any status may currently be set from any other, so operators can correct
mistakes. The valid transitions for this business have not been decided; a
state machine belongs in `OrderService.update_order_status` once they are.

## Conventions

- API identifiers are opaque Anvero identifiers.
- Errors have format `{"detail": "readable description"}` with appropriate HTTP code.
- Data-changing operations require authentication when login mechanism is deployed.
- Status change creates an entry in the status history — not yet implemented;
  the history model does not exist.
