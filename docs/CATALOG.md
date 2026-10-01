# The assortment

"Asortyment" in the menu (`/catalog`): every offer in the seller's Allegro account, with its pictures,
and for each how the same product stands on Erli. **Read only**: nothing here changes an offer on a
marketplace. Decided with the owner on 2026-10-01 (`DECISIONS.md`); built the same day, never run
against the real Allegro or Erli (`PROJECT_STATUS.md`, "Not yet verified").

## What it is for

- One place that says what is for sale: name, SKU, price, stock, status, category and pictures.
- Pictures kept on the NAS, so Anvero does not depend on Allegro's servers to show a product, with
  the address on Allegro always kept beside the copy.
- A check of Erli against Allegro: Erli's offers are copies of Allegro's, so the assortment is read
  from Allegro only, and Erli is read to say whether each offer is there and whether its category is the
  same.

Not built, on purpose, until the owner asks: changing a price or a stock, publishing or ending an offer,
a product catalogue of Anvero's own, purchase prices and margins. Anything that writes goes through
`MarketplaceWriter` (safe mode), as every marketplace write does.

## Where the data comes from

| What | Source | Notes |
| --- | --- | --- |
| The offers | Allegro `GET /sale/offers`, not ended (`ACTIVE`, `INACTIVE`, `ACTIVATING`), 100 a page | name, SKU (`external.id`), price, stock, status, category id, cover |
| All the pictures of an offer | Allegro `GET /sale/product-offers/{id}`, `images` | one request per offer at every sync |
| The way to a category | Allegro `GET /sale/categories/{id}`, followed up through `parent.id` | read once per category per sync |
| Erli's products | Erli `POST /products/_search`, by `externalId`, 200 a page, only the fields shown | price in grosze |
| The pictures themselves | downloaded from the address Allegro gave | only from Allegro's and Erli's own hosts, https only, no redirects, at most 15 MB, kind taken from the bytes |

None of these was seen answering for real. They were built from the marketplaces' published
descriptions (`INTEGRATIONS.md`, "Assortment") and tested against fakes shaped like them. The scope
`allegro:api:sale:offers:read` is needed; whether the connected application has it is not known until the
first sync (a refusal is shown on the page as "The last read failed").

## What is kept

Three tables (`DATABASE.md`): `catalog_items` (one Allegro offer), `catalog_images` (its pictures:
Allegro's address and the copy on the NAS) and `catalog_listings` (the same product on Erli, tied to the
offer). An offer Allegro stops listing is kept, marked gone with the time, and so are its pictures; it
leaves the assortment but not the history.

## One sync

Run by the button on the page ("Pobierz z Allegro", needs `orders` at `manage`) and by the backend by
itself: the schedule looks at it as often as it looks at the imports, but reads only when
`CATALOG_SYNC_HOURS` (default 6) have passed since the last read, failed or not. It shares the import lock,
because it uses the same rotating Allegro token: while it runs, an order import waits for the next turn,
and a click on the import button is answered `409`.

1. **The offers.** The whole list is read before anything is stored, so a list that breaks halfway never
   makes the offers after the break look gone. Each offer is added or updated; one not listed any more is
   marked gone, and comes back if it reappears.
2. **The pictures.** Pictures without a copy are downloaded, at most `CATALOG_IMAGES_PER_RUN` (default 400)
   at a time, the ones never tried before the ones that failed. A picture is stored as
   `<sha256>.<jpg|png|webp|gif>`: the same picture of two offers is one file, and a changed picture is a new
   file. A recorded copy whose file has gone (a lost volume) is fetched again. A first sync of a few
   thousand pictures takes several runs and says how many are left.
3. **Erli.** If a key is set, every product is read and tied to an offer, the first rule that fits winning:
   the Allegro offer the product names in `externalReferences`; its `externalId` being the offer's id; the same SKU
   (only when no two offers share it). A product that matches nothing, or a second one for an offer, is
   counted, not stored. A listing whose product has gone is removed. Erli failing is noted and leaves the
   listings as they were; Allegro's part still stands.

### The category check

Allegro and Erli have category trees of their own, so their ids say nothing. The two leaves are compared by
name (ignoring case and spacing): **same** when they are named alike, **different** when not, **unknown**
when either side has none. Erli's own category is the first chain of the product's `categories`; when there is
none, the one the product came with (`externalCategories`, Allegro's first). The page shows both paths, so
a person can judge the "different" ones: two names for the same shelf are expected for some.

## The page

A compact list (two lines to a row, as the order list) with the category tree beside it, as decided from the
mockups of 2026-10-01 (variant A):

- the tree (Allegro's categories, with counts, a node holding everything below it);
- a search by name, SKU or offer number; status as pills (all, active, inactive, ended) and quick filters
  for what is missing (no picture, no SKU, and, once Erli is connected, not on Erli and another category
  on Erli), each with its count;
- the list sorted by name, price or stock; the thumbnail grows on hover as it does in the order list; stock
  as a chip (red at 0, amber to 3, green above);
- a row opens to every picture (the copy on the NAS where there is one, always a link to Allegro), the offer's
  number linking to Allegro, and the Erli product beside it with both category paths and the verdict.

What is shown is kept in the address (`status`, `flag`, `category`, `sort`, `desc`, `skip`, `limit`), so going
back restores it; the search is not.

## Pictures and who may see them

The files are served without a login by `GET /api/v1/catalog/images/{name}`: an `<img>` cannot send one,
the name is the hash of the bytes (so nothing to enumerate that is not already public), the pictures are
public on Allegro anyway, and the endpoint serves only names of that exact form. Everything else about
the assortment needs a login and the `orders` area (`API.md`): whoever works the orders works from the
assortment's pictures and stock.

## Where the pictures live

`CATALOG_IMAGES_DIR`, by default `backend/data/catalog_images` (not in Git). On the NAS this must be a
folder mounted into the backend container, or every update from Settings would throw the pictures away
and they would be downloaded again: see `DEPLOYMENT.md`, "The assortment's pictures". Not part of the
database dump: a lost folder costs a download, not data, and the next sync notices the missing files.

## Next, when asked

1. Run the first sync on the real account and look at what Allegro and Erli really send (the checks under
   "Not yet verified").
2. Show the assortment in the order (the offer an item belongs to) and use the local copy for the order
   list's thumbnails.
3. Own groups beside the marketplaces' categories, if the owner wants them.
4. Writing: price and stock to Allegro and Erli through `MarketplaceWriter`, one change at a time and then in bulk.
