"""Reading the assortment from Allegro (and checking it against Erli), by hand or on a schedule.

One sync does, in this order (docs/CATALOG.md):

1. every Allegro offer that is not ended, with its pictures' addresses and its category's way from
   the top of the tree; an offer Allegro no longer lists is marked gone, not deleted;
2. the copies of the pictures: those without one, a limited number per run;
3. Erli's products, tied to the offers they copy, with their category set beside the offer's.

Allegro's part decides whether the sync worked: Erli failing is noted and leaves what Erli's side
held before. It shares the import lock, since it uses the same rotating Allegro token.
"""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.allegro.catalog import AllegroCatalogAdapter
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)
from app.integrations.erli.catalog import ErliCatalogAdapter
from app.models.catalog import (
    CATEGORY_DIFFERENT,
    CATEGORY_SAME,
    CATEGORY_UNKNOWN,
    MATCH_EXTERNAL_ID,
    MATCH_EXTERNAL_REFERENCE,
    MATCH_SKU,
    CatalogImage,
    CatalogItem,
    CatalogListing,
)
from app.models.marketplace_write import AppSetting
from app.models.order import OrderSource
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.catalog import (
    CatalogSyncNote,
    CatalogSyncResult,
    ErliProductSnapshot,
    OfferSnapshot,
)
from app.services import erli_settings
from app.services.allegro_import import build_allegro_client
from app.services.allegro_sync import ImportAlreadyRunning, import_lock
from app.services.catalog_images import ImageRejected, ImageStore

logger = logging.getLogger(__name__)

NOTE_KEY = "catalog_sync"
# a download that failed is kept as a short reason; the table cell it lands in is 255 wide
_MAX_ERROR = 255
# the pictures, and the offers, are committed in batches, so a sync cut short keeps what it did
_IMAGE_BATCH = 50
_OFFER_BATCH = 50
# a sync that left pictures to fetch is asked for again this soon, not after `catalog_sync_hours`
PENDING_PICTURES_RETRY = timedelta(minutes=15)


@dataclass
class CatalogProgress:
    """Where the sync that is running has got to, for the page's progress bar.

    Kept in memory, like the schedule's state: the sync runs in one process, so only that process can
    say. `phase` is `listing` (the offers' list, `total` unknown), `details` (each offer's pictures and
    category), `images` (the downloads) or `erli` (the products, `total` unknown). `done` counts within
    the phase. Written by the sync's thread and read by requests; single attribute writes, so no lock.
    """

    running: bool = False
    phase: str | None = None
    done: int = 0
    total: int | None = None
    started_at: datetime | None = None

    def begin(self) -> None:
        self.running = True
        self.phase = None
        self.done = 0
        self.total = None
        self.started_at = datetime.now(UTC)

    def enter(self, phase: str, total: int | None = None) -> None:
        self.phase = phase
        self.done = 0
        self.total = total

    def tick(self, done: int) -> None:
        self.done = done

    def end(self) -> None:
        self.running = False
        self.phase = None
        self.done = 0
        self.total = None
        self.started_at = None


# the one sync there can be at a time (they share the import lock)
catalog_progress = CatalogProgress()


def _name_key(name: str) -> str:
    return " ".join(name.casefold().split())


def category_match(offer_path: list[dict[str, str]], erli_path: list[dict[str, str]]) -> str:
    """Whether an Erli product sits in the same category as its Allegro offer.

    The two marketplaces have trees of their own, so the ids say nothing; the leaf's name does, or
    the whole way down when the leaf alone is ambiguous. SAME when the leaves are named alike."""
    if not offer_path or not erli_path:
        return CATEGORY_UNKNOWN
    same = _name_key(offer_path[-1]["name"]) == _name_key(erli_path[-1]["name"])
    return CATEGORY_SAME if same else CATEGORY_DIFFERENT


