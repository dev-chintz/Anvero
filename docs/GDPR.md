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
| The non-invoiced sales record: the buyer's name and own address, copied per sale and correction | `non_invoiced_ledger` | the record poz. 41 requires (tax duty) | 5 years after the year its tax was due, counted from the row's own date; not erased on the buyer's request |
| Operators' e-mails and password hashes | `users` | logging in | while the account exists |

Buyers' personal data is never written to the application log (`DATABASE.md`).
The buyer's personal identity number, which Allegro also offers, is not stored at
all (`INTEGRATIONS.md`). The buyer's own address is, since 2026-09-30, as an
address of type `BUYER`: the non-invoiced sales record must show it
(`NON_INVOICED_SALES.md`); it is kept and erased with the order.

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

The non-invoiced sales record (`NON_INVOICED_SALES.md`) is erased by the same run
and for the same period, counted from each row's own date (a sale's is its
payment's, which may fall in the year after the order's): its buyer fields and
any override's note are emptied, while the amount, date, order, payment trace
and category stay, so past totals still add up.

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
  their rows in the non-invoiced sales record, message threads with every
  message, after-sales cases. Hand the file over,
  then delete it.
- **Erasure (art. 17).** `scripts/anonymize_person.py --login LOGIN` shows what it
  would erase; with `--apply` it erases it, with the functions the retention
  run uses. An order still inside its tax period keeps a company invoice's
  name, tax id and address, which the law requires kept (art. 17(3)(b)); the
  retention run erases those once the period is over. The non-invoiced sales
  record's copy of the buyer (name and address, per sale) is kept the same way
  and for the same reason: it is the record the tax law requires for the sale,
  so the script leaves it and says how many rows it kept; the retention run
  erases it after the period (`DECISIONS.md`). It cannot be undone.
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
- **The accountant**: the non-invoiced sales record's exports (CSV, Excel or PDF), with whichever columns
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
`?search=` is kept out of the logs: the backend's access log (uvicorn) and the web
container's (nginx) both write the path without its query, marking a dropped one `?...`
(`CHANGELOG.md`, 2026-09-17 for the backend and 2026-10-01 for nginx, whose default line had
written the whole request until then; `frontend/nginx.conf`). One line is still written in
full: nginx's error log, when it cannot reach the backend, names the request as it came,
query included, and that cannot be configured away. So the containers' logs need a size
limit as well (`DEPLOYMENT.md`, "The log").

## Who looked at what

Status changes, deletions, labels, couriers and marketplace writes record which
account made them. Reading is not recorded, deliberately: with a handful of
accounts on a private network, a log of every opened order would itself be one
more copy of who bought what. What is recorded is the one way data leaves in
bulk: a non-invoiced record export holding a column that names or reaches a person is
written to the application log with the period, the column keys, the row count
and the user's id (`API.md`). Revisit this if accounts outside the business are
ever given access.

## The security log

Since 2026-10-01 (`DECISIONS.md`, "The security log") the backend writes one line to its
log, on the logger `security`, for each of: a login that succeeded; a login refused, and why
(an account that does not exist, a wrong password, a switched-off account: the answer to the
person is the same for all three, the log is not); a request stopped by a rate limit, with the
route; and an account made or changed, by an administrator or by one of the scripts run on the
server (`create_user.py`, `reset_password.py`), what changed by name, a role and a state by
their new value, never a password.

- **What it holds about a person:** the *number* of an account, not the e-mail, and the address
  the request came from (the one the rate limit counts by, which the web container's proxy sets;
  uvicorn's and nginx's access logs already hold the address with every request). A change made by a script
  says `actor=console`.
- **What it never holds:** an e-mail or anything typed at the login form (for an account that
  does not exist that is whatever a stranger typed, a password typed into the wrong field
  included), a password, a buyer's data. Line breaks and control characters in a value are
  removed, so a request cannot forge a line.
- **Where and for how long:** the backend's standard output, so the container's log. Docker
  keeps the last 5 files of 10 MB of it (the limit in the compose file, on the NAS since
  2026-10-01; `DEPLOYMENT.md`, "The log"), so a line lasts until about 50 MB of newer ones have
  been written, which is a matter of weeks or months, not of a stated period. Nothing in the
  application erases it.
