# STYLE GUIDE

How Anvero looks, so that every page looks like one application. Decided with the owner on
2026-09-25 (see `DECISIONS.md`); the values live in `frontend/src/index.css` and the parts built
from them in `frontend/src/styles/theme.css`. A new page uses these; it does not invent its own.

## The look in one paragraph

A light grey canvas under white, rounded cards. A card's title is a band tinted for what the card
is. Text is 14px in a dark ink, with small labels in bold capitals and values in medium or semibold
weight. One teal accent. Buttons, fields and dropdowns look the same everywhere.

## Colour

| Token | Light | Use |
| --- | --- | --- |
| `--color-canvas` | `#eef0f3` | the page behind the cards (also `body` and `.app-content`) |
| `--color-bg` | `#ffffff` | a card, a field, a table |
| `--color-surface-alt` | `#f3f5f7` | a strip inside a card: a table's head row, a hovered button |
| `--color-text` | `#111827` | body text |
| `--color-muted` | `#4b5563` | secondary text; never lighter than this |
| `--color-muted-strong` | `#374151` | small labels |
| `--color-heading` | `#030712` | titles |
| `--color-border` | `#d5d9e0` | the edge of a card or a field |
| `--color-divider` | `#e5e7eb` | a rule between rows |
| `--color-accent` | `#0d7377` | the one accent: the main button, the chosen tab, a link |

Dark mode has its own value for each, set once in `:root.dark`; a stylesheet never writes a colour
twice for the two modes, it uses the token.

**Tones** say what a band or a chip means: `--tone-blue-*` for the thing itself (an order, its
items, its buyer), `--tone-teal-*` for sending it (shipping, delivery, integrations),
`--tone-green-*` / `--tone-red-*` for money and health (paid or not, ok or a problem),
`--tone-amber-*` for notes and things waiting on someone. Put the class `tone-blue` (and so on) on a
card. Colour is for meaning: do not add a tone for decoration.

## Type

- Body 14px (`0.875rem`), line height 1.45, the system font stack.
- Page title (`.page-header h1`): 1.5rem, bold. Card title: 0.9rem, bold, in its band.
- Small labels (`.label-caps`, table heads, `dt` in a card): 0.7rem, bold, capitals, letter spacing
  0.05em, `--color-muted-strong`.
- Values beside a label: 0.9rem, semibold. Names and the first line of an address: semibold.
- Headline figures (an amount paid, a total, a count): 1.25 to 1.75rem, bold.

## Cards

A card is `class="card"` (or `order-card` on the order page): white, 1px `--color-border`, radius
10px, padding 1rem, no shadow. Its first `h2` or `h3` is the title band; where the title shares a
row with a button, that row is `class="card-head"`. Add a tone class for the band's colour.
Content that needs to sit in a card without a frame (a tab's body, a folded section) is
`CardShell` with `embedded`.

A table sits in `.table-wrapper` (a card of its own); its head row is a grey strip of small
capitals (`thead th` in `index.css`).

## Controls

Written once in `index.css` with `:where()`, which has no weight of its own, so a rule that must
differ still can:

- **Button:** outlined, radius 8px, padding 0.4rem 0.9rem, medium weight. `type="submit"` is the
  filled accent button: the one action a form is for. Give a page action its own class only to
  say it is the main one.
- **Field:** white, 1px border, radius 8px; focus is the accent border with a soft ring.
- **Dropdown (`select`):** the same as a field, with its own arrow. The browser's is switched off, so
  a stylesheet must **not** write `background:` on a `select` (it wipes the arrow): use
  `background-color`.
- **Tabs and quick filters:** pills, the chosen one filled with the accent (`theme.css`).
- Do not restyle a control in a page's stylesheet (padding, border, radius, colour, font size);
  if it looks wrong, fix the shared rule.

## Patterns for a page of settings

- One setting is a **row** (`.setting-row`): the name and what it does on the left, its control on the right.
- Something with a state (a connection, a switch) shows it as a **dot and a line** (`.status-dot`, green when set up,
  grey when not) on a tile or in a band, not as a paragraph further down.
- Many things that each need a form are **tiles** with the chosen one opened below, not a long column of forms.

## Patterns for a list and for a status

- A list that is worked through (the inbox) is grouped by day under small capital headings with a count,
  and a row that needs someone says so with a **chip** (`inbox-chip-amber` up to a day, `-red` after), not with
  colour alone. Something that goes with the row (an order) is a blue chip.
- A page that answers "is all well?" opens with **one bar** whose colour is the worst state and which names what
  is wrong and where to put it right; below it a **tile** for each part (the edge coloured by its state, one line
  of how it stands, the rest folded under "Details"), and a **timeline** of what happened last.

## Shape of a page

`.page-header` (title, subtitle, and what the page offers on the right) on the canvas, then cards.
A page is padded 2rem at the sides (1rem below 768px). Below 768px the menu is a strip and the
page's cards stack.

## When you change the look

Change the token or the shared rule, not the page. Record it in `DECISIONS.md`, and look at every
page in both modes (`localStorage.setItem("theme-mode", "dark")`).
