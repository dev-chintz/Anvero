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
- Order page (2026-09-29): status picker in the header, payment folded,
  Allegro Smart badge (`DECISIONS.md`)
- 1048 backend tests and 621 frontend tests (Vitest + React Testing Library)
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

**PICK UP HERE (2026-09-29, evening): UI improvement in Claude Design.** The
owner asked to improve the interface with Claude Design (`DECISIONS.md`,
2026-09-29, "UI work moves to Claude Design"). Two private artifacts in the
owner's claude.ai account hold it, readable only when signed in as the owner:

- the **Anvero design system**, https://claude.ai/artifact/UUeEBotbDsA8UdJ7sWHMwY: tokens, brand book and nine
  components built from `index.css`, `theme.css` and `STYLE_GUIDE.md` at
  `3cfbdc0`. It follows the code: a token changes in `index.css` first. Not
  yet brought up to 2026-09-30: the new variables, the Papier look and the new
  logo (`docs/brand/`).
- the **order page canvas**, https://claude.ai/artifact/QJHBPmAH386DKwASmqmG43: a proposal (two columns: the work on
  the left, the facts in a 340px rail on the right, payment back as a green
  card, the status facts beside the steps) next to today's layout.

The owner chose the canvas's layout, refined for a monitor turned upright, and
it is built (`DECISIONS.md`, 2026-09-29, "The order page in two columns"),
tested but not yet seen in a browser. The next screen, the **order list**,
is on its own canvas, https://claude.ai/artifact/JmMk1VptHZkoaDXtgYpumF: a
proposal for the upright monitor (four work queues as tiles with counts,
status as tabs, the buyer folded into the order cell, tinted status chips
readable at 5.3:1 or better instead of white on solid fills), today's list,
and the old and new status badges side by side. The owner chose it and it is
built (`DECISIONS.md`, 2026-09-29, "Status chips" and "The order list"),
tested but not yet seen in a browser. The design system still shows the old
solid badges: re-sync it from the code when convenient.

The third screen, the **dashboard** (Pulpit), is on
https://claude.ai/artifact/RtHYhEL8emq1dtChTBwLaG: a proposal (what needs
attention as coloured bars at the top, the same four work queues as the order
list, the nearest dispatch deadlines as a dense full-width list, recent orders
beside a narrow column with the week's figures and the channels) next to
today's. Chosen and built (`DECISIONS.md`, 2026-09-29, "The dashboard"), tested
but not yet seen in a browser.

The fourth screen, the **inbox** (Wiadomości), is on
https://claude.ai/artifact/EwL3qz5B69H3PQK7hZ76rR: a proposal (a narrower
290px list of conversations with one-line rows, the conversation wider, and
above it a card of the linked order: number, status, deadline, items, amount,
a link to it) next to today's. Chosen and built (`DECISIONS.md`, 2026-09-30, "The inbox"):
the order card became the buyer's orders, found by nick, since Allegro keeps
one conversation per buyer and no thread carries an order. Tested, not yet
seen in a browser.

The fifth screen, **Do wykonania** (the production list), is on
https://claude.ai/artifact/CSkXq3juSgom9XZKQrF7jV: a proposal (the filters,
search, "hide made" and the progress in one card; in each deadline group a
dense row led by the quantity in large type, then the picture, the product
and SKU, and the orders as small chips) next to today's. Chosen and built
(`DECISIONS.md`, 2026-09-30, "The to-make list"), tested, not yet seen in a
browser.

The sixth screen, **Etykiety** (labels), is on
https://claude.ai/artifact/3nh6EAifHeSk5n5WRtMSx9: a proposal (the two ways
to ship and the three views as underlined tabs, the print and courier buttons
in a bar that appears only with something ticked, labels grouped by carrier
with "tick the group", and one dense row per label: number, carrier, nick and
locker or waybill, print state and courier as chips) next to today's. Chosen and
built (`DECISIONS.md`, 2026-09-30, "The labels page"), tested, not yet seen in
a browser. Counts on the view tabs would need the labels of every
view, not only the one shown.

The seventh screen, **Zwroty i reklamacje** (after-sales), is on
https://claude.ai/artifact/PaHeT5BkF7g4EVxjjB1tLS: a proposal (the summary as
four tiles like the order list's queues, the views as underlined tabs and the
kind as pills in one card, one dense row per case: the deadline as a chip with
the date under it, the kind as a chip with its reference, what to do in bold
over the order, nick and reason, the status as a chip) next to today's.
Chosen and built (`DECISIONS.md`, 2026-09-30, "Returns and claims") without
the fourth tile and the last-read time, which have no data yet; tested, not
yet seen in a browser.

The eighth screen, **Finanse**, is on
https://claude.ai/artifact/1kMgPfN17SZ6iFp11VcMax: a proposal (the two tabs
and the period as one segmented control on one line, the four figures in one
row with fees tinted amber and what is left green, the fee bars full width,
then by channel, delivery and the check against Allegro as three narrow cards
side by side) next to today's, where below 1100px everything stacks into one
column. Chosen and built (`DECISIONS.md`, 2026-09-30, "The finance page"),
tested, not yet seen in a browser.

A **second look** is on https://claude.ai/artifact/1tJfJmnRK6JXpe4dJzNSRy:
three directions for the order list, the owner's pick ("Papier": cream,
brick accent, serif titles) drawn for every menu, and Settings with a style
switch beside light/dark, the layout the same in both looks. First step done
(`DECISIONS.md`, 2026-09-30, "Every colour in the stylesheets is a
variable"), then the Style choice in Settings with Papier's values
(2026-09-30, "A second look, chosen in Settings"); Papier is not yet looked at
behind the login.

The **non-invoiced sales report** is to be rebuilt from `NON_INVOICED_SALES.md`
(2026-09-30): a design only, waiting on the accountant's answers to its open
questions before any code.

The order page's round two (status in
the header, payment folded, Smart badge) was seen by the owner in the browser
and adjusted (space under Wysyłka, a blue band for Wiadomości); what is still
unseen is `delivery.smart` on a real import (`PROJECT_STATUS.md`).

After that, the feature plan at the end of `ROADMAP.md` (`PROJECT_STATUS.md`).

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

One exception, at the owner's request (`DECISIONS.md`, 2026-09-30): a second
look, Papier, to pick in Settings beside Classic. It is only a second set of
variable values; the layout and parts are the same in both looks.

What exists today:

- Left sidebar (200px open, 70px collapsed), light grey in light mode and
  dark in dark mode, beside a grey canvas of white rounded cards
- Plain CSS, stylesheets under `frontend/src/styles/` plus `index.css`; no
  component library, no CSS framework. `index.css`'s `:root`/`:root.dark`
  hold named tokens for values repeated across files (accent, surface,
  divider, headings, radii, semantic colours) — see `DECISIONS.md`
  2026-09-18 before assuming a value is a one-off
- Colours, fonts and radii come from the variables in `index.css`, never a
  literal in a stylesheet (since 2026-09-30); the accent is teal (brick in
  Papier)
- Two choices in Settings, both kept in the browser: the look (Classic or
  Papier, `theme-look`) and the mode (light until dark is chosen, whatever
  the system prefers, `theme-mode`)
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