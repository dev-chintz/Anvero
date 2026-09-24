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

`orders.order_number` is Anvero's own number for an order: an integer, unique across every source, continuous, given once when the row is created (by the ORM, from a row in the `counters` table, inside the same transaction) and never changed or reused, so it can have gaps but no repeats. Only the integer is stored: the `AN-` prefix and the zero padding are applied where it is shown (`app/core/order_number.py`), so changing how it reads needs no migration. It is an internal identifier, not an accounting document number; invoices will need their own gapless numbering. The migration numbered the orders that existed by purchase date, oldest first.

`external_id` is unique only within an integration. Amounts are stored as decimal values, never as `float`. Integration access credentials do not go to repositories or logs.

## Implemented so far

Migrations currently create `users`, `orders`, `order_items`,
`order_addresses`, `order_shipments`, `billing_entries`,
`order_status_history`, `integration_credentials`, `message_threads`,
`messages` and `after_sales_cases`. `integration` and `customer` are still targets.

`orders` deviates from the target shape while there are no integrations to
point at:

- `source` is an enum (`ALLEGRO`, `ERLI`) standing in for `integration_id`.
- `customer_email` is a column on the order rather than a `customer` row,
  and so are the other buyer details below. A `customer` row would need
  matching one buyer across orders, which nothing needs yet.
- `marketplace_status` (nullable, the same `order_status` enum) is not in the
  target. It holds what the marketplace's own status mapped to at the last
  import, beside `status`; a move in it moves `status` too, and the interface
  shows it when the two differ (the operator has set something Allegro has
  not caught up with). NULL for an order no import has touched.
- `marketplace_status_label` (nullable, 64 characters) holds the same status
  unmapped, in the marketplace's own words, e.g. Allegro's
  `READY_FOR_PICKUP`. Anvero's statuses collapse distinctions the
  marketplace's panel shows — `SENT` and `READY_FOR_PICKUP` are both
  `SHIPPED` — and this is what the interface displays.
- `status` (and `marketplace_status`) take one of `NEW`, `CONFIRMED` (in
  progress: being made or prepared), `READY_FOR_SHIPMENT` (made and packed,
  waiting for the carrier), `SHIPPED`, `DELIVERED`, `CANCELLED`.
  `READY_FOR_SHIPMENT` was added on 2026-09-24; the migration moved orders
  whose Allegro label already said so, and whose status still matched
  Allegro's, from `CONFIRMED` to it, without a history entry (a
  reclassification, not a change anyone made).
- `status_set_at` (nullable) is when an operator last set the status by hand
  (the API, not an import). An import does not move the status for a
  marketplace change older than this: the last change made in Anvero wins
  (`DECISIONS.md`). The migration filled it from the history's latest change
  with an author.
- `dispatch_by` (nullable, indexed) is not in the target: the latest moment
  the seller must hand the parcel over, as the marketplace states it (Allegro:
  `delivery.time.dispatch.to`). The work queues sort and flag orders by it.
- `marketplace_cancelled_at` (nullable) is not in the target. It records when
  an import first found the order cancelled on its marketplace; the Anvero
  status is left to the operator, so this is what flags the conflict.
- `ordered_at` matches the target. It is separate from `created_at` because
  for an imported order the purchase and the row's creation are different
  moments; orders that existed before the column was added were backfilled
  with their `created_at`, since they were all entered locally.

### Order details

Every detail is nullable (`invoice_required` defaults to false), because an
order entered by hand may have none and orders from before the details
existed have none. For an imported order the marketplace owns all of them: a
re-import replaces them, items and addresses included.

Columns on `orders`, one per order:

| Column | Meaning |
| --- | --- |
| `customer_login`, `customer_first_name`, `customer_last_name`, `customer_company_name`, `customer_phone` | the buyer |
| `buyer_message` | what the buyer wrote to the seller at checkout |
| `seller_note` | the seller's own note on the order, written on the marketplace itself; read-only here |
| `delivery_method`, `delivery_cost` | how it ships and what the buyer paid for that |
| `pickup_point_id`, `pickup_point_name` | the parcel locker or pickup point, if any |
| `payment_type` | `ONLINE`, `BANK_TRANSFER`, `CASH_ON_DELIVERY`, `DEFERRED` or `OTHER` |
| `payment_provider` | the payment operator as the marketplace names it, e.g. `P24` |
| `paid_amount`, `paid_at` | null means unknown; `0.00` means known to be unpaid |
| `invoice_required` | the buyer asked for an invoice |

`payment_type` is a plain string column validated by the application, not a
database enum type: the list grows with each marketplace, and a new value in a
PostgreSQL enum type needs its own migration.

`order_items` (matches the target `order_item`): `order_id`, `position` (the
marketplace's line order), `external_id`, `offer_id`, `sku` (the seller's own
product code, if the listing has one), `name`, `quantity`, `unit_price` (per
unit, in the order's currency, after discounts), `image_url` (the offer's
picture, fetched from Allegro's own product-offer resource at import time;
best-effort, so a deleted offer or a missing scope leaves it null).

