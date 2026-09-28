# GDPR (RODO)

What Anvero holds about people, for how long, and how a request is answered.
Not legal advice: it describes what the code does, so the owner (the data
controller) can settle the rest with an accountant, a lawyer or a data
protection officer. Decided on 2026-09-28 (`DECISIONS.md`, "Retention periods
and erasure").

## What is held, and why

| Data | Where | Why | Kept |
| --- | --- | --- | --- |
| Buyer's login, e-mail, name, company, phone | `orders` | fulfilling the sale (contract) | 5 years after the year its tax was due |
| Delivery, invoice and pickup-point addresses, tax id | `order_addresses` | shipping; invoicing (tax duty) | as the order |
| The buyer's message at checkout, the marketplace note, the operator's own note | `orders` | fulfilling the sale | as the order |
| Message Center threads: login and every message's text | `message_threads`, `messages` | answering the buyer | 2 years after the last message |
| Returns, claims, disputes: login, e-mail, the buyer's own words | `after_sales_cases` | handling the claim (consumer law) | 2 years after it was opened, once closed |
| What Anvero sent to a marketplace or InPost (a label's recipient, a reply's text) | `marketplace_writes` | a record of what was sent | 2 years, or with its order |
| Operators' e-mails and password hashes | `users` | logging in | while the account exists |

Buyers' personal data is never written to the application log (`DATABASE.md`).
The buyer's own address and personal identity number, which Allegro also offers,
are not stored at all (`INTEGRATIONS.md`).

## Retention: erased by itself

Every day the backend erases what is past its period (`app/services/retention.py`,
`run_retention_daily`), independently of the import schedule, so switching imports
off does not stop it. Nothing is deleted: an order keeps its number, dates,
status, amounts, items, payment and delivery method, pickup point, delivery
country and tracking numbers, so figures and reports over past years still add
up. The fields naming, reaching or quoting a person are emptied and
`anonymized_at` is set; the order's page then says so. An import does not touch
an anonymized order or case again, so the marketplace still having the data does
not bring it back. A message thread is the one exception: if the buyer writes
again, that is a new contact, kept for two years from then, while the old
messages stay erased.

**The order period, worked out:** tax records are kept five years from the end of
the year in which the tax was due (Ordynacja podatkowa, art. 86 and 70). Income
tax for a year is settled in the next one, so an order placed in 2020 is kept
through 2026 and anonymized on 1 January 2027 (Polish time). This is one year
more than "five years from the order's year", on purpose: the shorter reading
would erase December's orders while their tax could still be examined.

To see what the next run will erase, or to run it now:

```powershell
# backend/
.\.venv\Scripts\python.exe scripts\apply_retention.py
.\.venv\Scripts\python.exe scripts\apply_retention.py --apply
```

## Answering a request

A request comes from a buyer, usually through the marketplace. Identify them by
their marketplace login (Allegro's e-mails are per order and masked), or by
e-mail. Answer within one month. On the NAS the scripts run in the `backend`
container's terminal (`DEPLOYMENT.md`), as `python scripts/...`.

- **Access or portability (art. 15, 20).** `scripts/export_person.py --login LOGIN
  --out buyer.json` writes everything held about them as JSON: orders with
  addresses, items, shipments and labels, what was sent about those orders,
  message threads with every message, after-sales cases. Hand the file over,
  then delete it.
- **Erasure (art. 17).** `scripts/anonymize_person.py --login LOGIN` shows what it
  would erase; with `--apply` it erases it, with the functions the retention
  run uses. An order still inside its tax period keeps a company invoice's
  name, tax id and address, which the law requires kept (art. 17(3)(b)); the
  retention run erases those once the period is over. It cannot be undone.
- **Correction (art. 16).** The data comes from the marketplace, and an import
  replaces it: correct it there. The operator's own note is edited on the order.
- **Objection or restriction (art. 21, 18).** Nothing here markets to anyone, so
  an objection has little to reach; a restriction is honoured by not handling
  the order, and recorded outside Anvero.

Keep a note of each request and when it was answered (the date and the kind of
request, not the data): the register is the owner's, outside Anvero.

## Who the data goes to

- **Allegro and Erli**: where the orders come from; each is a controller in its
  own right. Anvero sends back statuses, tracking numbers and replies.
- **InPost** (ShipX): a parcel locker shipment carries the recipient's name,
  e-mail and phone and the locker. **Wysyłam z Allegro** carriers: the
  recipient's name, address, e-mail and phone.
- **The accountant**: the non-invoiced sales report's CSV, with whichever columns
  the owner chose (`DECISIONS.md`, "Export columns, chosen by the owner").
- **Google Drive**: the encrypted off-site copy of the nightly dump
  (`DEVELOPMENT.md`).
- **Tailscale**: carries the traffic between a laptop and the NAS, encrypted
  end to end; it does not see the pages.

## Secrets

Allegro's refresh token and client secret and InPost's token sit in the
database, so every dump holds them beside the personal data, and with them the
marketplace accounts can be reached. With `SECRETS_KEY` set they are stored
encrypted (`app/core/secrets.py`); without it, in plain text as before, so a
machine that sets nothing keeps working. Setting it up: `DEPLOYMENT.md`,
"Encrypting the integration secrets", and for a laptop the same key in
`backend/.env`. Every backend sharing a database needs the same key, and a copy
belongs in the password manager: a backend without it cannot read the secrets,
and a lost key means authorizing Allegro and entering the secrets again. Erli's
key is never stored.

## Backups

The nightly dump on the NAS (`anvero-backup`, 7 daily, 4 weekly, 3 monthly)
holds the personal data as it was that night, readable by whoever can read that
folder; the copy on Google Drive is encrypted. Erasure does not reach a dump
already made: it ages out with the rotation, within about three months. After
restoring a dump, run `apply_retention.py --apply` and the erasures answered
since the dump was made again, which is what the register above is for.

## Addresses and the browser's history

A search typed in the order list or the to-make list is often a buyer's name,
login or e-mail. It is kept in the page's history entry rather than in the
address (`frontend/src/hooks/useListSearch.ts`), so it does not stay in the
browser's history and suggestions; the other filters stay in the address, to be
shared. The Inbox's link to an order passes the order's number the same way. An
old address with `?search=` still works and loses it at once. The API's own
`?search=` never reaches a log: the access log drops query strings (`CHANGELOG.md`,
2026-09-17).

## Who looked at what

Status changes, deletions, labels, couriers and marketplace writes record which
account made them. Reading is not recorded, deliberately: with a handful of
accounts on a private network, a log of every opened order would itself be one
more copy of who bought what. What is recorded is the one way data leaves in
bulk: a sales report export holding a column that names or reaches a person is
written to the application log with the period, the column keys, the row count
and the user's id (`API.md`). Revisit this if accounts outside the business are
ever given access.

## For the owner, outside the code

- The register of processing activities (art. 30), with the legal bases above:
  the contract (art. 6(1)(b)) and the tax duty (art. 6(1)(c)).
- The information given to buyers (art. 13/14): the shop's privacy notice on
  each marketplace names the owner, the purposes, the periods above and the
  recipients.
- Data processing agreements where one is needed (the accountant, if they act
  on the owner's behalf; Google for the backup copy); the carriers and
  marketplaces act as controllers under their own terms.
- A procedure for a breach: the supervisory authority (UODO) within 72 hours of
  learning of it, the buyers too when the risk is high.
- Who has access to the NAS, its backup folder, the VPN and the password
  manager, and removing it when someone leaves.
