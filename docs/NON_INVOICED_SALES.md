# Non-invoiced sales (sprzedaż bezrachunkowa): design

A design, not yet built, for the record of mail-order sales exempt from the cash register and the
exports the accountant needs from it. Researched from scratch on 2026-09-30 (the law, the tax
authority's reading of it, Allegro's API) rather than from the report ported on 2026-09-27; how the
two differ is at the end. Nothing here is tax advice: the classification rules are to be confirmed
with the accountant, whose answers (2026-09-30) are section 3.

## 1. The law, as in force on 2026-09-30

**The act.** Rozporządzenie Ministra Finansów z dnia 17 grudnia 2024 r. w sprawie zwolnień z
obowiązku prowadzenia ewidencji sprzedaży przy zastosowaniu kas rejestrujących (Dz.U. 2024 poz.
1902), in force since 2025-01-01, amended by the regulation of 2026-03-27 (Dz.U. 2026 poz. 420,
from 2026-03-31; it changes only parking and coin-operated machines). Its exemptions hold "w danym
roku podatkowym, nie dłużej jednak niż do dnia 31 grudnia 2027 r." (§ 2 ust. 1): the rules may
change by 2028, so the classifier carries a rule-set version (section 4a).

Text read from the Sejm's ELI API (`api.sejm.gov.pl/eli/acts/DU/2024/1902/text.html` and
`.../DU/2026/420/text.pdf`), since ISAP's pages sit behind a CAPTCHA.

**Who needs a cash register at all.** Only sales to natural persons not running a business and to
flat-rate farmers (art. 111 ust. 1 of the VAT act). A sale to a business documented by an invoice
is outside the obligation, so it never needs an exemption.

**The exemption that matters: poz. 41 of the annex** (part II, "Sprzedaż dotycząca szczególnych
czynności"):

> Dostawa towarów w systemie wysyłkowym (pocztą lub przesyłkami kurierskimi), jeżeli dostawca
> towaru otrzyma w całości zapłatę za wykonaną czynność za pośrednictwem poczty, banku lub
> spółdzielczej kasy oszczędnościowo-kredytowej (odpowiednio na rachunek bankowy podatnika lub na
> rachunek podatnika w spółdzielczej kasie oszczędnościowo-kredytowej, której jest członkiem), a z
> ewidencji i dowodów dokumentujących zapłatę jednoznacznie wynika, jakiej konkretnie czynności
> dotyczyła i na czyją rzecz została dokonana (dane nabywcy, w tym jego adres)

It is judged per sale, with no turnover limit. The 20 000 zł limit (§ 3 ust. 1 pkt 1-2) and the
80% share rule (§ 3 ust. 1 pkt 3-4, which counts part I of the annex only) are different
exemptions and play no part here.

**Goods that can never use it (§ 4 ust. 1 pkt 1).** Among them: liquid gas, engine and vehicle
parts, computers, laptops, tablets and consoles, electronics (TV, radio, phones, smartwatches,
monitors, storage), optical goods, electric motors, photographic equipment, articles of precious
metals, data carriers, motor fuels, tobacco, alcohol over 1.2%, perfumes and eaux de toilette,
e-cigarettes and heated tobacco, some ethanol products, coal. The business's goods (ceramics,
candles, wood) are not on the list, but a product-level flag guards the day one is (section 4h).

**Payments through a payment operator.** The individual interpretation of 2025-06-05
(0112-KDIL3.4012.238.2025.1.MC), on an e-commerce seller paid by card, e-wallet and BLIK through a
payment service provider that sends aggregated transfers with a statement of the orders they cover,
answered that the exemption applies: "taka forma płatności, ponieważ dokonywana jest na konto
bankowe Wnioskodawcy, spełnia przesłankę do uznania, że została dokonana za pośrednictwem banku".
Earlier interpretations read PayU, Przelewy24 and PayPal the same way. Any part paid in cash loses
the exemption for that sale.

**Reporting.** Exempt sales without an invoice are entered in the VAT records in aggregate, split by
VAT rate, on an internal document marked `WEW` in JPK_V7 (commonly one per day, or one per month),
and the same daily totals feed the income records (KPiR or the ryczałt register). Anvero's
business is not a VAT payer (section 3), so for it only the record and its monthly total apply.

