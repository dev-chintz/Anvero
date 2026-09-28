# AI HANDOFF

## Project

Anvero

Modern Business Management Platform

---

# Mission

Anvero is a modern SaaS platform for managing e-commerce businesses.

The long-term goal is to build a modular, scalable system focused on excellent UX, clean architecture and AI-assisted development.

The project is developed incrementally using sprint-based planning.

---

# Current Status

Version: 0.1.0

Phase: Foundation

Sprint: Sprints 2, 3 and 4 delivered. The development database is a shared
PostgreSQL 17 on the owner's NAS (since 2026-09-18); a machine whose `.env`
still points at SQLite has its own separate data.

Repository: <https://github.com/dev-chintz/Anvero>

---

# Completed

- Updates from Settings (2026-09-28): banner and Settings tab for a newer
  published version, installed by the `updater` container (`DEPLOYMENT.md`)
- GDPR (2026-09-28): daily retention and anonymization, one buyer's export
  and erasure by script, integration secrets encrypted with `SECRETS_KEY`,
  searches kept out of the address (`GDPR.md`)
- Project name, branding direction, folder structure, development workflow
- FastAPI backend: orders, status changes, status history with author,
  statistics
- Login required for every orders endpoint and page; accounts created by
  script, no sign-up; 8-hour tokens
- React + TypeScript frontend: login page, dashboard, order list with
  filtering and search, order detail with items, buyer, delivery, payment
  and invoice, status editing and history, dark mode
- Alembic migrations for `users`, `orders`, `order_items`,
  `order_addresses`, `order_status_history` and `integration_credentials`
- Allegro adapter, order mapping, the import script, an import endpoint and
  a button, one import at a time and rate limited
- 2026-09-18: several additive interface capabilities and one more imported
  field, pulled forward while production Allegro waits on the owner (not the
  redesign below) — inline status editing in the list, status-history
  timeline icons, the order detail view as a slide-over drawer (a page again
  since 2026-09-24), the order
  list reorganized toward a denser reference layout, the seller's own
  Allegro note imported alongside the buyer's message, and item pictures
  fetched from Allegro's offer API (unverified against the sandbox for
  scope). Full detail in `DECISIONS.md` and `CHANGELOG.md`.
- 1017 backend tests and 604 frontend tests (Vitest + React Testing Library)
  passing

---

# Current Directory Structure

```
backend/    FastAPI application, migrations, tests, scripts
frontend/   React + TypeScript (Vite)
docs/       project documentation
scripts/    PowerShell helpers for the local environment
```

`database/` and `branding/` do not exist; migrations live under
`backend/migrations/`.

---

# Current Priorities

**PICK UP HERE (2026-09-28, evening): the order page's summary redesign.**
Started live with the owner in chat, mockups shown inline (not saved as
files - this description is the only record, so read it in full rather than
guessing from the code alone) and refined through two rounds. The *second*
round is the one to build; it replaces some of what the *first* round already
put in the working tree (uncommitted - `git status` before assuming any of
these files are clean). Both rounds are described below so the diff between
them is clear, since the first round's CSS classes and structure are still
sitting in the tree and need removing, not just adding to.

## Where this starts: the order page today

`frontend/src/components/OrderDetail.tsx` lays the order page out as: header
(`OrderHeader`), attention bar, after-sales card, items, then a 3-column grid
(`.order-details-top`: Kupujący/Buyer, Faktura/Invoice, Dostawa/Delivery -
this part is finished, approved, and out of scope here), then whatever the
first round below left in place, then messages, then the folded "more"
sections (`OrderMoreSections`), then the internal note.

`Kupujący`/`Faktura`/`Dostawa` already show a real carrier or Allegro Smart
brand mark where relevant, from `frontend/src/components/carrierBadge.tsx`
(real Simple Icons SVGs for DHL/DPD/UPS/FedEx/Allegro in
`frontend/src/assets/carriers/`, a coloured text badge for InPost/Poczta
Polska/GLS which Simple Icons does not carry) - reuse this pattern, do not
rebuild it, for the Smart badge below.

