"""The assortment's readers: Allegro's offers and categories, Erli's products, against fakes shaped
like the marketplaces' published API descriptions.

No real answer of either has been seen yet, so these check that Anvero reads what the descriptions
promise, not that the services send it.
"""

import json
from decimal import Decimal

import httpx2
import pytest

from app.integrations.allegro.catalog import (
    AllegroCatalogAdapter,
    image_urls,
    map_offer,
)
from app.integrations.allegro.client import OFFERS_PAGE_SIZE, AllegroClient
from app.integrations.base import IntegrationAuthError, IntegrationUnavailable
from app.integrations.erli.catalog import (
    ErliCatalogAdapter,
    allegro_offer_ids,
    map_product,
)
from app.integrations.erli.client import PRODUCT_PAGE_SIZE, ErliClient

ALLEGRO_URL = "https://allegro.test"
ERLI_URL = "https://erli.test/svc/shop-api"


def _offer(**overrides):
    offer = {
        "id": "7001",
        "name": "Kubek ceramiczny",
        "category": {"id": "42"},
        "primaryImage": {"url": "https://a.allegroimg.com/original/cover"},
        "sellingMode": {"format": "BUY_NOW", "price": {"amount": "49.00", "currency": "PLN"}},
        "stock": {"available": 12, "unit": "UNIT"},
        "publication": {"status": "ACTIVE"},
        "external": {"id": "KUB-350"},
    }
    offer.update(overrides)
    return offer


def _allegro(handler):
    client = AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url=ALLEGRO_URL,
        auth_url=ALLEGRO_URL + "/auth",
        user_agent="Anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(_with_token(handler))),
    )
    return client


