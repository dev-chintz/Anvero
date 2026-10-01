# AI START HERE

## Project

Anvero

Modern Business Management Platform

---

## Before doing anything

Read the following files in order:

1. PROJECT_STATUS.md
2. PROJECT_CONTEXT.md
3. PROJECT_RULES.md
4. ROADMAP.md
5. ARCHITECTURE.md
6. DATABASE.md
7. API.md
8. MVP.md
9. DECISIONS.md
10. INTEGRATIONS.md
11. STYLE_GUIDE.md (before writing any interface: the one look every page shares)
12. GDPR.md (before storing, showing or exporting anything about a buyer)
13. NON_INVOICED_SALES.md (before touching the non-invoiced sales record: the law, the design, what was found)
14. CATALOG.md (before touching the assortment: where it is read from, how pictures are kept, how Erli is tied to Allegro)

---

## Current State

**Feature work:** decided 2026-09-24 to keep building, modelled on
AlleIntegrator; the order of work is the feature plan at the end of
`ROADMAP.md`, followed there by a comparison with AlleIntegrator and the
suggested next steps (stages A1–A3 are done: work queues, the "to make" list,
wider search and the buyer's other orders; A4, the Erli import, has its
adapter built from Erli's docs and waits for the owner's API key; A5, safe
mode, is done, so every marketplace write must go through `MarketplaceWriter`;
A6, status and tracking number to Allegro, is built but never sent for real;
A7, the application status page, is done. Stage A is complete apart from
A4's first real run and A6's first real send. B1, labels through "Wysyłam z
Allegro", is built for one parcel per order, with printing many at once and
ordering a courier on the Labels page, and never used for real; cash on
delivery is not shipped, so B1 is complete in code. B2, buyer messages, is
started: see below. B4, returns and claims, is started: a read-only queue
with deadlines, an alert on the order and a dashboard reminder, built from
Allegro's published specification. Its first real read, on 2026-09-28,
failed with a `406` until the disputes-and-claims call was given the beta
Accept header the endpoint needs (`DECISIONS.md`); fixed, and a second real
read succeeded: 0 open issues, 10 closed issues, 10 customer returns).

**InPost (2026-09-25):** parcel locker shipments and their labels can be made through InPost's ShipX API, in bulk from the Labels page and on the order (`INTEGRATIONS.md`, "InPost"); built from the documentation, never run against InPost, and waiting for the owner's sandbox token and organization number, which they enter in Integrations.

**Shipping analysis (2026-09-25):** how the business ships and a proposed plan for labels (Allegro's InPost through Wysyłam z Allegro, Erli's own parcel API, printing from the NAS straight to the networked Xprinter) are in `ROADMAP.md`, "Shipping and labels: analysis and proposed plan". Not decided and not built; the owner will refine it. It found that the direct InPost path above would probably pay for Smart parcels from the InPost balance, so it should not be used for Allegro orders.

**Non-invoiced sales record (2026-10-01):** "Raport bezrachunkowy" in the menu (`/sales-report`) is the record poz. 41 requires, built from `NON_INVOICED_SALES.md` in all eight stages: the import keeps the trace of every payment (Allegro's and Erli's), a classifier sorts each paid sale, and every import writes the ledger (`non_invoiced_ledger`); reports for any range, exported as CSV, Excel or PDF with the columns chosen, are handed over to the accountant, which locks their rows. The report ported on 2026-09-27 and its `sales_report_overrides` are gone. Not yet used for real: see `PROJECT_STATUS.md`, "Not yet verified", for what to check before September goes to the accountant.

**Assortment (2026-10-01):** "Asortyment" in the menu (`/catalog`) lists every offer in the Allegro account with its pictures, a category tree beside a compact list, and for each offer the same product on Erli with the category in both. Read only. Pictures are downloaded to the NAS (`CATALOG_IMAGES_DIR`, a mounted folder: `DEPLOYMENT.md`) and kept beside their address on Allegro. Built from the marketplaces' published descriptions and never run against the real Allegro or Erli: see `PROJECT_STATUS.md`, "Not yet verified", and `CATALOG.md`.

**NAS deployment (2026-09-27):** done. Running at `http://NAS_ADDRESS:8081`
(not 8080 - taken on this NAS), backend reaching the database over a joined
Docker network by container name rather than the NAS's LAN address. See
`DEPLOYMENT.md` and `DECISIONS.md` for what differed from the written plan.

**GDPR (2026-09-28):** personal data is erased by itself once past its period (orders five years after the year their tax was due, messages, closed cases and what was sent to a marketplace after two), a buyer's request is answered with `backend/scripts/export_person.py` and `anonymize_person.py`, the integration secrets are encrypted once `SECRETS_KEY` is set, and the list's search is kept out of the address. See `GDPR.md`. Deployed to the NAS 2026-09-28 with everything else below; `SECRETS_KEY` is still not set there (optional, `DEPLOYMENT.md`, "Encrypting the integration secrets") and the daily retention run has not been watched for its first real pass yet.

**Updates from Settings (2026-09-28):** built, answering the "Open task" this
section used to name, and set up on the NAS the same day: `anvero-updater`
public, `UPDATER_TOKEN` in the NAS's `docker-compose.yml`, confirmed live (the
backend's log shows a successful GitHub API call, `/api/v1/health` answers
`commit: 286ab9d`). The button itself has not been clicked yet from
Settings - this first deploy was done by hand over SSH to get the updater
running in the first place; the next push to `main` is the real test.

Backend and frontend both run. See PROJECT_STATUS.md for the sprint-by-sprint
breakdown; the short version:

- FastAPI backend with orders, status changes, status history and statistics.
- Login: every orders endpoint and every page requires it. Accounts are
  created with `backend/scripts/create_user.py`, passwords changed with
  `backend/scripts/reset_password.py`; there is no sign-up.
- React + TypeScript frontend: dashboard, order list with filtering, order
  detail with items, buyer, delivery, payment and invoice, status editing and
  history.
- Allegro adapter, import script, an import endpoint and a button, one
  import at a time.
- 1299 backend and 659 frontend tests passing.
- The order opens as a page of its own with back and next/previous arrows, the
  list shows each order's items, the menu shows what waits, and a new interface
  language is a dictionary file and one line (`DECISIONS.md`, 2026-09-24).

- One shared PostgreSQL 17 on the owner's NAS is the development database;
  each machine's `backend/.env` points at it (the password is not in Git, ask
  the owner). SQLite remains the no-setup default for a fresh clone. Check
  `DATABASE_URL` in `backend/.env` to see which one a machine uses. Away from
  home the NAS is reachable only through a VPN (`DEVELOPMENT.md`).

The Allegro import first ran against the real API in the Allegro Sandbox, on
2026-09-17. Since 2026-09-25 both Allegro and Erli are connected on the
owner's real, production accounts and import real orders (Allegro also its
buyer messages) on the usual schedule - safe mode has stayed on throughout,
so nothing has been written back to either marketplace. See
PROJECT_STATUS.md, "Not yet verified", and INTEGRATIONS.md.

Treat anything in the "Not yet verified" section of PROJECT_STATUS.md as
unproven, however finished the code looks.

---

## Rules

- Documentation is the source of truth.
- Never redesign architecture without updating documentation.
- Keep code clean and modular.
- Follow existing project structure.
- Prefer simple solutions.
- Every important decision goes to DECISIONS.md.
- Every milestone goes to CHANGELOG.md.

---

## Workflow

Read documentation.

Understand current sprint.

Implement.

Update documentation.

Commit.

Push.

Before writing code, also read:

- DEVELOPMENT_WORKFLOW.md