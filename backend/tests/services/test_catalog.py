"""Reading the assortment: the offers kept, the pictures fetched, Erli's products tied to them."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.core.config import settings
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.models.catalog import CatalogItem
from app.models.order import OrderSource
from app.repositories.catalog_repository import CatalogRepository
from app.schemas.catalog import ErliProductSnapshot, OfferSnapshot
from app.services import catalog as catalog_service
from app.services.allegro_sync import ImportAlreadyRunning, import_lock
from app.services.catalog import (
    CatalogSyncService,
    category_match,
    run_catalog_sync,
    sync_is_due,
)
from app.services.catalog_images import ImageStore

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n"
KITCHEN = [{"id": "1", "name": "Dom i ogród"}, {"id": "20", "name": "Kuchnia"}, {"id": "300", "name": "Kubki"}]


def pic(n: int) -> str:
    return f"https://a.allegroimg.com/original/{n}"


def offer(offer_id="7001", **overrides) -> OfferSnapshot:
    fields = {
        "offer_id": offer_id,
        "name": f"Oferta {offer_id}",
        "status": "ACTIVE",
        "sku": f"SKU-{offer_id}",
        "price": Decimal("49.00"),
        "currency": "PLN",
        "stock": 5,
        "category_id": "300",
        "image_urls": (pic(1),),
    }
    fields.update(overrides)
    return OfferSnapshot(**fields)


def product(external_id="7001", **overrides) -> ErliProductSnapshot:
    fields = {
        "external_id": external_id,
        "status": "ACTIVE",
        "sku": None,
        "price": Decimal("52.00"),
        "currency": "PLN",
        "stock": 4,
        "allegro_offer_ids": (),
        "category_path": ({"id": "9", "name": "Kubki"},),
    }
    fields.update(overrides)
    return ErliProductSnapshot(**fields)


class FakeAllegro:
    def __init__(self, offers=(), images=None, categories=None):
        self.offers = list(offers)
        # what fetch_images answers by offer id: a tuple of addresses, or an exception to raise;
        # an offer not named has the cover it was listed with
        self.images = images or {}
        self.categories = categories if categories is not None else {"300": KITCHEN}
        self.list_error: Exception | None = None

    def iter_offers(self):
        for index, entry in enumerate(self.offers):
            if self.list_error is not None and index == 1:
                raise self.list_error
            yield entry

    def fetch_images(self, offer_id):
        answer = self.images.get(offer_id)
        if isinstance(answer, Exception):
            raise answer
        if answer is not None:
            return answer
        return next(o.image_urls for o in self.offers if o.offer_id == offer_id)

    def category_path(self, category_id):
        answer = self.categories[category_id]
        if isinstance(answer, Exception):
            raise answer
        return list(answer)


class FakeErli:
    def __init__(self, products=(), error: Exception | None = None):
        self.products = list(products)
        self.error = error

    def iter_products(self):
        if self.error is not None:
            raise self.error
        yield from self.products


@pytest.fixture
def requests():
    return []


@pytest.fixture
def store(tmp_path, requests):
    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(str(request.url))
        if request.url.path.endswith("/broken"):
            return httpx2.Response(404)
        # every address a picture of its own, so two are never one file
        return httpx2.Response(200, content=PNG + request.url.path.encode())

    return ImageStore(tmp_path, httpx2.Client(transport=httpx2.MockTransport(handler)))


def service(session, store, allegro, erli=None):
    return CatalogSyncService(CatalogRepository(session), allegro, erli, store)


def items(session) -> dict[str, CatalogItem]:
    session.expire_all()
    return CatalogRepository(session).items_by_offer()


# --- the offers -----------------------------------------------------------------------


def test_the_first_sync_keeps_every_offer_with_its_category_and_pictures(session, store):
    allegro = FakeAllegro([offer("1", image_urls=(pic(1),)), offer("2", category_id=None)], images={"1": (pic(1), pic(2))})

    result = service(session, store, allegro).sync(NOW)

    assert (result.items, result.added, result.gone) == (2, 2, 0)
    kept = items(session)
    first = kept["1"]
    assert (first.name, first.sku, first.price, first.stock, first.status) == ("Oferta 1", "SKU-1", Decimal("49.00"), 5, "ACTIVE")
    assert first.category_id == "300"
    assert [step["name"] for step in first.category_path] == ["Dom i ogród", "Kuchnia", "Kubki"]
    assert first.category_ids == "|1|20|300|"
    assert [image.url for image in first.images] == [pic(1), pic(2)]
    assert kept["2"].category_path == [] and kept["2"].category_ids == ""
    assert first.gone_at is None and first.last_seen_at.astimezone(UTC) == NOW


def test_a_later_sync_updates_the_offer_and_adds_no_second_row(session, store):
    allegro = FakeAllegro([offer("1")])
    service(session, store, allegro).sync(NOW)

    allegro.offers = [offer("1", name="Nowa nazwa", price=Decimal("59.90"), stock=0, status="INACTIVE")]
    result = service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert (result.items, result.added) == (1, 0)
    (kept,) = items(session).values()
    assert (kept.name, kept.price, kept.stock, kept.status) == ("Nowa nazwa", Decimal("59.90"), 0, "INACTIVE")


def test_an_offer_allegro_stops_listing_is_marked_gone_and_comes_back(session, store):
    allegro = FakeAllegro([offer("1"), offer("2")])
    service(session, store, allegro).sync(NOW)

    allegro.offers = [offer("1")]
    result = service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert result.gone == 1
    kept = items(session)
    assert kept["2"].gone_at is not None and kept["1"].gone_at is None
    # kept with its pictures, not deleted
    assert len(kept["2"].images) == 1

    allegro.offers = [offer("1"), offer("2")]
    result = service(session, store, allegro).sync(NOW + timedelta(hours=12))

    assert result.gone == 0 and result.added == 0
    assert items(session)["2"].gone_at is None


def test_a_list_that_breaks_halfway_stores_nothing_and_loses_no_offer(session, store):
    allegro = FakeAllegro([offer("1"), offer("2")])
    service(session, store, allegro).sync(NOW)

    allegro.list_error = IntegrationUnavailable("Allegro offers: 503")
    with pytest.raises(IntegrationUnavailable):
        service(session, store, allegro).sync(NOW + timedelta(hours=6))

    kept = items(session)
    assert all(item.gone_at is None for item in kept.values())


def test_a_refused_read_ends_the_sync(session, store):
    allegro = FakeAllegro([offer("1")], images={"1": IntegrationAuthError("denied")})

    with pytest.raises(IntegrationAuthError):
        service(session, store, allegro).sync(NOW)


def test_a_picture_list_that_cannot_be_read_keeps_the_pictures_it_had(session, store):
    allegro = FakeAllegro([offer("1")], images={"1": (pic(1), pic(2))})
    service(session, store, allegro).sync(NOW)

    allegro.images = {"1": IntegrationUnavailable("503")}
    result = service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert result.details_failed == 1
    assert [image.url for image in items(session)["1"].images] == [pic(1), pic(2)]


def test_a_new_offer_whose_pictures_cannot_be_read_gets_the_cover_of_the_list(session, store):
    allegro = FakeAllegro([offer("1", image_urls=(pic(7),))], images={"1": IntegrationUnavailable("503")})

    service(session, store, allegro).sync(NOW)

    assert [image.url for image in items(session)["1"].images] == [pic(7)]


def test_a_category_that_cannot_be_read_keeps_the_path_it_had_or_falls_back_to_its_id(session, store):
    allegro = FakeAllegro([offer("1"), offer("2", category_id="999")], categories={"300": KITCHEN, "999": KITCHEN})
    service(session, store, allegro).sync(NOW)

    allegro.categories = {"300": IntegrationUnavailable("503"), "999": IntegrationUnavailable("503")}
    allegro.offers = [offer("1"), offer("2", category_id="888")]
    allegro.categories["888"] = IntegrationUnavailable("503")
    service(session, store, allegro).sync(NOW + timedelta(hours=6))

    kept = items(session)
    assert [step["name"] for step in kept["1"].category_path] == ["Dom i ogród", "Kuchnia", "Kubki"]
    assert kept["2"].category_path == [{"id": "888", "name": "888"}]


# --- the pictures ---------------------------------------------------------------------


def test_the_pictures_are_downloaded_and_recorded(session, store, requests):
    allegro = FakeAllegro([offer("1")], images={"1": (pic(1), pic(2))})

    result = service(session, store, allegro).sync(NOW)

    assert (result.images_downloaded, result.images_failed, result.images_pending) == (2, 0, 0)
    first, second = items(session)["1"].images
    assert first.file_name != second.file_name
    assert store.has(first.file_name) and store.has(second.file_name)
    assert (first.content_type, first.fetch_error) == ("image/png", None)
    assert first.fetched_at is not None


def test_a_picture_already_held_is_not_fetched_again(session, store, requests):
    allegro = FakeAllegro([offer("1")])
    service(session, store, allegro).sync(NOW)
    assert len(requests) == 1

    service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert len(requests) == 1


def test_a_changed_address_is_fetched_afresh_and_the_old_copy_is_dropped_from_the_record(session, store, requests):
    allegro = FakeAllegro([offer("1", image_urls=(pic(1),))])
    service(session, store, allegro).sync(NOW)
    old = items(session)["1"].images[0].file_name

    allegro.offers = [offer("1", image_urls=(pic(2),))]
    service(session, store, allegro).sync(NOW + timedelta(hours=6))

    (image,) = items(session)["1"].images
    assert image.url == pic(2) and image.file_name not in (None, old)
    assert len(requests) == 2


def test_pictures_an_offer_no_longer_has_are_forgotten(session, store):
    allegro = FakeAllegro([offer("1")], images={"1": (pic(1), pic(2), pic(3))})
    service(session, store, allegro).sync(NOW)

    allegro.images = {"1": (pic(1),)}
    service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert [image.url for image in items(session)["1"].images] == [pic(1)]


def test_one_run_downloads_only_so_many_and_the_next_goes_on(session, store, monkeypatch):
    monkeypatch.setattr(settings, "catalog_images_per_run", 2)
    allegro = FakeAllegro([offer("1")], images={"1": tuple(pic(n) for n in range(5))})

    first = service(session, store, allegro).sync(NOW)
    assert (first.images_downloaded, first.images_pending) == (2, 3)

    second = service(session, store, allegro).sync(NOW + timedelta(hours=6))
    assert (second.images_downloaded, second.images_pending) == (2, 1)


def test_a_failed_download_is_noted_and_tried_again_after_the_fresh_ones(session, store):
    allegro = FakeAllegro([offer("1")], images={"1": ("https://a.allegroimg.com/broken", pic(2))})

    result = service(session, store, allegro).sync(NOW)

    assert (result.images_downloaded, result.images_failed, result.images_pending) == (1, 1, 1)
    broken, fine = items(session)["1"].images
    assert broken.file_name is None and broken.fetch_error == "HTTP 404"
    assert fine.file_name is not None

    # still broken, still noted, and the good one is not fetched again
    second = service(session, store, allegro).sync(NOW + timedelta(hours=6))
    assert (second.images_downloaded, second.images_failed) == (0, 1)


def test_a_picture_whose_file_has_gone_is_fetched_again(session, store, tmp_path):
    allegro = FakeAllegro([offer("1")])
    service(session, store, allegro).sync(NOW)
    (image,) = items(session)["1"].images
    store.path_for(image.file_name).unlink()

    result = service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert result.images_downloaded == 1
    assert store.has(items(session)["1"].images[0].file_name)


def test_an_address_outside_the_marketplaces_is_never_requested(session, store, requests):
    allegro = FakeAllegro([offer("1", image_urls=("https://evil.example/x.png",))])

    result = service(session, store, allegro).sync(NOW)

    assert result.images_failed == 1 and requests == []
    assert items(session)["1"].images[0].fetch_error == "address not allowed"


def test_pictures_of_gone_offers_are_not_fetched(session, store, requests):
    allegro = FakeAllegro([offer("1")])
    service(session, store, allegro)._sync_offers(NOW, catalog_service.CatalogSyncResult())
    allegro.offers = []
    service(session, store, allegro).sync(NOW + timedelta(hours=6))

    assert requests == []


# --- Erli -----------------------------------------------------------------------------


def erli_sync(session, store, offers, products, **kwargs):
    allegro = FakeAllegro(offers)
    erli = FakeErli(products, **kwargs)
    return service(session, store, allegro, erli).sync(NOW)


def listing(session, offer_id):
    return next((entry for entry in items(session)[offer_id].listings if entry.source is OrderSource.ERLI), None)


def test_a_product_naming_its_offer_is_tied_to_it(session, store):
    result = erli_sync(session, store, [offer("7001")], [product("zzz", allegro_offer_ids=("7001",))])

    assert (result.erli_products, result.erli_matched, result.erli_unmatched, result.erli_error) == (1, 1, 0, None)
    entry = listing(session, "7001")
    assert (entry.external_id, entry.matched_by) == ("zzz", "EXTERNAL_REFERENCE")
    assert (entry.price, entry.stock, entry.status, entry.currency) == (Decimal("52.00"), 4, "ACTIVE", "PLN")


def test_a_product_whose_id_is_the_offers_is_tied_to_it(session, store):
    erli_sync(session, store, [offer("7001")], [product("7001")])

    assert listing(session, "7001").matched_by == "EXTERNAL_ID"


def test_a_product_with_the_same_sku_is_tied_to_it(session, store):
    erli_sync(session, store, [offer("7001", sku="KUB-350")], [product("other", sku="KUB-350")])

    assert listing(session, "7001").matched_by == "SKU"


def test_a_sku_two_offers_share_ties_nothing(session, store):
    result = erli_sync(
        session,
        store,
        [offer("1", sku="SAME"), offer("2", sku="SAME")],
        [product("other", sku="SAME")],
    )

    assert (result.erli_matched, result.erli_unmatched) == (0, 1)


def test_the_reference_wins_over_the_id_and_the_id_over_the_sku(session, store):
    erli_sync(
        session,
        store,
        [offer("1", sku="S1"), offer("2", sku="S2")],
        [product("2", allegro_offer_ids=("1",), sku="S2")],
    )

    assert listing(session, "1") is not None and listing(session, "2") is None


def test_a_second_product_for_one_offer_is_left_over(session, store):
    result = erli_sync(session, store, [offer("1")], [product("1"), product("dup", allegro_offer_ids=("1",))])

    assert (result.erli_matched, result.erli_unmatched) == (1, 1)
    assert listing(session, "1").external_id == "1"


def test_a_product_of_no_offer_is_counted(session, store):
    result = erli_sync(session, store, [offer("1")], [product("stranger")])

    assert (result.erli_matched, result.erli_unmatched) == (0, 1)
    assert listing(session, "1") is None


def test_a_gone_offer_is_not_matched(session, store):
    allegro = FakeAllegro([offer("1")])
    service(session, store, allegro).sync(NOW)
    allegro.offers = []

    result = service(session, store, allegro, FakeErli([product("1")])).sync(NOW + timedelta(hours=6))

    assert result.erli_unmatched == 1 and listing(session, "1") is None


def test_the_listing_is_refreshed_and_removed_when_the_product_goes(session, store):
    allegro = FakeAllegro([offer("1")])
    erli = FakeErli([product("1", price=Decimal("10.00"))])
    service(session, store, allegro, erli).sync(NOW)

    erli.products = [product("1", price=Decimal("12.50"), stock=0)]
    service(session, store, allegro, erli).sync(NOW + timedelta(hours=6))
    entry = listing(session, "1")
    assert (entry.price, entry.stock) == (Decimal("12.50"), 0)

    erli.products = []
    service(session, store, allegro, erli).sync(NOW + timedelta(hours=12))
    assert listing(session, "1") is None


def test_erli_failing_leaves_what_it_held_and_does_not_fail_the_sync(session, store):
    allegro = FakeAllegro([offer("1")])
    erli = FakeErli([product("1")])
    service(session, store, allegro, erli).sync(NOW)

    erli.error = IntegrationUnavailable("Erli product search: 503")
    result = service(session, store, allegro, erli).sync(NOW + timedelta(hours=6))

    assert result.erli_error == "Erli product search: 503"
    assert result.items == 1 and result.erli_products is None
    assert listing(session, "1") is not None


def test_without_erli_nothing_is_said_of_it(session, store):
    result = service(session, store, FakeAllegro([offer("1")])).sync(NOW)

    assert result.erli_products is None and result.erli_error is None and listing(session, "1") is None


# --- the category compared ------------------------------------------------------------


def test_the_same_leaf_name_is_the_same_category_whatever_the_case_or_spacing():
    assert category_match(KITCHEN, [{"id": "9", "name": "  kubki "}]) == "SAME"


def test_another_leaf_is_a_different_category():
    assert category_match(KITCHEN, [{"id": "9", "name": "Szklanki"}]) == "DIFFERENT"


def test_a_missing_path_on_either_side_is_unknown():
    assert category_match([], [{"id": "9", "name": "Kubki"}]) == "UNKNOWN"
    assert category_match(KITCHEN, []) == "UNKNOWN"


def test_a_listing_records_whether_its_category_matches(session, store):
    erli_sync(
        session,
        store,
        [offer("1"), offer("2"), offer("3", category_id=None)],
        [
            product("1"),
            product("2", category_path=({"id": "5", "name": "Talerze"},)),
            product("3", category_path=()),
        ],
    )

    assert listing(session, "1").category_match == "SAME"
    assert listing(session, "2").category_match == "DIFFERENT"
    assert listing(session, "3").category_match == "UNKNOWN"


def test_the_category_a_product_came_with_stands_in_for_a_missing_own(session, store):
    erli_sync(session, store, [offer("1")], [product("1", category_path=(), source_category_path=({"id": "300", "name": "Kubki"},))])

    entry = listing(session, "1")
    assert entry.category_path == [{"id": "300", "name": "Kubki"}] and entry.category_match == "SAME"


# --- running it -----------------------------------------------------------------------


@pytest.fixture
def wired(session, store, monkeypatch):
    allegro, erli = FakeAllegro([offer("1")]), FakeErli([product("1")])
    monkeypatch.setattr(
        catalog_service, "build_catalog_sync_service", lambda db: CatalogSyncService(CatalogRepository(db), allegro, erli, store)
    )
    return allegro, erli


def test_a_run_notes_how_it_ended(session, wired):
    result = run_catalog_sync(session)

    note = catalog_service.read_note(session)
    assert result.items == 1
    assert (note.items, note.error, note.erli_error, note.erli_unmatched) == (1, None, None, 0)


def test_a_failed_run_is_noted_and_raised(session, wired):
    allegro, _ = wired
    allegro.list_error = IntegrationUnavailable("Allegro offers: 503")
    allegro.offers = [offer("1"), offer("2")]

    with pytest.raises(IntegrationUnavailable):
        run_catalog_sync(session)

    note = catalog_service.read_note(session)
    assert note.error == "Allegro offers: 503" and note.items is None


def test_a_run_waits_for_no_one(session, wired):
    assert import_lock.acquire(blocking=False)
    try:
        with pytest.raises(ImportAlreadyRunning):
            run_catalog_sync(session)
    finally:
        import_lock.release()
    # and the lock is free again afterwards
    assert import_lock.acquire(blocking=False)
    import_lock.release()


def test_the_lock_is_released_after_a_failed_run(session, wired):
    allegro, _ = wired
    allegro.offers = [offer("1"), offer("2")]
    allegro.list_error = IntegrationUnavailable("down")

    with pytest.raises(IntegrationUnavailable):
        run_catalog_sync(session)

    assert import_lock.acquire(blocking=False)
    import_lock.release()


def test_the_schedule_reads_when_never_read_and_then_every_so_many_hours(session, wired):
    assert sync_is_due(session)

    run_catalog_sync(session)
    now = datetime.now(UTC)

    assert not sync_is_due(session, now + timedelta(hours=settings.catalog_sync_hours - 1))
    assert sync_is_due(session, now + timedelta(hours=settings.catalog_sync_hours, minutes=1))


def test_a_failed_run_also_waits_before_the_next(session, wired):
    allegro, _ = wired
    allegro.offers = [offer("1"), offer("2")]
    allegro.list_error = IntegrationUnavailable("down")
    with pytest.raises(IntegrationUnavailable):
        run_catalog_sync(session)

    assert not sync_is_due(session, datetime.now(UTC) + timedelta(hours=1))
