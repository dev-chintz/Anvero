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

Migrations currently create `users`, `user_permissions`, `orders`, `order_items`,
`order_addresses`, `order_shipments`, `billing_entries`,
`order_status_history`, `integration_credentials`, `message_threads`,
`messages`, `after_sales_cases`, `payouts`, `order_item_packing`,
`app_updates`, `order_payments`, `payment_operations`, `product_settings`,
`non_invoiced_ledger`, `catalog_items`, `catalog_images` and `catalog_listings`.
`integration` and `customer` are still targets.

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
| `delivery_method_id` | the marketplace's id of that method (Allegro's `delivery.method.id`), which tells a courier from personal collection where the name may not. Added by `c7e2a9f4d318` |
| `delivery_smart` | an Allegro Smart delivery (the buyer's subscription covers it); not null, default false |
| `pickup_point_id`, `pickup_point_name` | the parcel locker or pickup point, if any |
| `payment_type` | `ONLINE`, `BANK_TRANSFER`, `CASH_ON_DELIVERY`, `DEFERRED` or `OTHER` |
| `payment_provider` | the payment operator as the marketplace names it, e.g. `P24` |
| `paid_amount`, `paid_at` | null means unknown; `0.00` means known to be unpaid |
| `payment_id` | the marketplace's id of the payment (Allegro's `payment.id`), indexed: what `payment_operations` names it by, tracing the money to the order (`NON_INVOICED_SALES.md`). Null for Erli and for orders imported before it was kept, which an import reads again by id (`INTEGRATIONS.md`). Added by `c7e2a9f4d318` |
| `invoice_required` | the buyer asked for an invoice |
| `invoice_is_company`, `invoice_vat_payer_status` | whether the invoice data names a company (`true`) or a private person (`false`), as the marketplace says it (Allegro: `invoice.address.company` present or null), null when the order has no invoice data; and the company's own declaration, `ACTIVE`, `NON_ACTIVE` or `NOT_APPLICABLE`. Added by `c7e2a9f4d318` |
| `deleted_at`, `deleted_by_user_id` | set when an operator deletes the order from the list (`DELETE /orders/{id}`); the row is kept, every list, figure and queue leaves it out, and an import does not touch it. Null while the order is in use. `deleted_by_user_id` is `SET NULL` when the account goes. Added by `b8e3d5a7c246` |
| `anonymized_at` | set when the buyer's personal data on the order was erased (`docs/GDPR.md`): by the daily retention run, or at the buyer's request. `customer_email` is then `''` (it is required), the other buyer fields, notes and address fields are null except `country_code`, and a company invoice address may keep its name, tax id and address while the tax period runs. An import does not touch such an order. Added by `a7d4e2c9f136` |
| `starred`, `flagged` | the operator's own marks for finding an order again, both `false` for every order until set (`PATCH /orders/{id}/marks`); Anvero's alone, no marketplace has them and an import never touches them. Added by `a4d7c1e9b352` |
| `internal_note` | the operator's own note on the order, written in Anvero (`PATCH /orders/{id}/note`) and never sent anywhere; unlike `seller_note` no marketplace has it and an import does not touch it. Null when there is none. Added by `b6e2f9a1c473` |
| `status_changed_at` | when the status last changed, by an operator or an import (set wherever a row is added to `order_status_history`); null for an order that has kept its first status, which the list then counts from `ordered_at`. Filled from the history's latest change for existing orders. Added by `a4d7c1e9b352` |

`payment_type` is a plain string column validated by the application, not a
database enum type: the list grows with each marketplace, and a new value in a
PostgreSQL enum type needs its own migration.

`order_items` (matches the target `order_item`): `order_id`, `position` (the
marketplace's line order), `external_id`, `offer_id`, `sku` (the seller's own
product code, if the listing has one), `name`, `quantity`, `unit_price` (per
unit, in the order's currency, after discounts), `image_url` (the offer's
picture, fetched from Allegro's own product-offer resource at import time;
best-effort, so a deleted offer or a missing scope leaves it null), `tax_rate`,
`tax_subject`, `tax_exemption` (the tax the offer declares, Allegro's `lineItems[].tax`, as
text; null when it declares none; added by `c7e2a9f4d318`).