## Round one (in the tree now, uncommitted, partly superseded)

Płatność, Zamówienie and Wysyłka were merged into one bordered box,
`.order-summary-bar` (`OrderPage.css`): Płatność and Zamówienie side by side
on one line (`.order-summary-top`), Wysyłka as its own line below (its own
collapse-behind-a-button already built, see below), band/heading colours
hidden, a vertical divider standing in for them. This is what is live in
`OrderDetail.tsx`, `OrderDetailsPanel.tsx`, `OrderPage.css` right now.

The owner's verdict after seeing it live: better than before, but still
"mało przejrzyste" (not clear enough) once real data (a Nowe order, no
parcels yet) filled it in - small-caps labels crammed against values with
no separation read as noise. That is what round two below replaces; do not
try to fix round one's formatting in place.

**Keep from round one, unchanged:** the shipping card's collapse. In
`OrderShippingCard.tsx`, `showAdd` (state) defaults to `shipments.length ===
0`; when there is already a parcel, the ways-to-ship tabs/form stay folded
behind a button, `t("order.addAnotherShipment")` (`+ Dodaj kolejną
przesyłkę` / `+ Add another shipment`, already in `messages.ts`). This part
was approved and is not part of what changes below - only *where* the
shipping card sits changes (its own card again, not a segment of the bar).

## Round two (approved, not yet built)

Płatność leaves the top of the page entirely; Zamówienie's status control
and facts move into the header; Wysyłka goes back to being its own ordinary
`.order-card` (own teal band, own margin - undo the "hide the band, share
one box" treatment from round one for this card specifically). An Allegro
Smart badge appears in three places. In order:

1. **`OrderHeader.tsx`: a Smart badge in the badge row.** Next to the
   existing `ALLEGRO`/`PL` badges (`.order-header-meta`, around line 111),
   when the order is a Smart delivery: same visual language as
   `carrierBadge.tsx`'s pill (small, coloured, bold), text "Smart!", on a
   near-black background with Allegro's orange (`#FF5A00`) text - Allegro
   Smart has no ready-made mark to reuse, this is the agreed fallback, same
   idea as InPost/Poczta/GLS's text-only badges. A new small component,
   e.g. `frontend/src/components/smartBadge.tsx`, exporting a `SmartBadge`
   that takes whatever tells it the order is Smart (see the data question
   below) and renders `null` when it is not - used from here, from
   `OrderDetailsPanel.tsx`'s Dostawa card head (next to `CarrierBadge`,
   `OrderDetailsPanel.tsx` around line 341-365), and from `OrderRow.tsx`'s
   shipping cell (around line 331) for the order list.

2. **`OrderHeader.tsx`: a status row under the step pills.** The existing
   `<ol className="order-steps">` (line 177) stays exactly as it is - do not
   redesign the pill road. Immediately below it, a new row, divided from the
   pills by a top border: a `<select>` that can set *any* status (not only
   the next one - this is `OrderFactsCard`'s existing `onStatusChange`
   contract, `STATUSES = Object.values(OrderStatus)`, reused here rather
   than reinvented), then inline beside it, separated by " · ", the three
   facts `OrderFactsCard` used to show: "w tym statusie od X"
   (`order.inStatus`), "termin wysyłki Y" (`order.dispatchBy`, only when
   `order.dispatch_by` is set), "Allegro: Z" (`order.marketplaceStatus`,
   only when `order.marketplace_status_label` is set). `OrderHeader` does
   not currently receive `saving`/`saveError`/`writeNote`/`onStatusChange`
   for a *manual* status pick (only `onNextStep`) - it will need the same
   props `OrderFactsCard` takes today, passed from `OrderDetail.tsx` the
   same way. Whether `OrderFactsCard.tsx` becomes dead code to delete, or
   its guts move into `OrderHeader.tsx` and the file goes, or `OrderHeader`
   imports and reuses pieces of it, is an implementation choice - the owner
   did not specify, only the *result* (described above and, more precisely,
   in the mockup this note summarizes). `orderPageParts.test.tsx` has the
   existing `OrderFactsCard` tests (status select, deadline/marketplace
   text, writeNote) - move or adapt them to wherever this logic ends up
   rather than deleting the coverage.