## 2. What Allegro tells us about an order

From Allegro's published OpenAPI specification (`developer.allegro.pl/swagger.yaml`, read
2026-09-30), `GET /order/checkout-forms/{id}` and `GET /payments/payment-operations`:

| Condition | Field |
| --- | --- |
| Business or private buyer | `invoice.address.company` ("Setting the value to null indicates a private purchase, while any other value indicates a corporate purchase"), `company.taxId`, `company.ids`, `company.vatPayerStatus` (`ACTIVE`, `NON_ACTIVE`, `NOT_APPLICABLE`) |
| A private buyer who wants an invoice | `invoice.required` with `invoice.address.naturalPerson` |
| How paid | `payment.type`: `ONLINE`, `WIRE_TRANSFER`, `CASH_ON_DELIVERY`, `SPLIT_PAYMENT`, `EXTENDED_TERM` |
| Through whom | `payment.provider`: `PAYU`, `P24`, `AF` (Allegro Finance), `OFFLINE`, `EPT` (Allegro Pay Business); `payment.features` has `ALLEGRO_PAY` |
| Paid in full | `payment.paidAmount` against `summary.totalToPay`; `surcharges[]` (later additional payments, same shape as `payment`); `codBookedPayments[]` for cash on delivery |
| When paid | `payment.finishedAt` |
| Shipped, not collected | `delivery.method`, `delivery.pickupPoint`, `delivery.address.countryCode`, `delivery.cancellation` |
| Buyer and address | `buyer` (`firstName`, `lastName`, `login`, `address`), `delivery.address` |
| VAT rate of an item | `lineItems[].tax.rate` (with `subject`, `exemption`), filled when the offer carries a tax setting |
| Status | `status`: `BOUGHT`, `FILLED_IN`, `READY_FOR_PROCESSING`, `CANCELLED` |
| Proof of payment | `payment.id` = the `CONTRIBUTION` operation's `payment.id` in `/payments/payment-operations` (with `participant.login`, the buyer); the `PAYOUT` operations are the transfers to the seller's bank account, per operator wallet (`wallet.paymentOperator`: `PAYU`, `P24`, `AF`, `AF_P24`, `AF_PAYU`) |
| Refunds | `GET /payments/refunds`, and the `REFUND` group of payment operations |

So every condition of poz. 41 can be checked automatically except the goods exclusion, which
Allegro cannot know. Erli follows the same logic; its equivalents (a business buyer, the payment
operator, payouts per order) are still to be checked against its API.

What Anvero's import keeps today: the payment type and provider, `paidAmount` and `finishedAt`, the
buyer, delivery and invoice addresses with a tax id, the delivery method and pickup point, and the
payouts. Not kept, and needed: `payment.id`, `surcharges`, `codBookedPayments`,
`lineItems[].tax`, `company.vatPayerStatus` and `company.ids`, and the `CONTRIBUTION` operations.

## 3. The accountant's answers (2026-09-30)

1. **Taxation:** the business is not a VAT payer (exempt by turnover, art. 113 of the VAT act).
   So no split by VAT rate and no `WEW` in JPK_V7 (a non-payer files no JPK_V7); the cash register
   rules apply all the same, so the poz. 41 record is still needed. Whether income is kept in KPiR
   or the ryczałt register was not asked and does not change this design.
2. **Which date puts a sale in a period:** the payment date (`payment.finishedAt`).
3. **VAT rate:** the standard rate; with no VAT charged, it matters only if the business ever
   becomes a VAT payer.
4. **Classification:** confirmed as proposed: private buyers, shipped and paid in full online
   through an operator, are exempt under poz. 41; the goods are not on the § 4 list; a sale
   invoiced to a private buyer stays out of the totals so it is not counted twice.
5. **Refunds:** a correction in the period the money was returned.
6. **The summary:** one total per month, gross.
7. **Formats:** CSV, Excel and PDF, all three.
8. **Columns:** by default only a running number (Lp.), the sale date, the buyer's first and last
   name, and the amount. Other columns Anvero knows about the sale may be added by choice.
9. **Sales abroad:** none.
10. **When:** a report for any date range, made by hand, the default being the whole previous
    month once it has ended.

## 4. The design

### a) The classifier

