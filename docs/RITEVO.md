# Ritevo: a map of the panel (2026-09-27)

A competitor's order-management panel (`https://app.ritevo.com`), mapped by reading it while
logged in with the owner's own account. The account was empty (no integration, order, product
or message), so this records structure, not data. Nothing was created or changed there.

## Menu and addresses

| Section | Address | What is there |
| --- | --- | --- |
| Dashboard | `/dashboard` | Four tiles (today's and this month's order total and count, with a change in %), a chart of value and count over 7 days (SVG/PNG/CSV export), orders by integration, "message audits" and "order audits" |
| Orders: All | `/orders` | List with filters and paging (20 per page), "Add order" |
| Orders: Billings | `/orders/billings` | Tabs: VAT invoice, invoice correction, receipt; filters; "numbering settings" |
| Orders: Statuses | `/orders/statuses` | Own statuses: display name, description (shown on hover), look, options |
| Orders: Actions | `/orders/automatic-actions` | Automatic actions (list) |
| Orders: Settings | `/orders/settings` | Packing assistant and keyboard shortcuts |
| Messages: All | `/messages` | List with filters |
| Messages: Statuses | `/messages/statuses` | As the order statuses |
| Messages: Templates | `/messages/templates` | Ready answers "in one click" |
| Messages: Actions | `/messages/automatic-actions` | Automatic actions for messages |
| Products | `/products` | List with filters, "Add product" |
| Integrations | `/integrations` | List, "Add integration" (`/integrations/add-integration`) |

Creating uses `/…/create` (`/orders/create`, `/products/create`, `/orders/automatic-actions/create`).
The menu's foot has sign out, settings (not opened) and a dark mode toggle.

## Integrations offered (22)

- Marketplaces (5): Allegro, eBay, Erli, Empik, an own sales channel
- Web shops (3): WooCommerce, PrestaShop, Shoper
- Shipping (3): Wysyłam z Allegro, InPost ShipX parcel locker, DPD PL
- Accounting (3): wFirma, KSeF, eParagony
- Warehouses and wholesalers (2): an own warehouse, Hurtownia Karm
- E-mail (1); messengers (2): WhatsApp, Messenger; AI (2): OpenAI, Claude; printers (1)

## Forms

- **Order:** a manual order can only be added to the "own integration"; without one the form is blocked.
- **Product:** integration, name, producer, category, identifiers (external id, SKU, EAN, extra EANs up to 100),
  description, dimensions and weight, price (amount, currency, VAT rate), stock levels.
- **Automatic action:** name, description, trigger type, time zone (Europe/Warsaw), active yes/no, up to 50
  conditions and up to 50 steps. The trigger and step types could not be read: the lists stay empty until an
  integration exists.
- **Packing assistant (Orders: Settings):** the field a code is matched on (EAN), scanning mode ("strict",
  items in order), packing flow ("products only"), accept a product's extra EANs, close the assistant when a
  parcel is packed; shortcuts for packing a parcel, skipping the waybill scan and opening the assistant.

## What is worth a look for Anvero

- The **packing assistant**, with scanning by EAN and keyboard shortcuts, which Anvero has nothing like.
- **Own statuses** for orders and messages, and **automatic actions** ("conditions, then steps"): the "Rules" row
  of `ROADMAP.md`, marked missing.
- **Message templates**, **audits** on the dashboard, and invoice, correction and receipt with their own numbering
  (with KSeF and wFirma offered as integrations).
- Its list of integrations overlaps ours almost entirely (Allegro, Erli, InPost, Wysyłam z Allegro): a direct competitor.