class CatalogSyncService:
    def __init__(
        self,
        repository: CatalogRepository,
        allegro: AllegroCatalogAdapter,
        erli: ErliCatalogAdapter | None = None,
        images: ImageStore | None = None,
        progress: CatalogProgress | None = None,
    ):
        self.progress = progress if progress is not None else catalog_progress
        self.repository = repository
        self.db = repository.db
        self.allegro = allegro
        self.erli = erli
        self.images = images or ImageStore()

    def sync(self, now: datetime | None = None) -> CatalogSyncResult:
        now = now or datetime.now(UTC)
        result = CatalogSyncResult()

        items = self._sync_offers(now, result)
        self._download_images(now, result)
        if self.erli is not None:
            self._sync_erli(items, now, result)

        logger.info(
            "Assortment synced: %d offers (%d new, %d gone), %d pictures fetched, %d pending, Erli %s",
            result.items,
            result.added,
            result.gone,
            result.images_downloaded,
            result.images_pending,
            f"{result.erli_matched} matched" if result.erli_error is None and self.erli else result.erli_error or "off",
        )
        return result

    # ---- 1. the offers ------------------------------------------------------

    def _sync_offers(self, now: datetime, result: CatalogSyncResult) -> dict[str, CatalogItem]:
        # the whole list is read before anything is stored: a list that fails halfway must not
        # make the offers after the break look gone
        self.progress.enter("listing")
        offers: list[OfferSnapshot] = []
        for listed in self.allegro.iter_offers():
            offers.append(listed)
            self.progress.tick(len(offers))
        known = self.repository.items_by_offer()
        seen: set[str] = set()

        self.progress.enter("details", total=len(offers))
        for index, offer in enumerate(offers, start=1):
            seen.add(offer.offer_id)
            item = known.get(offer.offer_id)
            if item is None:
                item = CatalogItem(source=OrderSource.ALLEGRO, offer_id=offer.offer_id)
                self.db.add(item)
                known[offer.offer_id] = item
                result.added += 1
            self._apply_offer(item, offer, now, result)
            self.progress.tick(index)
            if index % _OFFER_BATCH == 0:
                self.db.commit()

        for offer_id, item in known.items():
            if offer_id not in seen and item.gone_at is None:
                item.gone_at = now
                result.gone += 1

        result.items = len(offers)
        self.db.commit()
        return known

    def _apply_offer(self, item: CatalogItem, offer: OfferSnapshot, now: datetime, result: CatalogSyncResult) -> None:
        item.name = offer.name[:512]
        item.sku = offer.sku
        item.price = offer.price
        item.currency = offer.currency
        item.stock = offer.stock
        item.status = offer.status
        item.last_seen_at = now
        item.gone_at = None

        path = self._category_path(item, offer)
        item.category_id = offer.category_id
        item.category_path = path
        item.category_ids = "|" + "|".join(step["id"] for step in path) + "|" if path else ""

        try:
            urls = self.allegro.fetch_images(offer.offer_id)
        except IntegrationAuthError:
            raise
        except IntegrationUnavailable as exc:
            # keep the pictures it had; the cover the list gave stands in for a new offer's
            logger.warning("Offer %s: pictures unreadable: %s", offer.offer_id, exc)
            result.details_failed += 1
            urls = offer.image_urls if not item.images else None
        if urls is not None:
            self._apply_images(item, urls)

    def _category_path(self, item: CatalogItem, offer: OfferSnapshot) -> list[dict[str, str]]:
        if offer.category_id is None:
            return []
        try:
            return self.allegro.category_path(offer.category_id)
        except IntegrationAuthError:
            raise
        except IntegrationUnavailable as exc:
            logger.warning("Category %s unreadable: %s", offer.category_id, exc)
            if item.category_id == offer.category_id and item.category_path:
                return list(item.category_path)
            return [{"id": offer.category_id, "name": offer.category_id}]

    @staticmethod
    def _apply_images(item: CatalogItem, urls: tuple[str, ...]) -> None:
        """Make the offer's pictures these addresses, in this order. A picture whose address is
        unchanged keeps its copy; one with a new address starts again, and the old copy is simply
        no longer shown."""
        by_position = {image.position: image for image in item.images}
        for position, url in enumerate(urls):
            image = by_position.get(position)
            if image is None:
                item.images.append(CatalogImage(position=position, url=url))
            elif image.url != url:
                image.url = url
                image.file_name = image.content_type = image.byte_size = image.fetched_at = None
                image.fetch_error = None
        for position, image in by_position.items():
            if position >= len(urls):
                item.images.remove(image)

    # ---- 2. the pictures ----------------------------------------------------

    def _download_images(self, now: datetime, result: CatalogSyncResult) -> None:
        # a copy recorded but gone from the folder (a lost volume) is a picture to fetch again
        for image in self.repository.recorded_images():
            if not self.images.has(image.file_name):
                image.file_name = image.content_type = image.byte_size = image.fetched_at = None
        self.db.flush()

        pending = list(self.repository.pending_images())
        budget = pending[: settings.catalog_images_per_run]
        self.progress.enter("images", total=len(budget))
        for count, image in enumerate(budget, start=1):
            self.progress.tick(count - 1)
            try:
                stored = self.images.download(image.url)
            except ImageRejected as exc:
                image.fetch_error = str(exc)[:_MAX_ERROR]
                result.images_failed += 1
            except OSError as exc:
                # the folder cannot be written: every further picture would fail the same way
                image.fetch_error = f"cannot write: {type(exc).__name__}"[:_MAX_ERROR]
                result.images_failed += 1
                result.notes.append(f"The pictures folder is not writable: {exc}")
                break
            else:
                image.file_name = stored.file_name
                image.content_type = stored.content_type
                image.byte_size = stored.byte_size
                image.fetched_at = now
                image.fetch_error = None
                result.images_downloaded += 1
            if count % _IMAGE_BATCH == 0:
                self.db.commit()
        self.db.commit()
        result.images_pending = len(pending) - result.images_downloaded

    # ---- 3. Erli ------------------------------------------------------------

    def _sync_erli(self, items: dict[str, CatalogItem], now: datetime, result: CatalogSyncResult) -> None:
        assert self.erli is not None
        self.progress.enter("erli")
        try:
            products: list[ErliProductSnapshot] = []
            for product in self.erli.iter_products():
                products.append(product)
                self.progress.tick(len(products))
        except IntegrationError as exc:
            # the listings it kept last time stand, and Allegro's part stays good
            logger.warning("Assortment: Erli unreadable: %s", exc)
            result.erli_error = (str(exc) or type(exc).__name__)[:_MAX_ERROR]
            return

        current = {offer_id: item for offer_id, item in items.items() if item.gone_at is None}
        by_sku: dict[str, CatalogItem] = {}
        ambiguous: set[str] = set()
        for item in current.values():
            if item.sku:
                if item.sku in by_sku:
                    ambiguous.add(item.sku)
                by_sku[item.sku] = item

        matched: dict[str, tuple[ErliProductSnapshot, str]] = {}
        unmatched = 0
        for product in products:
            found = self._match(product, current, by_sku, ambiguous)
            if found is None:
                unmatched += 1
                continue
            item, how = found
            if item.offer_id in matched:
                # two Erli products for one offer: the first stands, the rest are not the offer's copy
                unmatched += 1
                continue
            matched[item.offer_id] = (product, how)

        for item in items.values():
            existing = next((entry for entry in item.listings if entry.source is OrderSource.ERLI), None)
            hit = matched.get(item.offer_id)
            if hit is None:
                if existing is not None:
                    item.listings.remove(existing)
                continue
            product, how = hit
            if existing is None:
                existing = CatalogListing(source=OrderSource.ERLI)
                item.listings.append(existing)
            erli_path = list(product.category_path or product.source_category_path)
            existing.external_id = product.external_id
            existing.matched_by = how
            existing.price = product.price
            existing.currency = product.currency
            existing.stock = product.stock
            existing.status = product.status
            existing.category_path = erli_path
            existing.category_match = category_match(item.category_path, erli_path)
            existing.seen_at = now

        result.erli_products = len(products)
        result.erli_matched = len(matched)
        result.erli_unmatched = unmatched
        self.db.commit()

    @staticmethod
    def _match(
        product: ErliProductSnapshot,
        current: dict[str, CatalogItem],
        by_sku: dict[str, CatalogItem],
        ambiguous: set[str],
    ) -> tuple[CatalogItem, str] | None:
        """The offer an Erli product copies: the one it names itself, then the one whose id it
        carries as its own, then the one with the same SKU (when no two offers share it)."""
        for offer_id in product.allegro_offer_ids:
            if offer_id in current:
                return current[offer_id], MATCH_EXTERNAL_REFERENCE
        if product.external_id in current:
            return current[product.external_id], MATCH_EXTERNAL_ID
        if product.sku and product.sku not in ambiguous and product.sku in by_sku:
            return by_sku[product.sku], MATCH_SKU
        return None