- **Basis:** the security of the application, art. 6(1)(f), as for the accounts in the register.
- **Not logged:** a token that was refused (an expired one is every morning's), a request a
  permission refused, and what was read. See the paragraph above on reading.

## The GDPR tab

Help → RODO (`/help?tab=gdpr`; `frontend/src/pages/help/GdprTab.tsx`, text in
`frontend/src/guide/gdpr.ts`; added 2026-10-01) puts this document in front of the
team and drafts the two texts the owner has to produce. Any logged-in account may
open it. It opens with the warning that it describes what the application does and
gives drafts to check, and is not legal advice (`DECISIONS.md`, "The in-app guide and
the GDPR tab").

- **The controller.** Who the data controller is: name, address, tax id, an e-mail for
  data matters, a phone, and how to reach a data protection officer if one was
  appointed. An administrator enters it in Settings (the card at the foot of the
  Settings page); it is one row of `app_settings` (`API.md`, "GDPR"; `DATABASE.md`).
  The tab says which of name, address and e-mail are still missing, and shows an
  administrator where to fill them in. The texts below show a visible
  `[uzupełnij: ...]` gap where a detail is missing, never a blank.
- **The notice to buyers** (art. 13 and 14), ready to paste into a shop's description
  on Allegro or Erli, or a sheet in the parcel: "Kopiuj tekst" copies it as plain text
  with the lists as dashes. It is built from the controller and from the retention
  periods, which the backend gives as the erasure uses them (`app/services/retention.py`),
  so it cannot name a period the application does not apply. It says the marketplace is
  a controller in its own right (the data comes from there, so art. 14 applies as well
  as art. 13).
- **The register of processing activities** (art. 30(1)): a row for each of orders and
  shipping, tax and accounting records, buyers' messages, returns, claims and disputes,
  the record of what was sent to marketplaces and carriers, user accounts, and backups,
  each with its purpose and legal basis, the people and the data concerned, recipients,
  transfers and retention. It prints on its own.
- **For the team**: what is held and for how long (the table at the top of this
  document, with the periods in force), who the data goes to, the steps for answering a
  request with the scripts to run (`export_person.py`, `anonymize_person.py`), what to do
  after a breach (the supervisory authority within 72 hours, art. 33; the people
  concerned when the risk is high, art. 34), the security measures, and "Do ustalenia z
  prawnikiem", the list below of what only the owner can settle.

The notice and the register are in Polish whatever language the interface is in: they
are for Polish buyers and the Polish authority. The team's part is in both languages.
The text is code and follows this document by hand; its tests hold it to what the code
does (the periods, the script names, the 72 hours and the month), not to the law.
What the tab cannot know, it lists as the owner's to settle (below).

## For the owner, outside the code

- The register of processing activities (art. 30), with the legal bases above:
  the contract (art. 6(1)(b)) and the tax duty (art. 6(1)(c)). A draft is in Help →
  RODO, to be checked; whether the accountant is a controller or a processor, and the
  basis for the backup copy leaving the EEA, are marked there for a lawyer.
- The information given to buyers (art. 13/14): the shop's privacy notice on
  each marketplace names the owner, the purposes, the periods above and the
  recipients, and that an erasure request leaves the tax records (a company
  invoice, the non-invoiced sales record) until their period is over. A draft is
  in Help → RODO; putting it on each marketplace is the owner's.
- Data processing agreements where one is needed (the accountant, if they act
  on the owner's behalf; Google for the backup copy); the carriers and
  marketplaces act as controllers under their own terms.
- A procedure for a breach: the supervisory authority (UODO) within 72 hours of
  learning of it, the buyers too when the risk is high. The steps are in Help →
  RODO; the register of breaches (art. 33(5)) and of requests is kept outside
  Anvero, and Anvero stores neither.
- Who has access to the NAS, its backup folder, the VPN and the password
  manager, and removing it when someone leaves.
- Deciding whether "until about 50 MB of newer lines" is a short enough time to keep the numbers
  of operators' accounts and their addresses in the container's log, or whether the register
  needs a stated period and a smaller limit (`DEPLOYMENT.md`, "The log").
