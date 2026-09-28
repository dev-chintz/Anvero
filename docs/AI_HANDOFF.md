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
- 1031 backend tests and 613 frontend tests (Vitest + React Testing Library)
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

**PICK UP HERE (2026-09-29): the order page's summary redesign is built -
it needs the owner's look in a browser.** What was built, and why, is in
`DECISIONS.md` (2026-09-29): the status picker and its facts moved into
`OrderHeader` (`OrderFactsCard.tsx` deleted, its tests moved to "the status
row under the road" in `orderPageParts.test.tsx`), payment folded as
"Płatność" after the status history (`OrderPaymentCard` with `embedded`),
shipping its own card again, and a "Smart!" badge (`smartBadge.tsx`) in the
header, the Dostawa card and the order list, fed by the new
`orders.delivery_smart` (migration `b3e8d1f4a627`, applied to the NAS
development database). What is left: the owner opening a Smart and a
non-Smart order, with and without a parcel, in light and dark mode, and
saying whether round two reads as intended; then the next Allegro import, to
see `delivery.smart` arrive on real orders (`PROJECT_STATUS.md`, "Not yet
verified").

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