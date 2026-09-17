# Data Model

The model will be deployed via migrations after framework selection, but a common data language already applies.

| Entity | Role | Key Fields |
| --- | --- | --- |
| `integration` | configured data source | `provider`, `external_account_id`, `status` |
| `order` | order in Anvero | `id`, `integration_id`, `external_id`, `status`, `ordered_at`, `currency` |
| `order_item` | order item | `order_id`, `sku`, `name`, `quantity`, `unit_price` |
| `customer` | buyer | `name`, `email`, `phone` |
| `address` | shipping or invoice address | `order_id`, `type`, address data |
| `shipment` | shipment | `order_id`, `carrier`, `tracking_number`, `status` |
| `order_status_history` | status audit | `order_id`, `from_status`, `to_status`, `changed_at` |

`external_id` is unique only within an integration. Amounts are stored as decimal values, never as `float`. Integration access credentials do not go to repositories or logs.

## Implemented so far

Migrations currently create `users`, `orders`, `order_status_history` and
`integration_credentials`. Everything else in the table above is still a
target.

`orders` deviates from the target shape while there are no integrations to
point at:

- `source` is an enum (`ALLEGRO`, `ERLI`) standing in for `integration_id`.
- `customer_email` is a column on the order rather than a `customer` row.
- `marketplace_cancelled_at` (nullable) is not in the target. It records when
  an import first found the order cancelled on its marketplace; the Anvero
  status is left to the operator, so this is what flags the conflict.
- `ordered_at` matches the target. It is separate from `created_at` because
  for an imported order the purchase and the row's creation are different
  moments; orders that existed before the column was added were backfilled
  with their `created_at`, since they were all entered locally.

All timestamps are stored in UTC. SQLite keeps no zone and returns them naive;
the API attaches UTC on the way out.

`order_status_history` matches the target: `order_id`, `from_status`,
`to_status`, `changed_at`, plus `changed_by_user_id`, a nullable reference to
`users` that becomes null if the account is deleted, so the history outlives
the user. Entries made before logins existed have no author.

`integration_credentials` is not in the target table above; it is the first
piece of `integration`. Allegro rotates its refresh token on every use, so
the latest token has to be kept between runs:

| Column | Meaning |
| --- | --- |
| `provider` | primary key, e.g. `ALLEGRO` |
| `refresh_token` | the most recently issued refresh token |
| `seed_fingerprint` | SHA-256 of the `.env` token the chain started from; a different `.env` token means a fresh authorization |
| `updated_at` | last rotation |

The rule above about credentials is read as "never committed to Git and never
logged": the token lives only in the local, git-ignored database file, as it
already did in the git-ignored `.env`.
