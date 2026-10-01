# The in-app guide

Help (`/help`, "Pomoc" last in the menu) holds two tabs: the **guide**, which tells
someone who has just sat down at Anvero what each part of it is for, and the
**GDPR tab** (`GDPR.md`, "The GDPR tab"). Both are open to every logged-in account;
the menu entry carries no area. Added 2026-10-01 (`DECISIONS.md`, "The in-app guide
and the GDPR tab").

## What the guide holds

`frontend/src/pages/help/GuideTab.tsx` shows `GuideContent`
(`frontend/src/guide/types.ts`), written once per interface language:
`content.pl.ts` and `content.en.ts`, chosen by `guideFor(language)`; a language
without its own shows the English one.

- **About**: what the application is, in a paragraph.
- **Sections**, in four groups (`basics`, `daily`, `money`, `setup`), one for each
  part of the application: Start (the menu), Dashboard, Orders, an order, To make,
  Assortment, Labels, Returns and claims, Messages, Finance, the non-invoiced
  report, Settings, Integrations, Users, Updates, Status, and Help itself. Each has
  an intro, **where things are** on the screen (the thing as it is labelled, and what
  it shows), **what can be done**, optional tips, a screenshot, and a link that opens
  the page. A part only an administrator sees (`adminOnly`) says so.
- **"Where do I find"**: a table of "I want to ..." against where to go, each a link.
- **A glossary** of the words the application uses (the statuses, safe mode, the
  non-invoiced record, and so on).

A part can be opened from a link: `/help#catalog` scrolls to it, `/help?tab=gdpr`
opens the other tab. A screenshot opens full size in a new tab.

The guide is text in code, not in the database: it describes what is on the screens
as of the commit it is in, and is changed with them.

## What keeps it honest

`frontend/src/guide/guide.test.ts` ties the guide to the application, so a page
cannot be added or removed without it noticing:

- the two languages have the same sections in the same order, the same questions
  pointing at the same pages, and the same glossary terms;
- every section that names a screenshot has the file in `frontend/public/guide`;
- every section's page exists as a route, every route and every menu item has a
  section, every Settings tab has one, and `adminOnly` is set on exactly the tabs
  only an administrator sees.

What no test can check is that the words still match the screens. Changing a page's
labels or what it does means rereading its section in both languages.

## Adding or changing a page

1. Write its section in `content.pl.ts` and `content.en.ts`: the same `id`, `group`,
   `path` and `image`, and the lookup rows it deserves.
2. Add a shot for it to `SHOTS` in `tools/guide/capture.mjs` (the file name, the
   address, the window height if it is long, and what to click first), and, if the page
   needs data to look like itself, the invented rows to `tools/guide/seed_sample.py`.
3. Make the picture (below) and look at it.
4. Run the frontend tests.

## The screenshots

The pictures in `frontend/public/guide/*.webp` are of an **invented shop**, never of
real data, because they are committed to Git and shipped with the interface as static
files, which the web container serves without a login. `tools/guide/` makes them:

```powershell
.\tools\guide\make.ps1                     # all of them
.\tools\guide\make.ps1 -Only dashboard,orders
```

It needs `backend\.venv` (`scripts\bootstrap.ps1`), Node 22 or later (the capture uses
its built-in `WebSocket` and `fetch`), and Chrome or Edge (`CHROME_PATH` names another
browser). Ports 8000 and 5173 must be free: it refuses to start otherwise, because a
running backend or interface would be photographed instead of the invented shop.

What it does, in order:

1. `seed_sample.py` makes a scratch SQLite database (`tools/guide/.work/guide.db`,
   not in Git) and fills it with made-up buyers, addresses, products, orders, parcels,
   labels, messages, returns, an administrator and two limited accounts, and a made-up
   data controller. It also draws the product pictures and writes a login token for the
   administrator to `.work/token.txt`.
2. `run_backend.py` starts the backend on that database, with the schedule off and its
   state set as a working one would report it.
3. `npm run dev` starts the interface.
4. `capture.mjs` drives a headless Chrome through the DevTools protocol (nothing to
   install), puts the token in the browser's storage, in Polish, the classic look and
   light mode, and takes one 1440 px WebP per screen into `frontend/public/guide`.
5. Everything it started is stopped again, and the browser's temporary profile, which
   held the token, is deleted.

`sample_env.py` sets `DATABASE_URL` and the pictures folder before anything of the
application is imported, so the seed and the server cannot reach the real database;
`GUIDE_WORK` moves the scratch folder. The seed's passwords and keys are made up, and
no button that calls a marketplace is pressed. Do not point `capture.mjs --base` at a
server running on real data.

A picture goes stale when its page changes: make it again with `-Only`. The guide
says under its introduction that the pictures show sample data.