A pure function: an order's facts, its payment operations and the product settings in, one
category, a reason code and the rule-set version out. Deterministic, so it can be re-run on any
order and tested case by case without a database.

| Category | When | In the report |
| --- | --- | --- |
| `EXEMPT_MAIL_ORDER` (poz. 41) | a private buyer (`company` null); shipped by courier, post or to a pickup point; paid in full, with no cash part, through `PAYU`, `P24` or `AF` (`ONLINE`, `WIRE_TRANSFER`, `SPLIT_PAYMENT`); its `CONTRIBUTION` found; buyer name and address present; no excluded goods; no invoice issued | yes |
| `PRIVATE_INVOICED` | as above, but an invoice was issued to the private buyer | no: the invoice documents it; listed apart so it is not counted twice |
| `BUSINESS` | `company` present with a tax id | no: outside the cash register obligation |
| `NEEDS_REGISTER` | cash on delivery or any cash part, `OFFLINE`, personal collection, or goods on the § 4 list | no: raised as an alert, it should have gone through the register |
| `TO_REVIEW` | anything the rules cannot decide: missing buyer data or address, paid amount differing from the total, a surcharge not yet paid, no `CONTRIBUTION` found, a delivery abroad, `EXTENDED_TERM`, cancelled after payment | no, until a person decides |
| `NOT_A_SALE` | never paid, or cancelled before payment | no |

Every category carries a reason code (`E41_OK`, `B2B_TAX_ID`, `CASH_PART`, `NO_CONTRIBUTION`,
`FOREIGN_DELIVERY`, …) so that a row always says why it is where it is. A person can override any
category except `BUSINESS`, always with a written reason; the automatic result is kept beside the
override, never replaced.

### b) The ledger: its own table, append-only

Not a view over the orders: orders change (a buyer edits an address, a refund arrives, GDPR
anonymizes a buyer after the retention period), and a report already given to the accountant must
not change with them. One row per event, never rewritten once written:

- a **sale** (positive), dated by its payment date, written when the order is paid and classified;
- a **correction** (negative), dated the day the money was returned (a refund) or the change was
  found (a sale reclassified out of the report after it was handed over).

Each row holds what poz. 41 asks the records to show: the order and the marketplace's id; the sale
(payment) date; the buyer's name and address, copied so the record outlives the order's
anonymization; the gross amount, delivery included; the payment type and operator; `payment.id`,
the `CONTRIBUTION` operation and the `PAYOUT` it went out in; the category, reason code, rule-set
version and any override (who, when, why). It is kept as long as the order's own records: five
years from the end of the year the tax was due (`GDPR.md`), and erased by the same daily run.

### c) Reports for any range, and what has been handed over

A report is made for any date range (by default the whole previous month, offered once it has
ended) and reads the ledger rows dated in it. When a report is marked **handed over** to the
accountant, the rows it held are recorded against it. A later change to one of those sales never
rewrites them: it becomes a correction dated when it happened, which the next report carries. A
report handed over is then the same file every time it is downloaded again.

Before a report can be handed over, and shown as warnings while it is being prepared:

- every order paid in the range has a category, and none is `TO_REVIEW`;
- the categories add up to the range's `CONTRIBUTION` operations per operator, so nothing paid is
  missing and nothing in the report was never paid;
- no `NEEDS_REGISTER` row is left unacknowledged.

### d) Linking payments to the bank account

Each order's `payment.id` finds its `CONTRIBUTION` operation, which proves the payment came through
the operator for that order and that buyer. The operator's `PAYOUT` operations are what reaches the
bank account, per wallet; each contribution is assigned to the first payout of its wallet after it
became available. This is the "zestawienie" the interpretation relies on: an aggregate transfer and
the orders it covers. It can be checked against the payout report Allegro's Sales Center exports.

### e) Exports: CSV, Excel and PDF

- **Columns:** by default Lp., sale date, buyer's first and last name, amount; any other column the
  ledger holds (order number, marketplace, login, address, payment operator, `payment.id`, payout
  date, category, reason) may be added and ordered, and the choice remembered.
- **Rows:** the range's `EXEMPT_MAIL_ORDER` sales, then its corrections as negative amounts, then
  the total gross for the range. Lp. numbers the rows of that report.
