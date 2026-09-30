# STYLE GUIDE

How Anvero looks, so that every page looks like one application. Decided with the owner on
2026-09-25 (see `DECISIONS.md`); the values live in `frontend/src/index.css` and the parts built
from them in `frontend/src/styles/theme.css`. A new page uses these; it does not invent its own.

## The look in one paragraph

A light grey canvas under white, rounded cards. A card's title is a band tinted for what the card
is. Text is 14px in a dark ink, with small labels in bold capitals and values in medium or semibold
weight. One teal accent. Buttons, fields and dropdowns look the same everywhere.

## Two looks

Anvero has two looks, picked in Settings: Classic (below) and Papier (warm cream, a brick accent,
Fraunces titles over Instrument Sans, larger radii). A look is only a set of variable values
(`:root.look-papier` and `:root.look-papier.dark` in `index.css`); the layout, spacing and parts
are the same in both. So a page never writes a colour, a font or a card radius itself: it uses the
variable, and must look right in all four combinations of look and mode.

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

Every colour a stylesheet uses is a variable from `index.css`, never a literal: besides the table
above, text on a solid fill (`--color-on-accent` on the accent, which is dark text in dark mode;
`--color-on-strong` on a fill that stays dark in both modes), the menu (`--color-nav-*`), notices and
banners (`--notice-<kind>-bg|border|fg`) and a few single ones listed in `DECISIONS.md`
(2026-09-30). A brand's own colours drawn in a component (a carrier's badge, the logo) are the
exception. This is what lets a second look be one more set of values.

**Tones** say what a band or a chip means: `--tone-blue-*` for the thing itself (an order, its
items, its buyer), `--tone-teal-*` for sending it (shipping, delivery, integrations),
`--tone-green-*` / `--tone-red-*` for money and health (paid or not, ok or a problem),
`--tone-amber-*` for notes and things waiting on someone. Put the class `tone-blue` (and so on) on a
card. Colour is for meaning: do not add a tone for decoration. `--tone-violet-*` exists only for the
"in progress" status chip.

**Status chips** (`.badge badge-<status>`, `.badge badge-allegro|erli`) are a tone's `-bg` with its `-fg`
text, never white on a solid colour: New blue, In progress violet, Ready to ship teal, Shipped amber,
Delivered green, Cancelled red.

## Type

The faces, the page title's size and weight and the card title's weight are variables
(`--font-body`, `--font-heading`, `--page-title-size`, `--page-title-weight`,
`--card-title-weight`), because Papier changes them; the values below are Classic's.

- Body 14px (`0.875rem`), line height 1.45, the system font stack (Papier: Instrument Sans).
- Page title (`.page-header h1`): 1.5rem, bold (Papier: Fraunces, 2rem, medium). Card title:
  0.9rem, bold, in its band (Papier: Fraunces, semibold).
- Small labels (`.label-caps`, table heads, `dt` in a card): 0.7rem, bold, capitals, letter spacing
  0.05em, `--color-muted-strong`.
- Values beside a label: 0.9rem, semibold. Names and the first line of an address: semibold.
- Headline figures (an amount paid, a total, a count): 1.25 to 1.75rem, bold.

## Cards

A card is `class="card"` (or `order-card` on the order page): white, 1px `--color-border`, radius
`--radius-card` (10px; Papier 16px), padding 1rem, no shadow. Its first `h2` or `h3` is the title band; where the title shares a
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

## Colour of a channel

Allegro, Erli and InPost each have a colour (`--channel-allegro|erli|inpost`, with `-bg`/`-fg` for a tinted band and
values for dark mode); the sender uses the accent. Use it as a small mark (a lettered square, a bar across a tile) or
a band with the tone classes `tone-allegro|erli|inpost|sender`, not as a fill for large areas or for text.

## Patterns for a list and for a status

- A long list is **compact**: a row is two lines (a value and, under it, a quieter `.cell-sub` line), so as
  many rows as possible are on the screen; what does not fit is folded into a count ("+3 more") with the whole
  in a tooltip. Where something came from is one coloured letter with its name on hover, not a word.

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
page in all four combinations of look and mode (`localStorage.setItem("theme-look", "papier")`,
`localStorage.setItem("theme-mode", "dark")`, or Settings, "Appearance and language").