def _with_token(handler):
    def wrapped(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/token"):
            return httpx2.Response(200, json={"access_token": "t", "refresh_token": "refresh", "expires_in": 3600})
        return handler(request)

    return wrapped


# --- Allegro: mapping ------------------------------------------------------------


def test_maps_an_allegro_offer():
    offer = map_offer(_offer())

    assert offer.offer_id == "7001"
    assert offer.name == "Kubek ceramiczny"
    assert offer.status == "ACTIVE"
    assert offer.sku == "KUB-350"
    assert offer.price == Decimal("49.00")
    assert offer.currency == "PLN"
    assert offer.stock == 12
    assert offer.category_id == "42"
    assert offer.image_urls == ("https://a.allegroimg.com/original/cover",)


def test_an_offer_without_an_id_or_a_name_is_skipped():
    assert map_offer(_offer(id=None)) is None
    assert map_offer(_offer(name="  ")) is None


def test_a_sparse_offer_keeps_what_it_has():
    offer = map_offer({"id": 9, "name": "Goły"})

    assert (offer.offer_id, offer.status) == ("9", "UNKNOWN")
    assert offer.sku is None and offer.price is None and offer.stock is None
    assert offer.category_id is None and offer.image_urls == ()


def test_a_price_that_is_not_a_number_is_none():
    offer = map_offer(_offer(sellingMode={"price": {"amount": "n/a", "currency": "PLN"}}))

    assert offer.price is None


def test_pictures_are_read_from_addresses_or_objects_each_once():
    raw = {"images": ["https://a.allegroimg.com/1", {"url": "https://a.allegroimg.com/2"}, "https://a.allegroimg.com/1", 5, None]}

    assert image_urls(raw) == ("https://a.allegroimg.com/1", "https://a.allegroimg.com/2")
    assert image_urls({}) == ()


# --- Allegro: reading -------------------------------------------------------------


def test_the_offers_are_read_page_by_page_until_the_total():
    seen = []

    def handler(request):
        offset = int(request.url.params["offset"])
        seen.append((offset, request.url.params.get_list("publication.status"), request.url.params["limit"]))
        count = OFFERS_PAGE_SIZE if offset == 0 else 30
        return httpx2.Response(
            200,
            json={
                "offers": [_offer(id=str(offset + i)) for i in range(count)],
                "count": count,
                "totalCount": OFFERS_PAGE_SIZE + 30,
            },
        )

    offers = list(AllegroCatalogAdapter(_allegro(handler)).iter_offers())

    assert len(offers) == OFFERS_PAGE_SIZE + 30
    assert [offset for offset, *_ in seen] == [0, OFFERS_PAGE_SIZE]
    # ended offers are not asked for
    assert seen[0][1] == ["ACTIVE", "INACTIVE", "ACTIVATING"]
    assert seen[0][2] == str(OFFERS_PAGE_SIZE)


def test_an_empty_list_is_no_offers():
    adapter = AllegroCatalogAdapter(_allegro(lambda request: httpx2.Response(200, json={"offers": [], "count": 0, "totalCount": 0})))

    assert list(adapter.iter_offers()) == []


def test_a_failing_page_stops_the_whole_read():
    def handler(request):
        if int(request.url.params["offset"]) == 0:
            return httpx2.Response(200, json={"offers": [_offer(id=str(i)) for i in range(OFFERS_PAGE_SIZE)], "totalCount": 250})
        return httpx2.Response(503)

    iterator = AllegroCatalogAdapter(_allegro(handler)).iter_offers()

    with pytest.raises(IntegrationUnavailable):
        list(iterator)


def test_a_refused_read_is_an_auth_error():
    adapter = AllegroCatalogAdapter(_allegro(lambda request: httpx2.Response(403)))

    with pytest.raises(IntegrationAuthError):
        list(adapter.iter_offers())


def test_an_offers_pictures_come_from_its_full_record():
    def handler(request):
        assert request.url.path == "/sale/product-offers/7001"
        return httpx2.Response(200, json={"images": ["https://a.allegroimg.com/1", "https://a.allegroimg.com/2"]})

    assert AllegroCatalogAdapter(_allegro(handler)).fetch_images("7001") == (
        "https://a.allegroimg.com/1",
        "https://a.allegroimg.com/2",
    )


def test_the_way_to_a_category_is_followed_to_the_top_and_remembered():
    asked = []
    tree = {
        "300": {"id": "300", "name": "Kubki", "parent": {"id": "20"}},
        "20": {"id": "20", "name": "Kuchnia", "parent": {"id": "1"}},
        "1": {"id": "1", "name": "Dom i ogród", "parent": None},
    }

    def handler(request):
        category_id = request.url.path.rsplit("/", 1)[1]
        asked.append(category_id)
        return httpx2.Response(200, json=tree[category_id])

    adapter = AllegroCatalogAdapter(_allegro(handler))

    assert adapter.category_path("300") == [
        {"id": "1", "name": "Dom i ogród"},
        {"id": "20", "name": "Kuchnia"},
        {"id": "300", "name": "Kubki"},
    ]
    # a sibling shares the parents already read
    tree["301"] = {"id": "301", "name": "Szklanki", "parent": {"id": "20"}}
    assert adapter.category_path("301")[-1] == {"id": "301", "name": "Szklanki"}
    assert asked == ["300", "20", "1", "301"]


# --- Erli: mapping ----------------------------------------------------------------


def _product(**overrides):
    product = {
        "externalId": "7001",
        "sku": "KUB-350",
        "name": "Kubek ceramiczny",
        "price": 4900,
        "stock": 12,
        "status": "active",
        "archived": False,
        "currency": "PLN",
        "externalReferences": [{"id": "7001", "kind": "allegro"}],
        "externalCategories": [{"source": "allegro", "breadcrumb": [{"id": 1, "name": "Dom i ogród"}, {"id": 300, "name": "Kubki"}]}],
        "categories": [[{"id": 11, "name": "Dom"}, {"id": 111, "name": "Kubki i szklanki"}]],
    }
    product.update(overrides)
    return product


def test_maps_an_erli_product():
    product = map_product(_product())

    assert product.external_id == "7001"
    assert product.sku == "KUB-350"
    # Erli's prices are in grosze
    assert product.price == Decimal(49)
    assert product.stock == 12
    assert product.status == "ACTIVE"
    assert product.allegro_offer_ids == ("7001",)
    assert [step["name"] for step in product.category_path] == ["Dom", "Kubki i szklanki"]
    assert [step["name"] for step in product.source_category_path] == ["Dom i ogród", "Kubki"]


def test_an_archived_product_is_archived_whatever_its_status():
    assert map_product(_product(archived=True)).status == "ARCHIVED"


def test_a_product_without_an_external_id_is_skipped():
    assert map_product(_product(externalId=None)) is None


def test_references_are_read_in_both_notations():
    raw = {"externalReferences": [{"id": "111111", "kind": "allegro"}, "allegro:222222", {"id": "x", "kind": "ceneo"}, "other:1", "allegro:222222"]}

    assert allegro_offer_ids(raw) == ("111111", "222222")
    assert allegro_offer_ids({}) == ()


def test_the_given_category_prefers_allegros():
    product = map_product(
        _product(
            categories=[],
            externalCategories=[
                {"source": "ceneo", "breadcrumb": [{"id": 5, "name": "Inne"}]},
                {"source": "allegro", "breadcrumb": [{"id": 300, "name": "Kubki"}]},
            ],
        )
    )

    assert product.category_path == ()
    assert [step["name"] for step in product.source_category_path] == ["Kubki"]


# --- Erli: reading ----------------------------------------------------------------


def _erli(handler):
    return ErliClient(
        api_key="key", api_url=ERLI_URL, http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )


def test_the_products_are_read_after_the_last_external_id():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        after = body["pagination"].get("after")
        if after is None:
            return httpx2.Response(200, json=[_product(externalId=f"p{i:04d}") for i in range(PRODUCT_PAGE_SIZE)])
        return httpx2.Response(200, json=[_product(externalId="z-last")])

    products = list(ErliCatalogAdapter(_erli(handler)).iter_products())

    assert len(products) == PRODUCT_PAGE_SIZE + 1
    assert bodies[0]["pagination"] == {"sortField": "externalId", "order": "ASC", "limit": PRODUCT_PAGE_SIZE}
    assert bodies[1]["pagination"]["after"] == f"p{PRODUCT_PAGE_SIZE - 1:04d}"
    # only what the page shows is asked for, not the whole description
    assert "description" not in bodies[0]["fields"] and "externalCategories" in bodies[0]["fields"]


def test_a_refused_key_is_an_auth_error():
    with pytest.raises(IntegrationAuthError):
        list(ErliCatalogAdapter(_erli(lambda request: httpx2.Response(401))).iter_products())
