# Alternatives: similar products

Written 2026-09-21, after the owner pointed at two existing products that do
much of what Anvero is meant to. **Everything below comes from each product's
home page only** (read once, summarised); nothing was installed or tried, no
documentation, terms or privacy policy was read, and prices and features may
have changed or be described more generously than reality. Treat it as a list
of questions, not findings.

## The two products

### AlleIntegrator — https://alleintegrator.pl

- **Model:** self-hosted, on the user's own computer or server; not SaaS.
  Free, with no time limit, no order limit and no per-account or per-channel
  fee. Configuration exports as one portable file; onboarding said to take
  about a day.
- **Marketplaces and shops:** Allegro, EmpikPlace, Erli, OLX; PrestaShop,
  WooCommerce.
- **Couriers:** InPost, DPD, DHL, ORLEN Paczka, Pocztex, with label generation.
- **Invoicing:** automatic, with KSeF; Fakturownia, Firmino, Fakturowo.
- **Also:** one order queue across channels, stock shared across channels to
  prevent overselling, centralised customer messages with AI auto-replies,
  price rules with profitability thresholds.

### Ritevo — https://ritevo.com

- **Model:** cloud SaaS, used from a browser. Starter free (up to 1,000
  orders and 200 messages a month); Business 99 PLN a month (up to 10,000
  orders, 1,000 messages); Enterprise by quote. AI usage billed separately.
- **Marketplaces and shops:** Allegro, eBay, Empik, Erli; WooCommerce.
- **Couriers:** InPost, DPD, Wysyłam z Allegro.
- **Invoicing:** wFirma, KSeF, eparagony.pl.
- **Also:** orders with custom statuses, filters and bulk actions; a shared
  inbox (marketplaces, WhatsApp, e-mail) with templates and AI replies;
  rule-based automation (trigger, condition, action: e.g. issue an invoice and
  create a shipment); a packing assistant that checks items by EAN barcode
  scan; product and stock list; sales analytics; warehouse connections. The
  page names almost nothing about the company beyond a contact e-mail.

## Side by side

| | Anvero | AlleIntegrator | Ritevo |
|---|---|---|---|
| Runs on | the owner's NAS | user's computer or server | the vendor's cloud |
| Cost | none | none, no limits | none up to 1,000 orders a month, then 99 PLN |
| Where data and Allegro tokens live | with the owner | with the owner | with the vendor |
| Marketplaces | Allegro (Erli planned) | Allegro, Empik, Erli, OLX | Allegro, eBay, Empik, Erli |
| Shipping labels | planned (`ROADMAP.md` item 4) | yes | yes |
| Invoices, KSeF | planned | yes | yes |
| Messages | planned | yes, with AI | yes, with AI |
| Fees per order | read, not yet verified | not stated | analytics, not stated |
| Rules and automation | none | price rules | trigger, condition, action |
| Packing check | none | not stated | EAN scanning |
| Interface language | Polish and English | Polish (presumably) | Polish (presumably) |

## What it means for Anvero

- Anvero is the least complete of the three. Labels, invoices with KSeF, and
  courier integrations are the most expensive part of the roadmap and are
  already built by both others.
- What Anvero has that the others may not: the code and data are the owner's
  and can be changed to fit; no limits or vendor to depend on; the order
  history and its backup are the owner's.
- What each other product is a useful reference for: Ritevo for automation
  rules and the packing check (what saves most time at volume); AlleIntegrator
  for the self-hosted, one-file-configuration model.

## To decide, and how

The question is whether to keep building Anvero's own labels, invoices and
stock, adopt one of these for that part, or take ideas only. Suggested way to
find out, before building any of it:

1. Install AlleIntegrator (it is self-hosted) and open a free Ritevo account,
   both against the Allegro **Sandbox** or a few real orders, and go through
   the owner's ordinary working day in each: what is quicker, what is missing,
   what gets in the way.
2. Before giving either access to the real Allegro account: who is behind it,
   which permissions it asks for, how tokens are stored and where data is kept,
   what happens to the data if it is switched off. The home pages say nothing
   on this. For Ritevo it also means customers' names and addresses on the
   vendor's servers.
3. Write the result here: what each covers of the roadmap items, what it
   costs, and what would still be worth building, and remove from
   `ROADMAP.md` what is not.

Until then, additions to Anvero should be the kind neither of them can offer:
things specific to how the owner works, or that depend on owning the data.