3. **`OrderMoreSections.tsx`: a new folded "Płatność" section, right after
   "Historia statusów"** (the first `Folded` in the list, `history.title` -
   the new one goes immediately after it, before the `billing &&` one).
   Content: what `OrderPaymentCard` (`OrderDetailsPanel.tsx`) shows today -
   the paid/unpaid amount and date (`PaymentState`), the payment type, the
   provider - as the folded section's body, `embedded` style like
   `OrderBillingCard`/`BuyerOrdersCard` beside it. A summary value beside
   the title while folded (`Folded`'s `summary` prop, e.g. the amount) was
   in the mockup but not explicitly asked for - reasonable to include,
   matching how the other folded sections already do it (`billing`'s
   summary is its total, `writes`'s is its count). `OrderPaymentCard`
   itself (component and its `payment-paid`/`payment-unpaid` colour, tested
   in `orderPageParts.test.tsx`, "the payment card's colour") should very
   likely stay as the thing rendered inside the fold, `embedded`-styled,
   rather than being rewritten - keep that test passing, adapting only what
   it needs to run standalone.

4. **`OrderDetail.tsx` / `OrderPage.css`: unwind the round-one bar.** Remove
   `.order-summary-bar` / `.order-summary-top` and their CSS; `Kupujący`/
   `Faktura`/`Dostawa`'s own grid (`.order-details-top`) is untouched.
   `OrderShippingCard` goes back to being rendered on its own between the
   items and the messages card, with its normal `.order-card` chrome (own
   teal band) - only its internal collapse-behind-a-button (round one,
   kept) changes what it looks like once there is a parcel.

## The Smart data question - answer this before step 1 above

`delivery.smart` is a real boolean Allegro returns on `GET
/order/checkout-forms` (confirmed by searching Allegro's own developer
documentation this session, not assumed) - **and nothing in Anvero reads it
yet.** Before the frontend badges can show anything real:

- `backend/app/schemas/order.py`: add `smart: bool` (or `bool | None`) to
  `Delivery`.
- `backend/app/integrations/allegro/mapper.py`, around line 366-389 (where
  `Delivery` is built via `_build(...)`, alongside `method`/`cost`): add
  `"smart": bool(delivery.get("smart", False))`.
- `backend/app/models/order.py`: a new column, most likely `delivery_smart`,
  next to the existing `delivery_method`/`delivery_cost` columns Order
  already flattens `Delivery` onto (see `schemas/order.py` around line
  345-347, `Delivery(method=order.delivery_method, cost=order.delivery_cost,
  ...)` for the pattern to follow) - plus a new Alembic migration.
  `backend/app/services/order_details.py` (`apply_details`, mentioned by
  `order_import_service.py`) and wherever else `delivery_method`/
  `delivery_cost` are read from an imported payload and written onto the
  `Order` row need the same new field added alongside them - grep for
  `delivery_cost` to find every place that needs the parallel change, rather
  than assuming the two spots above are the only ones.
- `frontend/src/types/order.ts`: add `smart: boolean` to the `Delivery`
  interface.
- Whether the order **list** endpoint (`OrderListItem`, `schemas/order.py`,
  which extends `OrderRead` - the same class that already builds `Delivery`
  for the detail response) already carries `delivery.smart` once the schema
  change lands, or needs its own explicit wiring, is unverified - check
  before assuming `OrderRow.tsx`'s list-row badge (place 3 above) has data
  to read; the order list's own query/repository method may select fewer
  columns than the detail one does.
- Erli has no equivalent concept as far as is known; leave its mapper alone
  unless research says otherwise.

## Before calling this done

- Backend and frontend tests, both suites, run fresh rather than trusting
  the numbers elsewhere in this file or in `PROJECT_STATUS.md` - they were
  not re-measured after this handoff was written. A new Alembic migration
  needs `alembic upgrade head` on this machine's database before the
  backend tests touching it will pass.
- `npx tsc --noEmit` in `frontend/`.
- The order page opened in the browser, logged in **by the owner, not by an
  assistant** (`CLAUDE.md`, "Environment gotchas": every page needs a login,
  and typing a password into the browser to verify UI work is off-limits -
  check functionality through the API instead, and ask the owner to look at
  the page itself) - on a Smart order, a non-Smart order, an order with no
  parcel yet and one with a parcel already, in light and dark mode.
- `docs/DECISIONS.md`, `PROJECT_STATUS.md`, `CHANGELOG.md`, this file's
  "Completed"/"Current Priorities" updated the same way every other entry
  in `DECISIONS.md` this session was (decision, rationale, consequences,
  what was and was not verified) - see the entries dated 2026-09-28 for the
  pattern.

---

# UI Direction

A visual rework — new colours, a component library, the Figma/purple-accent
direction below — is planned only after the system works unattended and runs
somewhere with backups (`ROADMAP.md` item 5, `DECISIONS.md` 2026-09-17). That
is still on hold. What is *not* on hold, per the owner: additive interface
capabilities that reuse what already exists rather than restyle it — see the
2026-09-18 entries in `DECISIONS.md` for what that has meant in practice
(inline editing, a drawer instead of a page - reversed on 2026-09-24 - denser
list columns). The
distinction that matters: does it change what a screen *looks* like
everywhere, or does it add a capability without touching the values already
in `index.css`.

What exists today:

- Dark left sidebar (200px open, 70px collapsed), bright workspace, rounded
  corners
- Plain CSS, stylesheets under `frontend/src/styles/` plus `index.css`; no
  component library, no CSS framework. `index.css`'s `:root`/`:root.dark`
  hold named tokens for values repeated across files (accent, surface,
  divider, headings, radii, semantic colours) — see `DECISIONS.md`
  2026-09-18 before assuming a value is a one-off
- Colours, spacing and radii come from the variables in `index.css`; the
  accent is blue in light mode, teal in dark
- Light and dark follow the system, with an explicit override
- Vitest + React Testing Library, wired into the pre-commit hook and CI
  (`npm run test`); still thin, per `ROADMAP.md`

The direction below — premium SaaS, purple accent, Linear and Stripe as
models — and the Figma dashboard prototype are aspirations, not descriptions:
nothing in the code follows them. They are candidates for the later visual
pass, to be confirmed or dropped then.

Style:

- Premium SaaS
- Dark left sidebar
- Bright workspace
- Purple accent color
- Rounded corners
- Large whitespace
- Modern typography

Inspired by:

- Linear
- Stripe Dashboard
- Notion
- Vercel

---

# Development Principles

- Clean Architecture
- Modular design
- Production-quality code
- Documentation first
- Small commits
- Simplicity over complexity

---

# Before Writing Code

Read:

- AI_START_HERE.md
- PROJECT_STATUS.md
- PROJECT_CONTEXT.md
- PROJECT_RULES.md
- ROADMAP.md
- ARCHITECTURE.md
- DATABASE.md
- API.md
- MVP.md
- DECISIONS.md
- INTEGRATIONS.md

---

# AI Responsibilities

Before implementing anything:

- understand current sprint
- understand project architecture
- avoid unnecessary redesign
- keep documentation synchronized
- explain important architectural decisions

---

# Long-Term Vision

Anvero should become a professional business management platform that combines:

- ERP
- Inventory
- Orders
- CRM
- Marketplace integrations
- Analytics

The system should remain modular and easy to extend.

---

# Notes

Repository documentation is the single source of truth.

Chat history must never be treated as project documentation.