`order_payments` (added by `c7e2a9f4d318`): the payments for an order beyond its main one,
owned by the marketplace like the items (an import replaces them). `order_id`, `position`,
`kind` (`SURCHARGE`, a later additional payment, or `CASH_ON_DELIVERY`, cash the carrier
collected), `external_id` (the payment's id), `payment_type` and `provider` (a surcharge's),
`paid_amount`, `currency`, `paid_at`. What tells whether an order was paid in full and without
cash (`NON_INVOICED_SALES.md`).

`order_addresses` (matches the target `address`): `order_id`, `type`
(`DELIVERY`, `INVOICE`, `PICKUP_POINT` or `BUYER`, the buyer's own address on their
marketplace account, which the non-invoiced sales record must show and the recipient's may
differ from; `BUYER` needed no migration, the column being a plain string; at most one of each per order,
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
to an order by `(source, order_external_id)`. `is_settlement` (added by
`d8b3f1a6c925`, false by default) marks the marketplace taking its fees out of
the proceeds (Allegro's `PAD`, Erli's `plusPayments` kinds such as `PAYM`):
the fees paid, which the Finance page leaves out of the fees. For Erli,
`offer_id` holds Erli's item id (`productId`), which is the item's
`external_id`.

`payouts`: money a marketplace sent to the seller's bank account, one row per
payout, never changed once stored. `source`, `external_id` (unique together),
`paid_at` (indexed), `amount`, `currency`, `operator` (e.g. `PAYU`). Read from
Erli and Allegro since 2026-09-27 (Allegro's from `/payments/payment-operations`; a cancelled payout is a second row, `<id>:cancel`, negative). Added by `d8b3f1a6c925`.

`payment_operations` (added by `c7e2a9f4d318`): every operation on the seller's wallets at the
payment operators that Allegro's `/payments/payment-operations` lists in its `INCOME`, `REFUND`
and `OUTCOME` groups: a buyer's payment (`CONTRIBUTION`), a surcharge, a refund, a payout, a
deduction. What ties the money on the bank account to the orders it came from
(`NON_INVOICED_SALES.md`). Allegro gives an operation no id, so a row is kept by `fingerprint`
(a SHA-256 of its type, group, time, wallet, balance after it, value and what it concerns),
unique with `source`, and never changed once stored. `type`, `group`, `occurred_at` (indexed),
`amount` (signed: into the wallet positive), `currency`, `wallet_operator` (`PAYU`, `P24`,
`AF`, ...), `wallet_type` (`AVAILABLE` or `WAITING`), `wallet_balance`, `payment_id` (indexed;
the order's `payment_id`), `payout_id` (indexed), `surcharge_id`, `marketplace_id`. No buyer's
data: the participant's login Allegro sends is not kept, the payment id finds the order.

`product_settings` (added by `e3b7a1c9d524`): what the owner has said about one product, kept by
`(source, offer_id)` (unique together; `offer_id` as `order_items.offer_id` holds it). So far only
`excluded_from_exemption` (not null, default false): the goods are on the list of § 4 of the
regulation and can never use the poz. 41 exemption (`NON_INVOICED_SALES.md`, 4h). No row means
not excluded. `updated_at`, `updated_by_user_id` (nullable, `SET NULL`). No API or screen yet.

`non_invoiced_ledger` (added by `e3b7a1c9d524`): the non-invoiced sales record, one row per money
event (`NON_INVOICED_SALES.md`, 4b), written after every import
(`app/services/non_invoiced/ledger.py`). Not a view over the orders: what the record must show is
copied when the row is written and never changed after.

| Column | Meaning |
| --- | --- |
| `kind` | `SALE` (money received: an order's main payment, or one surcharge) or `CORRECTION` (a refund, a refund's cancelling, or a locked sale moved in or out of the report) |
| `event_key` | what makes the event one, unique with `source`: `ORDER:<order's marketplace id>` for the main payment, `SURCHARGE:<surcharge id>`, `OPERATION:<fingerprint>` for a refund's payment operation, `RECLASSIFIED:<sale row id>:<n>` for the n-th move of a locked sale. Writing again finds the row instead of adding one |
| `entry_at`, `entry_date` | when (UTC), and that moment's day in `BUSINESS_TIMEZONE` (indexed): a sale's payment time, a refund operation's time, or when a reclassification was found |
| `source`, `order_id`, `order_external_id`, `order_number` | the order; `order_id` is `SET NULL` if the order row ever goes, the rest stays |
| `corrects_entry_id` | a correction's sale (indexed, `SET NULL`) |
| `amount`, `currency` | gross and signed: a sale positive, money returned negative |
| `buyer_first_name`, `buyer_last_name`, `buyer_street`, `buyer_postal_code`, `buyer_city`, `buyer_country_code` | the buyer and their own (`BUYER`) address, copied from the order when the row is written (a correction copies its sale's); erased by the retention run only (`GDPR.md`) |
| `anonymized_at` | set when retention erased the buyer fields and the override's note |
| `payment_type`, `payment_operator` | as the order (or the surcharge) had them when written |
| `payment_id` | the marketplace's payment id, or the surcharge's (indexed) |
| `operation_fingerprint` | the `payment_operations` row matched: the `CONTRIBUTION` or `SURCHARGE`, for a refund its own |
| `payout_id`, `payout_at`, `payout_link` | the payout the money most likely went out in, and how it was found: `FIRST_AFTER` (4d) |
| `category`, `reason`, `ruleset` | the classifier's result; for a correction, the category whose total it adjusts |
| `override_category`, `override_note`, `overridden_by_user_id`, `overridden_at` | a person's category, with the written reason, beside the automatic result; never on a company's sale or a locked row |
| `locked_at` | set when a report holding the row is handed over (indexed); the row never changes after |
| `created_at`, `updated_at` | |

`non_invoiced_reports` and `non_invoiced_report_rows` (added by `b4d2f8a61c37`): the reports
of the record handed over to the accountant (`NON_INVOICED_SALES.md`, 4c). A report: `id` (uuid),
`date_from` (indexed), `date_to`, `handed_over_at`, `handed_over_by_user_id` (nullable, `SET
NULL`), `ruleset` (the classifier's then), `total` and `currency` (what it listed), `row_count`,
`created_at`. Its rows: `(report_id, position)` the primary key (`position` its Lp., `CASCADE` with
the report), `entry_id` the ledger row (indexed, `SET NULL`). The ledger rows a report lists are
locked (`locked_at`) when it is handed over, so downloading it again gives the same file.

`order_item_packing` (added by `b4e6f9c2a831`): how many of one order line an operator has
physically gathered into the parcel for that order - their own use, kept by `(order_id,
position)` (unique together), not `order_items.id`: an import replaces every item row of an
order wholesale (`app/services/order_details.py`), which would otherwise wipe this on the next
scheduled sync. `packed_quantity` (default 0), `updated_by_user_id` (nullable, `SET NULL` on
delete). Cleared whenever the order's `status` reaches `SHIPPED`, `DELIVERED` or `CANCELLED`
(`OrderRepository.update_status`) - the one chokepoint both a manual status change and an
import's own auto-follow go through. Never sent to a marketplace.

`sales_report_overrides` (added by `a2f4c8e1b937`) was dropped by `c6e1a9d4f028` (2026-10-01,
empty), with the report it served (`NON_INVOICED_SALES.md`, stage 8).

`catalog_items`, `catalog_images` and `catalog_listings` (added by `d5f2a8c1e947`): the assortment
(`CATALOG.md`). Allegro is where the assortment lives, so `catalog_items` is one Allegro offer:
`(source, offer_id)` unique together (`source` is always `ALLEGRO`; `offer_id` as `order_items.offer_id`
holds it), `name`, `sku` (Allegro's external id; indexed), `price`, `currency`, `stock`, `status`
(`ACTIVE`, `INACTIVE`, `ACTIVATING`), `category_id` (the leaf), `category_path` (JSON, a list of
`{"id", "name"}` from the top, the leaf last) and `category_ids` (the same ids as `|1|23|456|`, indexed, so
"everything under 23" is one `LIKE` on any database), `last_seen_at`, `gone_at` (indexed; set when a sync no
longer finds the offer, cleared if it comes back; the row and its pictures are kept), `created_at`,
`updated_at`. Never edited in Anvero.

`catalog_images`: one picture of an offer, `item_id` (`CASCADE`), `position` (the offer's order; unique with
`item_id`; the first is the cover), `url` (the address on Allegro, always kept), and the copy on this
server: `file_name` (`<sha256 of the bytes>.<jpg|png|webp|gif>`, the file under `CATALOG_IMAGES_DIR`; null
until downloaded; the same picture of two offers is one file), `content_type`, `byte_size`, `fetched_at`,
`fetch_error` (why the last download failed; cleared by the next that succeeds). A changed address on
Allegro clears the copy's columns.

`catalog_listings`: the same product on Erli, `item_id` (`CASCADE`), `source` (`ERLI`; unique with `item_id`),
`external_id` (Erli's `externalId`, as `order_items.offer_id` holds it for Erli), `matched_by`
(`EXTERNAL_REFERENCE`, `EXTERNAL_ID` or `SKU`), `price`, `currency`, `stock`, `status` (`ACTIVE`, `INACTIVE`,
`ARCHIVED`), `category_path` (Erli's own, as above), `category_match` (`SAME`, `DIFFERENT`, `UNKNOWN`),
`seen_at`. Replaced by every sync that reads Erli; a product Erli no longer has loses its row.

How the last sync went is the `catalog_sync` row of `app_settings` (JSON: `at`, `error`, `items`,
`erli_error`, `erli_unmatched`).

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
thread later, and the inbox excludes it by default. `anonymized_at` (nullable)
is set when the retention run erased the login and every message's text
(`''`, the column being required); new activity from the buyer clears it, the
old messages staying erased.

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
prints on a claim. `anonymized_at` (nullable) is set when the retention run
erased `buyer_login`, `buyer_email`, `summary` and `detail`; a sync no longer
touches the row.

These columns hold buyers' personal data: names, addresses, phone numbers.
It is never written to logs; mapping problems are logged by field name only.
How long each is kept, and how it is erased, is in `docs/GDPR.md`.

All timestamps are stored in UTC. SQLite keeps no zone and returns them naive;
PostgreSQL returns them in the connection's time zone (on a Polish Windows
install, Europe/Warsaw). The API converts both to UTC on the way out, and code
comparing a stored timestamp must normalise the same way rather than assume
either form.

`order_status_history` matches the target: `order_id`, `from_status`,
`to_status`, `changed_at`, plus `changed_by_user_id`, a nullable reference to
`users` that becomes null if the account is deleted, so the history outlives
the user. Entries made before logins existed have no author.

`users.token_version` (added by `a9c4e7d2b815`) is a counter, 0 to begin with,
written into every login token and compared on every request. A new password
raises it, so the tokens issued before stop working instead of living out
their eight hours (`API.md`, `POST /auth/login`). Tokens from before the
column existed carry no version and count as 0, so adding it logged nobody out.

`users.role` (added by `c2a6f9e3b184`) is `admin` or `user`, a plain string
column like `payment_type` rather than a database enum, for the same reason:
what a role can do is decided by the application, not by a fixed set the
database enforces. An admin needs no rows in `user_permissions` below: it
passes every check outright. The migration set every account that already
existed to `admin`, since none of them had ever needed to be anything less;
`UserCreate.role` defaults to `admin` too (`API.md`, "Users, roles and
permissions"), so every caller that predates roles - `scripts/create_user.py`
and the whole test suite - keeps the access it always had unless it asks
for `user` explicitly, which only the Users tab in Settings does.

`user_permissions` (added by `c2a6f9e3b184`): one row per `(user_id, area)`
a `user` account has been granted, unique together. `user_id` (`ON DELETE
CASCADE`, indexed): a deleted account's grants go with it, unlike the
nullable, `SET NULL` foreign keys elsewhere in this file, since a permission
row means nothing without the account it grants access to. `area` and
`level` are plain string columns, not database enums, for the same reason as
`role`: the list of areas is expected to grow as the application does, and a
native enum would need its own migration for every new value. `area` is one
of `orders`, `messages`, `after_sales`, `labels`, `finance`, `integrations`;
`level` is `view` or `manage`. Replacing a user's whole grant list
(`UserRepository.replace_permissions`) clears the existing rows and flushes
before appending the new ones - appending in the same flush as the clear
queues the inserts before the deletes, and a kept area collides with itself
on `(user_id, area)` before the old row is gone.

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

`app_updates` is the history of the version the backend runs (Settings,
Updates): `from_commit` and `to_commit` (full commits; from is null for the
first version the database saw), `started_at`, `started_by_user_id` (null
outside Settings, or once the account is deleted), `finished_at` and `result`
(`ok` or `failed`, both null while under way), `via` (`settings` for the
button, `outside` for a version the backend found itself on at start) and
`detail` (why it failed). A row from the button is written when it is pressed
and closed by the new backend on its first start.

`app_settings` holds settings an operator changes in the interface, one row
per key: `key` (primary key), `value` (text), `updated_at`,
`updated_by_user_id` (nullable, `SET NULL` when the account goes). The only
key so far is `safe_mode` (`on` or `off`); no row means on.

`marketplace_writes` records every change Anvero made, or would have made, on
a marketplace, and is never otherwise updated: `id`, `created_at` (indexed), `source`,
`order_id` (nullable, indexed, `SET NULL` if the order is deleted: what was
sent stays sent), `action` (e.g. `fulfillment_status`), `payload` (the JSON,
as text), `outcome` (`DRY_RUN`, `SENT` or `FAILED`), `detail` (the
marketplace's answer or the error, up to 2000 characters), `user_id`
(nullable), `anonymized_at` (nullable: set when the retention run replaced
`payload` with `{}` and emptied `detail`, since a label's payload holds the
recipient's address and a reply's its text; what was done, when and by whom
stays).

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

`inpost_shipments`: parcel locker shipments made through InPost's ShipX API
(`INTEGRATIONS.md`, "InPost"). `id`, `order_id` (indexed, deleted with the order),
`created_at`, `created_by_user_id` (nullable, `SET NULL`), `inpost_id` (InPost's own
id, unique), `status` (InPost's word: `created`, `offer_selected`, `confirmed`,
`cancelled`, ..., stored as text), `tracking_number` (null until InPost has bought
the shipment), `target_point` (the locker), `template` (`small`, `medium`, `large`),
`reference`, `error` (the last cancel InPost refused), `printed_at` (when its label
was last fetched; null puts it on the "to print" list). The number also goes onto the
order as an `order_shipments` row added in Anvero.

`app_settings` also holds `inpost_api_token` (encrypted like the secrets below
when `SECRETS_KEY` is set), `inpost_organization_id`, `inpost_environment`
(`sandbox` by default), `inpost_default_template` and `retention_last_run` (the
day, in the business's time zone, the retention run last ran).

`courier_pickups`: couriers ordered through Wysyłam z Allegro. `id`,
`created_at`, `created_by_user_id` (nullable, `SET NULL`), `command_id`
(unique), `pickup_id` (Allegro's), `status` (`PENDING`, `ORDERED`, `FAILED`,
as text), `carrier_id`, `ready_date` (a date), `proposal_id` and
`proposal_label` (the slot chosen, as its id and as it was shown), `error`.
Its parcels are the `shipping_labels` pointing at it; a refused pickup lets
go of them.

`production_checks` (added by `c7a1e4d9b258`) holds the products on the to-make
list that have been made: `key` (the product's key on the list, `sku:...`,
`offer:...` or `name:...`; the primary key), `quantity` (how many the list asked for
when it was ticked), `checked_at` (indexed; ticks older than 90 days are deleted when
another is made) and `checked_by_user_id` (`SET NULL` when the account goes). A product
counts as made while the list asks for no more than `quantity`. It is by product, not
by order, because the list is.

`app_settings` also holds `shipping_sender` and `shipping_default_package`,
each a JSON object (`API.md`, "Labels through Wysyłam z Allegro").

`integration_settings` holds the application's own credentials when they were
entered in Integrations, and are then used instead of the `ALLEGRO_*` variables:
`provider` (primary key), `client_id`, `client_secret` (never returned by the
API), `user_agent`, `environment` (`sandbox` or `production`),
`updated_at`.

The rule above about credentials is read as "never committed to Git and never
logged": the token lives only in the database, as it already did in the
git-ignored `.env`. With `SECRETS_KEY` set, `integration_credentials.refresh_token`,
`integration_settings.client_secret` and `inpost_api_token` are stored encrypted
(Fernet, prefixed `enc:v1:`), so a backup of the database does not carry them
readable; without it they are plain text as before, and a value of either kind
reads the same (`app/core/secrets.py`, `docs/GDPR.md`, "Secrets").
