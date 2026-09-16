# API Contract

API will be versioned under the `/api/v1` prefix. Communication format: JSON; dates: ISO 8601 in UTC.

## MVP Planned Endpoints

| Method | Path | Meaning |
| --- | --- | --- |
| `GET` | `/api/v1/health` | service status |
| `GET` | `/api/v1/orders` | order list with filters |
| `GET` | `/api/v1/orders/{id}` | order details |
| `PATCH` | `/api/v1/orders/{id}/status` | internal status change |
| `GET` | `/api/v1/integrations` | connected sources list |

## Conventions

- API identifiers are opaque Anvero identifiers.
- Errors have format `{"detail": "readable description"}` with appropriate HTTP code.
- Data-changing operations require authentication when login mechanism is deployed.
- Status change creates an entry in the status history.