`order_addresses` (matches the target `address`): `order_id`, `type`
(`DELIVERY`, `INVOICE` or `PICKUP_POINT`, at most one of each per order,
enforced by a unique constraint), `first_name`, `last_name`, `company_name`,
`street`, `postal_code`, `city`, `country_code`, `phone`, `tax_id`.

`order_shipments` (the target `shipment`): `order_id`, `position`,
`external_id` (the marketplace's id), `carrier_id` (e.g. `DHL`, or `OTHER`),
`carrier_name`, `waybill`, `shipped_at` (when the number was added, by the
marketplace's clock), `tracking_status` (the carrier's latest code:
`PENDING`, `IN_TRANSIT`, `RELEASED_FOR_DELIVERY`, `AVAILABLE_FOR_PICKUP`,
`NOTICE_LEFT`, `ISSUE`, `DELIVERED`, `RETURNED`; null when none was read) and
`tracking_updated_at`, and `added_in_anvero` (a tracking number typed in on
the order rather than read from the marketplace). Replaced by an import like
the items, except that parcels an import could not read are left as they
were, and a parcel added in Anvero that the marketplace does not list is kept.

All three child tables are deleted with their order.

`billing_entries`: the marketplace's own record of fees and corrections on the
seller's account, one row per operation, never changed once stored. `source`,
`external_id` (the marketplace's id; unique together), `occurred_at`,
`type_id` and `type_name` (its code and name for the kind of operation, e.g.
`SUC`, sales commission), `amount` (signed: a charge is negative, a refund of
a fee positive) and `currency`, `order_external_id` (the marketplace's order
id, for the types that name one; indexed) and `offer_id`, `offer_name`. There
is deliberately no foreign key to `orders`: an entry may be read before its
order is, or belong to none (a subscription, an advertising fee). It is tied
to an order by `(source, order_external_id)`.

`message_threads` and `messages`: one buyer-seller conversation each, and its
messages, read from a marketplace's Message Center (plan B2, `INTEGRATIONS.md`,
"Buyer messages"). A thread is kept by `(source, external_id)`, like
`billing_entries`; unlike an order's items, its messages are not wholly
replaced on sync, only added to, since a message once sent is never edited or
withdrawn on the marketplace's side either (matched by `(thread_id,
external_id)`, so reading an overlapping page twice adds nothing).
`interlocutor_login` is the buyer's own login, the only name a thread
carries. `order_external_id` (nullable, indexed) is the marketplace's id of
an order a message in the thread named, if any - not a foreign key, for the
same reason `billing_entries.order_external_id` is not one: the order may
not exist in Anvero, or the thread may name none. `last_message_at` and
`last_message_text` are cached from the newest message so the inbox list
needs no join; `last_message_at` is also what a sync compares against to
decide whether a thread's messages need reading again. `read` mirrors the
marketplace's own flag as of the last sync - Anvero never writes it back, so
opening a thread here does not mark it read there. `aside` is local to
Anvero only, never touched by a sync: an operator sets it to come back to a
thread later, and the inbox excludes it by default.

A message's `external_id` is null for a reply written in Anvero that safe
mode held back or that the marketplace refused - the same idea as
`order_shipments.external_id` before an import confirms it. `direction`
(`IN` from the buyer, `OUT` from the seller) is not read from a field of its
own on Allegro's side - none is confirmed to exist - but decided by
comparing the message's author login to the connected seller's own
(`integration_credentials.account_login`); see `INTEGRATIONS.md`, "Buyer
messages". `created_in_anvero` marks a reply written here, as opposed to one
read from the marketplace, which includes the seller's own past replies sent
from its own panel.

`after_sales_cases`: a return, claim or dispute read from a marketplace (plan
B4, `INTEGRATIONS.md`, "Returns and claims"), one row each, kept by `(source,
external_id)` and replaced on every sync (the marketplace owns every field).
`kind` is `RETURN`, `CLAIM` or `DISPUTE`; `status` is the marketplace's own
status as text; `is_open` is false once the process is over on its side (a
refunded return is over, though its commission may still be claimed).
`action` (`NONE`, `DECIDE`, `REPLY`, `RECOVER_COMMISSION`, indexed) and `due_at`
(nullable, indexed) are worked out when the row is stored, by the rules in
`app/services/after_sales.py`: they are what the queue sorts and filters by, so
they are stored, not derived on every read. `order_external_id` (indexed) names
the order by the marketplace's id and is deliberately not a foreign key, like
`message_threads.order_external_id`: the order may not have been imported. The
API joins to `orders` on `(source, external_id)`. `reason` is the marketplace's
reason code, `summary` what the case is about (the goods returned, or the
buyer's own words) and `detail` the buyer's comment or, for a claim, what it asks
for; both are cut to 500 characters. `reference_number` is the number Allegro
prints on a claim.

These columns hold buyers' personal data: names, addresses, phone numbers.
It is never written to logs; mapping problems are logged by field name only.

All timestamps are stored in UTC. SQLite keeps no zone and returns them naive;
PostgreSQL returns them in the connection's time zone (on a Polish Windows
install, Europe/Warsaw). The API converts both to UTC on the way out, and code
comparing a stored timestamp must normalise the same way rather than assume
either form.

`order_status_history` matches the target: `order_id`, `from_status`,
`to_status`, `changed_at`, plus `changed_by_user_id`, a nullable reference to
`users` that becomes null if the account is deleted, so the history outlives
the user. Entries made before logins existed have no author.

`integration_credentials` is not in the target table above; it is the first
piece of `integration`. Allegro rotates its refresh token on every use, so
the latest token has to be kept between runs:

| Column | Meaning |
| --- | --- |
| `provider` | primary key, e.g. `ALLEGRO`; an `ERLI` row holds Erli's sync point, with an empty `refresh_token` and the API key's fingerprint (Erli's key does not rotate and is never stored) |
| `refresh_token` | the most recently issued refresh token |
| `token_issued_at` | when that token was issued (a rotation or a connection), so the status page can say when it lapses; null for a row with no token, such as Erli's. The migration filled existing rows from `updated_at`, a slight overestimate |
| `seed_fingerprint` | SHA-256 of the `.env` token the chain started from; a different `.env` token means a fresh authorization |
| `last_import_at`, `last_import_created`, `last_import_updated`, `last_import_error` | how the last import ended, whoever ran it: when it finished, how many orders it created and updated, or the error if it failed (then the counts are null). Cleared when an account is connected |
| `last_synced_at` | where the next import resumes: when the last one that fetched everything started, less five minutes; null until one has, and reset by a re-authorization, since another seller account has another order history |
| `account_login` | the connected seller's login, read once when the account is connected; only a label |
| `updated_at` | last rotation |

`app_settings` holds settings an operator changes in the interface, one row
per key: `key` (primary key), `value` (text), `updated_at`,
`updated_by_user_id` (nullable, `SET NULL` when the account goes). The only
key so far is `safe_mode` (`on` or `off`); no row means on.

`marketplace_writes` records every change Anvero made, or would have made, on
a marketplace, and is never updated: `id`, `created_at` (indexed), `source`,
`order_id` (nullable, indexed, `SET NULL` if the order is deleted: what was
sent stays sent), `action` (e.g. `fulfillment_status`), `payload` (the JSON,
as text), `outcome` (`DRY_RUN`, `SENT` or `FAILED`), `detail` (the
marketplace's answer or the error, up to 2000 characters), `user_id`
(nullable).

`shipping_labels`: shipments bought through Wysyłam z Allegro. Kept apart
from `order_shipments`, which an import replaces, because Allegro's
shipment-management ids are needed to print the label again or cancel it.
`id`, `order_id` (indexed, deleted with the order), `created_at`,
`created_by_user_id` (nullable, `SET NULL`), `command_id` (unique: the id
Anvero gave the create command), `shipment_id` (Allegro's, once it exists),
`status` (`PENDING`, `CREATED`, `FAILED`, `CANCELLED`, stored as text),
`delivery_method_id`, `carrier_id`, `waybill`, `length_cm`, `width_cm`,
`height_cm` (numeric 8,1), `weight_kg` (numeric 8,3), `error`, `printed_at`
(when its PDF was last fetched; null puts it on the "to print" list),
`pickup_id` (indexed, the courier ordered for it, `SET NULL`). The waybill
also goes onto the order as an `order_shipments` row added in Anvero.

`courier_pickups`: couriers ordered through Wysyłam z Allegro. `id`,
`created_at`, `created_by_user_id` (nullable, `SET NULL`), `command_id`
(unique), `pickup_id` (Allegro's), `status` (`PENDING`, `ORDERED`, `FAILED`,
as text), `carrier_id`, `ready_date` (a date), `proposal_id` and
`proposal_label` (the slot chosen, as its id and as it was shown), `error`.
Its parcels are the `shipping_labels` pointing at it; a refused pickup lets
go of them.

`app_settings` also holds `shipping_sender` and `shipping_default_package`,
each a JSON object (`API.md`, "Labels through Wysyłam z Allegro").

`integration_settings` holds the application's own credentials when they were
entered in Settings, and are then used instead of the `ALLEGRO_*` variables:
`provider` (primary key), `client_id`, `client_secret` (plain text, never
returned by the API), `user_agent`, `environment` (`sandbox` or `production`),
`updated_at`.

The rule above about credentials is read as "never committed to Git and never
logged": the token lives only in the local, git-ignored database file, as it
already did in the git-ignored `.env`.