- **PDF:** the same table with a header naming the business, the range and the date made, for the
  archive.
- **For reconciliation, on the screen and optionally exported:** the range's `BUSINESS`,
  `PRIVATE_INVOICED`, `NEEDS_REGISTER` and `NOT_A_SALE` totals, so that all categories add up to
  the range's sales.

### f) The VAT exemption limit

A non-payer loses the exemption from the sale that takes the year's sales past 240 000 zł (art. 113
ust. 1, the limit since 2026-01-01). Anvero knows every sale on both marketplaces, so the screen
shows the year's total against the limit, with a warning from 80%. What exactly counts toward the
limit (art. 113 ust. 2 leaves some sales out) is for the accountant; the counter is a warning, not
a ruling.

### g) The screen

A range at a time: the totals by category, the rows to review first, an override with a reason,
the checks of (c), the limit of (f), the exports, "mark as handed over", and the reports handed
over before. Drawn as mockups to choose from before it is built (`STYLE_GUIDE.md`).

### h) What the import must add

`payment.id`, `surcharges`, `codBookedPayments`, `lineItems[].tax`, `company.ids` and
`vatPayerStatus` from the checkout form; the `CONTRIBUTION` operations from
`/payments/payment-operations` (the payouts are read already) and the refunds (`/payments/refunds`).
Per product (SKU, else offer): an "excluded from the exemption (§ 4)" flag, off by default.

## 5. Plan of work

Each stage is committed and pushed on its own, with its tests, and the contracts (`API.md`,
`DATABASE.md`) changed in the same stage as the code.

1. **The import (h).** The new checkout-form fields and a migration; the `CONTRIBUTION` operations
   and refunds read on the import's schedule, into a table of payment operations. Tested against
   payloads shaped like the specification; then read once from the production account (read only,
   nothing written to Allegro) to confirm the fields are filled. *Built 2026-09-30*
   (`order_payments`, `payment_operations`, the new columns; `INTEGRATIONS.md`, "Payment
   operations, and the payment's id"). Refunds come from the `REFUND` group of the payment
   operations rather than `/payments/refunds`: they carry the payment's id and the amount, which is
   what a correction needs. The product's § 4 flag moves to stage 3, where it is first read.
   Waiting on the first real read, on the NAS after the update.
2. **The classifier (4a).** A pure function with a test for every category and reason code, and a
   run over the orders already imported, its counts shown to the owner before anything uses them.
3. **The ledger (4b, 4d).** The table, writing sales and corrections after each import, linking
   contributions to payouts, overrides with a reason, retention with the orders.
4. **Reports and exports (4c, 4e, 4f).** The API for a range with its checks, CSV, Excel
   (`openpyxl`) and PDF (a library that embeds a font with Polish letters), the column choice,
   handing over, the limit counter.
5. **The screen (4g).** Mockups first, then the page, replacing "Raport bezrachunkowy" in the menu.
6. **The first real month.** September 2026 produced and compared with Allegro's payout report and
   with what the accountant received before; any difference explained before the report is used.
7. **Erli.** Its buyer, payment and payout fields checked against its API, then the same classifier.
8. **The old report removed.** Its page, API and `sales_report_overrides` dropped, the docs brought
   up to date.

## 6. The report built on 2026-09-27, and what this replaces

The page "Raport bezrachunkowy" and `/sales-report/*` were ported from a standalone tool
(`DECISIONS.md`, 2026-09-27): three rules (a complete company invoice is `COMPANY`; cancelled or
suspended and unpaid is `OUT_OF_SCOPE`; paid in full, in PLN, shipped, with no or a personal invoice
is `RETAIL`) and everything else `MANUAL_REVIEW`, over Anvero's orders, with an override per order
and a CSV export. It has no notion of poz. 41's conditions (the payment operator, a cash part,
personal collection, excluded goods, a foreign delivery), links no payment to the bank account,
splits nothing by VAT rate, and is computed afresh on every request, so a month given to the
accountant can change afterwards. Its export also deliberately carries no name or address
(`DECISIONS.md`, 2026-09-27), which poz. 41 requires the record to show.

This design replaces it once built: the page, the API and `sales_report_overrides` go, and the new
ledger takes their place in the menu. Until then the old report stays as it is.