# ---- running it ---------------------------------------------------------------


def build_catalog_sync_service(db: Session) -> CatalogSyncService:
    erli_client = erli_settings.build_erli_client(db)
    return CatalogSyncService(
        CatalogRepository(db),
        AllegroCatalogAdapter(build_allegro_client(db)),
        ErliCatalogAdapter(erli_client) if erli_client.is_configured else None,
    )


def read_note(db: Session) -> CatalogSyncNote | None:
    row = db.get(AppSetting, NOTE_KEY)
    if row is None:
        return None
    try:
        return CatalogSyncNote.model_validate(json.loads(row.value))
    except (ValueError, TypeError):
        return None


def _write_note(db: Session, note: CatalogSyncNote) -> None:
    value = note.model_dump_json()
    row = db.get(AppSetting, NOTE_KEY)
    if row is None:
        db.add(AppSetting(key=NOTE_KEY, value=value))
    else:
        row.value = value
    db.commit()


def _sync_and_note(db: Session) -> CatalogSyncResult:
    """The sync itself, with the lock already held by the caller: noted when it ends, either way."""
    catalog_progress.begin()
    try:
        service = build_catalog_sync_service(db)
        try:
            result = service.sync()
        except IntegrationNotConfigured:
            raise
        except Exception as exc:
            db.rollback()
            _write_note(
                db,
                CatalogSyncNote(at=datetime.now(UTC), error=(str(exc) or type(exc).__name__)[:_MAX_ERROR]),
            )
            raise
        _write_note(
            db,
            CatalogSyncNote(
                at=datetime.now(UTC),
                items=result.items,
                added=result.added,
                gone=result.gone,
                images_downloaded=result.images_downloaded,
                images_pending=result.images_pending,
                erli_error=result.erli_error,
                erli_matched=result.erli_matched if result.erli_products is not None else None,
                erli_unmatched=result.erli_unmatched if result.erli_products is not None else None,
            ),
        )
        return result
    finally:
        catalog_progress.end()


def run_catalog_sync(db: Session) -> CatalogSyncResult:
    """Run one sync and wait for it, sharing the import lock so it never races a token refresh.
    Raises ImportAlreadyRunning without waiting if an import or another sync is under way; an error
    of the sync's own is noted and raised again. What the schedule uses."""
    if not import_lock.acquire(blocking=False):
        raise ImportAlreadyRunning
    try:
        return _sync_and_note(db)
    finally:
        import_lock.release()


def start_catalog_sync(db: Session) -> None:
    """Start one sync in the background and return at once, what the page's button uses: a first
    sync takes minutes, longer than a request may wait (the proxy gives up after 300 seconds).

    Raises ImportAlreadyRunning without waiting if an import or another sync is under way, and
    IntegrationNotConfigured when there is no Allegro account to read. How it goes is shown by
    `catalog_progress` while it runs and noted when it ends."""
    if not import_lock.acquire(blocking=False):
        raise ImportAlreadyRunning
    try:
        if not build_allegro_client(db).is_configured:
            raise IntegrationNotConfigured("Allegro is not configured")
    except BaseException:
        import_lock.release()
        raise
    # running from now, so the page's first look finds it so
    catalog_progress.begin()

    def work() -> None:
        own = SessionLocal()
        try:
            _sync_and_note(own)
        except Exception:
            # the reason is noted for the page; the log keeps the trace
            logger.exception("Assortment sync failed")
        finally:
            own.close()
            import_lock.release()

    threading.Thread(target=work, name="catalog-sync", daemon=True).start()


def sync_is_due(db: Session, now: datetime | None = None) -> bool:
    """Whether the schedule should read the assortment now: never read, or last read longer ago
    than `catalog_sync_hours`, or, when the last read left pictures to download, a quarter of an
    hour ago. A failed run counts as a run, so a broken connection is not hammered every fifteen
    minutes."""
    note = read_note(db)
    if note is None:
        return True
    now = now or datetime.now(UTC)
    wait = timedelta(hours=settings.catalog_sync_hours)
    if note.error is None and note.images_pending:
        wait = min(wait, PENDING_PICTURES_RETRY)
    return now - note.at >= wait


def _scheduled_catalog_run() -> None:
    """One scheduled sync, on its own session. Never raises."""
    db = SessionLocal()
    try:
        if not build_allegro_client(db).is_configured:
            return
        if not sync_is_due(db):
            return
        result = run_catalog_sync(db)
        logger.info("Scheduled assortment sync: %d offers, %d pictures fetched", result.items, result.images_downloaded)
    except ImportAlreadyRunning:
        logger.info("Scheduled assortment sync skipped: another import is running")
    except IntegrationError as exc:
        logger.warning("Scheduled assortment sync failed: %s", exc)
    except Exception:
        logger.exception("Scheduled assortment sync failed")
    finally:
        db.close()
