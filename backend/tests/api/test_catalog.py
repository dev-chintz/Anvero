"""The assortment's API: the list and its filters, the category tree, the summary, the button that
reads the offers, and the stored pictures."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.endpoints.catalog as catalog_endpoint
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.integrations.base import IntegrationNotConfigured
from app.main import app
from app.models.catalog import CatalogImage, CatalogItem, CatalogListing
from app.models.marketplace_write import AppSetting
from app.models.order import BillingEntry, Order, OrderItem, OrderSource, OrderStatus
from app.repositories.user_repository import UserRepository
from app.schemas.user import PermissionGrant, UserCreate
from app.services.allegro_sync import ImportAlreadyRunning
from app.services.catalog import catalog_progress
from app.services.user_service import UserService

client = TestClient(app)
viewer = TestClient(app)
stranger = TestClient(app)
anonymous = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
KITCHEN = [{"id": "1", "name": "Dom i ogród"}, {"id": "20", "name": "Kuchnia"}, {"id": "300", "name": "Kubki"}]
PLATES = [{"id": "1", "name": "Dom i ogród"}, {"id": "20", "name": "Kuchnia"}, {"id": "301", "name": "Talerze"}]
TOYS = [{"id": "2", "name": "Dziecko"}, {"id": "50", "name": "Zabawki"}]
PNG = b"\x89PNG\r\n\x1a\n" + b"a-stored-picture"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_module():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        service = UserService(UserRepository(db))
        admin = service.create_user(UserCreate(email="catalog-admin@example.com", password="operator-password-123"))
        client.headers["Authorization"] = f"Bearer {create_access_token(admin.id)}"
        reader = service.create_user(
            UserCreate(
                email="catalog-viewer@example.com",
                password="operator-password-123",
                role="user",
                permissions=[PermissionGrant(area="orders", level="view")],
            )
        )
        viewer.headers["Authorization"] = f"Bearer {create_access_token(reader.id)}"
        other = service.create_user(
            UserCreate(
                email="catalog-stranger@example.com",
                password="operator-password-123",
                role="user",
                permissions=[PermissionGrant(area="labels", level="view")],
            )
        )
        stranger.headers["Authorization"] = f"Bearer {create_access_token(other.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.pop(get_db, None)


def setup_function():
    db = TestingSessionLocal()
    try:
        for model in (BillingEntry, OrderItem, Order, CatalogListing, CatalogImage, CatalogItem, AppSetting):
            db.query(model).delete()
        db.commit()
    finally:
        db.close()


def add_item(offer_id, name=None, path=KITCHEN, images=(), erli=None, gone=False, **fields):
    db = TestingSessionLocal()
    try:
        values = {
            "source": OrderSource.ALLEGRO,
            "offer_id": offer_id,
            "name": name or f"Oferta {offer_id}",
            "sku": f"SKU-{offer_id}",
            "price": Decimal("10.00"),
            "currency": "PLN",
            "stock": 3,
            "status": "ACTIVE",
            "category_id": path[-1]["id"] if path else None,
            "category_path": path,
            "category_ids": "|" + "|".join(s["id"] for s in path) + "|" if path else "",
            "last_seen_at": NOW,
            "gone_at": NOW if gone else None,
        }
        values.update(fields)
        item = CatalogItem(**values)
        for position, (url, file_name) in enumerate(images):
            item.images.append(CatalogImage(position=position, url=url, file_name=file_name))
        if erli is not None:
            item.listings.append(
                CatalogListing(
                    source=OrderSource.ERLI,
                    external_id=erli.get("external_id", offer_id),
                    matched_by="EXTERNAL_ID",
                    price=Decimal("11.00"),
                    currency="PLN",
                    stock=2,
                    status="ACTIVE",
                    category_path=erli.get("path", [{"id": "9", "name": "Kubki"}]),
                    category_match=erli.get("match", "SAME"),
                    seen_at=NOW,
                )
            )
        db.add(item)
        db.commit()
    finally:
        db.close()


def names(response):
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


# --- who may ---------------------------------------------------------------------------


def test_the_assortment_needs_a_login():
    for path in ("/items", "/categories", "/summary"):
        assert anonymous.get(f"/api/v1/catalog{path}").status_code == 401
    assert anonymous.post("/api/v1/catalog/sync").status_code == 401


def test_it_needs_the_orders_area():
    assert stranger.get("/api/v1/catalog/items").status_code == 403
    assert stranger.get("/api/v1/catalog/summary").status_code == 403


def test_viewing_is_not_reading_from_allegro():
    add_item("1")

    assert viewer.get("/api/v1/catalog/items").status_code == 200
    assert viewer.post("/api/v1/catalog/sync").status_code == 403


# --- the list --------------------------------------------------------------------------


def test_the_list_has_each_offer_with_its_pictures_and_where_it_is_on_allegro():
    add_item("7001", name="Kubek", images=[("https://a.allegroimg.com/1", "f" * 64 + ".png"), ("https://a.allegroimg.com/2", None)])

    (item,) = client.get("/api/v1/catalog/items").json()["items"]

    assert (item["offer_id"], item["name"], item["sku"], item["price"], item["currency"], item["stock"]) == (
        "7001",
        "Kubek",
        "SKU-7001",
        "10.00",
        "PLN",
        3,
    )
    assert item["status"] == "ACTIVE" and item["gone"] is False
    assert item["allegro_url"] == "https://allegro.pl/oferta/7001"
    assert [step["name"] for step in item["category_path"]] == ["Dom i ogród", "Kuchnia", "Kubki"]
    # the copy on this server where there is one, Allegro's address where there is not
    assert item["images"] == [
        {"position": 0, "url": "https://a.allegroimg.com/1", "local_url": f"/api/v1/catalog/images/{'f' * 64}.png"},
        {"position": 1, "url": "https://a.allegroimg.com/2", "local_url": None},
    ]
    assert item["thumbnail_url"] == f"/api/v1/catalog/images/{'f' * 64}.png"
    assert item["erli"] is None


def test_the_thumbnail_is_allegros_address_until_a_copy_exists_and_none_without_pictures():
    add_item("1", name="A", images=[("https://a.allegroimg.com/1", None)])
    add_item("2", name="B")

    first, second = client.get("/api/v1/catalog/items").json()["items"]

    assert first["thumbnail_url"] == "https://a.allegroimg.com/1"
    assert second["thumbnail_url"] is None and second["images"] == []


def test_the_erli_listing_is_shown_beside_the_offer():
    add_item("1", erli={"external_id": "erli-1", "match": "DIFFERENT", "path": [{"id": "5", "name": "Talerze"}]})

    (item,) = client.get("/api/v1/catalog/items").json()["items"]

    assert item["erli"]["external_id"] == "erli-1"
    assert (item["erli"]["price"], item["erli"]["stock"], item["erli"]["status"]) == ("11.00", 2, "ACTIVE")
    assert item["erli"]["category_match"] == "DIFFERENT"
    assert [step["name"] for step in item["erli"]["category_path"]] == ["Talerze"]
    assert item["erli"]["matched_by"] == "EXTERNAL_ID"


def test_the_list_is_by_name_and_does_not_mind_the_case():
    for offer_id, name in (("1", "banan"), ("2", "Cytryna"), ("3", "Ananas")):
        add_item(offer_id, name=name)

    assert names(client.get("/api/v1/catalog/items")) == ["Ananas", "banan", "Cytryna"]


def test_the_list_can_be_sorted_by_price_or_stock_either_way():
    add_item("1", name="A", price=Decimal("30.00"), stock=1)
    add_item("2", name="B", price=Decimal("10.00"), stock=9)
    add_item("3", name="C", price=Decimal("20.00"), stock=5)

    assert names(client.get("/api/v1/catalog/items?sort=price")) == ["B", "C", "A"]
    assert names(client.get("/api/v1/catalog/items?sort=price&descending=true")) == ["A", "C", "B"]
    assert names(client.get("/api/v1/catalog/items?sort=stock&descending=true")) == ["B", "C", "A"]


def test_the_list_is_paged_and_says_how_many_there_are():
    for index in range(5):
        add_item(str(index), name=f"Oferta {index}")

    page = client.get("/api/v1/catalog/items?limit=2&offset=2").json()

    assert page["total"] == 5
    assert [item["name"] for item in page["items"]] == ["Oferta 2", "Oferta 3"]
    assert client.get("/api/v1/catalog/items?limit=201").status_code == 422


def test_search_finds_a_name_a_sku_or_an_offer_id():
    add_item("111", name="Kubek niebieski", sku="NIEB-1")
    add_item("222", name="Talerz", sku="TAL-2")

    assert names(client.get("/api/v1/catalog/items?q=KUBEK")) == ["Kubek niebieski"]
    assert names(client.get("/api/v1/catalog/items?q=tal-2")) == ["Talerz"]
    assert names(client.get("/api/v1/catalog/items?q=222")) == ["Talerz"]
    assert names(client.get("/api/v1/catalog/items?q=nothing")) == []


def test_search_takes_percent_and_underscore_literally():
    add_item("1", name="Rabat 50% taniej")
    add_item("2", name="Rabat 500 zł")

    assert names(client.get("/api/v1/catalog/items", params={"q": "50%"})) == ["Rabat 50% taniej"]
    assert names(client.get("/api/v1/catalog/items", params={"q": "_"})) == []


def test_a_category_holds_everything_below_it():
    add_item("1", name="Kubek", path=KITCHEN)
    add_item("2", name="Talerz", path=PLATES)
    add_item("3", name="Piłka", path=TOYS)

    assert names(client.get("/api/v1/catalog/items?category=20")) == ["Kubek", "Talerz"]
    assert names(client.get("/api/v1/catalog/items?category=300")) == ["Kubek"]
    assert names(client.get("/api/v1/catalog/items?category=2")) == ["Piłka"]
    # `20` is not part of `200` or `1`: ids are matched whole
    add_item("4", name="Inny", path=[{"id": "1", "name": "Dom"}, {"id": "200", "name": "X"}])
    assert "Inny" not in names(client.get("/api/v1/catalog/items?category=20"))


def test_gone_offers_are_out_of_the_assortment_unless_asked_for():
    add_item("1", name="Jest")
    add_item("2", name="Nie ma", gone=True)

    assert names(client.get("/api/v1/catalog/items")) == ["Jest"]
    assert names(client.get("/api/v1/catalog/items?status=gone")) == ["Nie ma"]
    assert client.get("/api/v1/catalog/items?status=gone").json()["items"][0]["gone"] is True


def test_active_and_inactive_offers_can_be_told_apart():
    add_item("1", name="Aktywna")
    add_item("2", name="Wyłączona", status="INACTIVE")
    add_item("3", name="Włączana", status="ACTIVATING")
    add_item("4", name="Dawna", status="ACTIVE", gone=True)

    assert names(client.get("/api/v1/catalog/items?status=active")) == ["Aktywna"]
    # what sorts first depends on the database's collation, so the set is compared
    assert set(names(client.get("/api/v1/catalog/items?status=inactive"))) == {"Wyłączona", "Włączana"}
    assert len(names(client.get("/api/v1/catalog/items"))) == 3


def test_the_quick_filters_find_what_is_missing():
    add_item("1", name="Kompletna", images=[("https://a.allegroimg.com/1", None)], erli={"match": "SAME"})
    add_item("2", name="Bez zdjęcia", sku=None, erli={"match": "DIFFERENT"})
    add_item("3", name="Bez Erli", images=[("https://a.allegroimg.com/3", None)])

    assert names(client.get("/api/v1/catalog/items?flag=no_image")) == ["Bez zdjęcia"]
    assert names(client.get("/api/v1/catalog/items?flag=no_sku")) == ["Bez zdjęcia"]
    assert names(client.get("/api/v1/catalog/items?flag=not_on_erli")) == ["Bez Erli"]
    assert names(client.get("/api/v1/catalog/items?flag=category_differs")) == ["Bez zdjęcia"]
    assert client.get("/api/v1/catalog/items?flag=bogus").status_code == 422


def test_filters_combine():
    add_item("1", name="Kubek A", path=KITCHEN)
    add_item("2", name="Kubek B", path=KITCHEN, sku=None)
    add_item("3", name="Talerz", path=PLATES, sku=None)

    assert names(client.get("/api/v1/catalog/items?category=300&flag=no_sku&q=kubek")) == ["Kubek B"]


# --- categories and summary ------------------------------------------------------------


def test_the_category_tree_counts_each_node_with_what_is_below_it():
    add_item("1", path=KITCHEN)
    add_item("2", path=KITCHEN)
    add_item("3", path=PLATES)
    add_item("4", path=TOYS)
    add_item("5", path=[])
    add_item("6", path=KITCHEN, gone=True)

    tree = client.get("/api/v1/catalog/categories").json()

    assert tree["uncategorized"] == 1
    top = {node["name"]: node for node in tree["tree"]}
    assert set(top) == {"Dom i ogród", "Dziecko"}
    home = top["Dom i ogród"]
    assert home["count"] == 3
    (kitchen,) = home["children"]
    assert (kitchen["name"], kitchen["count"]) == ("Kuchnia", 3)
    assert [(c["name"], c["count"]) for c in kitchen["children"]] == [("Kubki", 2), ("Talerze", 1)]
    assert [(c["name"], c["count"], c["children"]) for c in top["Dziecko"]["children"]] == [("Zabawki", 1, [])]


def test_the_summary_counts_what_the_page_offers_to_filter_by():
    add_item("1", images=[("https://a.allegroimg.com/1", "a" * 64 + ".png"), ("https://a.allegroimg.com/2", None)], erli={"match": "SAME"})
    add_item("2", status="INACTIVE", sku=None, erli={"match": "DIFFERENT"})
    add_item("3")
    add_item("4", gone=True, images=[("https://a.allegroimg.com/4", None)])

    summary = client.get("/api/v1/catalog/summary").json()

    assert summary["total"] == 3
    assert (summary["active"], summary["inactive"], summary["gone"]) == (2, 1, 1)
    assert (summary["no_image"], summary["no_sku"], summary["not_on_erli"], summary["category_differs"]) == (2, 1, 1, 1)
    # only the pictures of current offers
    assert (summary["images_total"], summary["images_local"]) == (2, 1)
    assert summary["erli_connected"] is False
    assert summary["last_sync"] is None and summary["erli_unmatched"] is None


def test_the_summary_carries_the_note_of_the_last_sync():
    note = '{"at": "2026-10-01T12:00:00Z", "error": null, "items": 3, "erli_error": "Erli product search: 503", "erli_unmatched": 4}'
    db = TestingSessionLocal()
    db.add(AppSetting(key="catalog_sync", value=note))
    db.commit()
    db.close()

    summary = client.get("/api/v1/catalog/summary").json()

    assert summary["last_sync"]["items"] == 3 and summary["last_sync"]["at"].startswith("2026-10-01T12:00:00")
    assert summary["last_sync"]["erli_error"] == "Erli product search: 503"
    assert summary["erli_unmatched"] == 4


# --- the button ------------------------------------------------------------------------


def test_the_button_starts_the_read_and_answers_at_once(monkeypatch):
    started = []
    monkeypatch.setattr(catalog_endpoint, "start_catalog_sync", lambda db: started.append(True))

    response = client.post("/api/v1/catalog/sync")

    # accepted, not done: a first read takes minutes, longer than a request may wait
    assert response.status_code == 202
    assert response.json() == {"started": True}
    assert started == [True]


@pytest.mark.parametrize(
    "error, status",
    [
        (ImportAlreadyRunning(), 409),
        (IntegrationNotConfigured("none"), 409),
    ],
)
def test_the_button_says_why_it_could_not(monkeypatch, error, status):
    def refuse(db):
        raise error

    monkeypatch.setattr(catalog_endpoint, "start_catalog_sync", refuse)

    assert client.post("/api/v1/catalog/sync").status_code == status


def test_the_buttons_refusal_says_what_is_in_the_way(monkeypatch):
    def refuse(db):
        raise ImportAlreadyRunning

    monkeypatch.setattr(catalog_endpoint, "start_catalog_sync", refuse)

    assert "already running" in client.post("/api/v1/catalog/sync").json()["detail"]


# --- the progress -----------------------------------------------------------------------


@pytest.fixture
def progress():
    catalog_progress.end()
    yield catalog_progress
    catalog_progress.end()


def test_the_progress_says_nothing_is_running_when_nothing_is(progress):
    assert client.get("/api/v1/catalog/progress").json() == {
        "running": False,
        "phase": None,
        "done": 0,
        "total": None,
        "started_at": None,
    }


def test_the_progress_says_where_the_read_has_got_to(progress):
    progress.begin()
    progress.enter("images", total=400)
    progress.tick(120)

    body = viewer.get("/api/v1/catalog/progress").json()

    assert (body["running"], body["phase"], body["done"], body["total"]) == (True, "images", 120, 400)
    assert body["started_at"].endswith("Z") or "+00:00" in body["started_at"]


def test_a_phase_with_no_known_total_says_so(progress):
    progress.begin()
    progress.enter("listing")
    progress.tick(37)

    body = client.get("/api/v1/catalog/progress").json()

    assert (body["phase"], body["done"], body["total"]) == ("listing", 37, None)


def test_the_progress_needs_a_login_and_the_orders_area(progress):
    assert anonymous.get("/api/v1/catalog/progress").status_code == 401
    assert stranger.get("/api/v1/catalog/progress").status_code == 403


# --- the pictures ----------------------------------------------------------------------


@pytest.fixture
def pictures(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "catalog_images_dir", str(tmp_path))
    name = "ab" + "c" * 62 + ".png"
    folder = tmp_path / "ab"
    folder.mkdir()
    (folder / name).write_bytes(PNG)
    return name


def test_a_stored_picture_is_served_without_a_login_and_cached_for_good(pictures):
    response = anonymous.get(f"/api/v1/catalog/images/{pictures}")

    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert "immutable" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_a_picture_that_is_not_stored_is_not_found(pictures):
    assert anonymous.get(f"/api/v1/catalog/images/{'d' * 64}.png").status_code == 404


@pytest.mark.parametrize("name", ["..%2F..%2Fetc%2Fpasswd", "%2e%2e%2f.env", "x.png", "a" * 64 + ".svg", "a" * 64 + ".png.exe", "A" * 64 + ".png"])
def test_only_names_of_our_own_form_are_served(pictures, name):
    assert anonymous.get(f"/api/v1/catalog/images/{name}").status_code in (404, 422)


def test_an_offer_without_a_price_goes_last_whichever_way_the_list_is_sorted():
    add_item("1", name="A", price=None)
    add_item("2", name="B", price=Decimal("5.00"))
    add_item("3", name="C", price=Decimal("9.00"))

    assert names(client.get("/api/v1/catalog/items?sort=price")) == ["B", "C", "A"]
    assert names(client.get("/api/v1/catalog/items?sort=price&descending=true")) == ["C", "B", "A"]


# --- what each offer sold -----------------------------------------------------------------


def days_ago(days):
    return datetime.now(UTC) - timedelta(days=days)


def sold(offer_id, quantity, price, days=2, source=OrderSource.ALLEGRO, fee=None, delivery=None, **fields):
    """An order of one item of the offer, with the commission booked for it (and, when given, a
    delivery fee); returns the order's marketplace id."""
    db = TestingSessionLocal()
    try:
        external_id = f"form-{uuid.uuid4()}"
        order = Order(
            external_id=external_id,
            source=source,
            status=fields.pop("status", OrderStatus.CONFIRMED),
            customer_email="buyer@example.com",
            total_amount=Decimal(price) * quantity,
            currency="PLN",
            ordered_at=days_ago(days),
            **fields,
        )
        order.items.append(
            OrderItem(position=0, name="Item", quantity=quantity, unit_price=Decimal(price), offer_id=offer_id)
        )
        db.add(order)
        for amount, type_id, name in ((fee, "SUC", "Prowizja"), (delivery, "DXP", "Dostawa")):
            if amount is not None:
                db.add(
                    BillingEntry(
                        source=source,
                        external_id=str(uuid.uuid4()),
                        occurred_at=days_ago(days),
                        type_id=type_id,
                        type_name=name,
                        amount=-Decimal(amount),
                        currency="PLN",
                        order_external_id=external_id,
                        offer_id=offer_id if type_id == "SUC" else None,
                    )
                )
        db.commit()
        return external_id
    finally:
        db.close()


def only_item(**params):
    response = client.get("/api/v1/catalog/items", params=params)
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


def test_an_offer_shows_what_it_sold_and_what_is_left_after_the_fees():
    add_item("7001")
    sold("7001", 2, "50.00", fee="23.00")
    sold("7001", 1, "50.00", fee="11.50")

    sales = only_item()["sales_allegro"]

    assert sales == {"quantity": 3, "orders": 2, "sales": "150.00", "fees": "34.50", "net": "115.50"}


def test_allegro_and_erli_are_told_apart_even_under_the_same_number():
    add_item("7001", erli={"external_id": "7001"})
    sold("7001", 2, "50.00", fee="23.00")
    sold("7001", 5, "45.00", source=OrderSource.ERLI, fee="22.50")

    item = only_item()

    assert (item["sales_allegro"]["quantity"], item["sales_allegro"]["net"]) == (2, "77.00")
    assert (item["sales_erli"]["quantity"], item["sales_erli"]["net"]) == (5, "202.50")


def test_erli_sales_are_found_by_the_erli_products_own_id():
    add_item("7001", erli={"external_id": "erli-77"})
    sold("erli-77", 3, "40.00", source=OrderSource.ERLI, fee="12.00")
    # another Erli product is not this offer's
    sold("someone-else", 9, "40.00", source=OrderSource.ERLI, fee="12.00")

    assert only_item()["sales_erli"]["quantity"] == 3


def test_without_an_erli_product_there_are_no_erli_sales_to_show():
    add_item("7001")
    sold("7001", 1, "50.00", source=OrderSource.ERLI)

    assert only_item()["sales_erli"] is None


def test_an_offer_that_sold_nothing_says_zero_not_nothing():
    add_item("7001", erli={})

    item = only_item()

    zero = {"quantity": 0, "orders": 0, "sales": "0.00", "fees": "0.00", "net": "0.00"}
    assert item["sales_allegro"] == zero and item["sales_erli"] == zero


def test_the_subscription_and_the_marketplace_taking_its_fees_are_not_shared_out():
    add_item("7001")
    sold("7001", 1, "100.00", fee="23.00")
    db = TestingSessionLocal()
    for amount, type_id, settlement in (("199.00", "SB2", False), ("500.00", "PAD", True)):
        db.add(
            BillingEntry(
                source=OrderSource.ALLEGRO,
                external_id=str(uuid.uuid4()),
                occurred_at=days_ago(1),
                type_id=type_id,
                type_name="x",
                amount=-Decimal(amount),
                currency="PLN",
                order_external_id=None,
                is_settlement=settlement,
            )
        )
    db.commit()
    db.close()

    sales = only_item()["sales_allegro"]

    assert (sales["fees"], sales["net"]) == ("23.00", "77.00")


def test_the_delivery_the_buyer_paid_for_offsets_the_delivery_fee():
    add_item("7001")
    sold("7001", 1, "100.00", fee="23.00", delivery="12.00", delivery_cost=Decimal("12.00"))

    # the 12 the carrier took was paid by the buyer: only the commission is the offer's
    assert only_item()["sales_allegro"]["fees"] == "23.00"


def test_a_delivery_fee_beyond_what_the_buyer_paid_is_the_offers():
    add_item("7001")
    sold("7001", 1, "100.00", fee="23.00", delivery="12.00", delivery_cost=Decimal("5.00"))

    assert only_item()["sales_allegro"]["fees"] == "30.00"


def test_cancelled_orders_do_not_count():
    add_item("7001")
    sold("7001", 1, "50.00", fee="5.00")
    sold("7001", 4, "50.00", fee="5.00", status=OrderStatus.CANCELLED)
    sold("7001", 4, "50.00", fee="5.00", marketplace_cancelled_at=days_ago(1))

    assert only_item()["sales_allegro"]["quantity"] == 1


def test_the_period_is_the_last_thirty_days_unless_another_is_asked_for():
    add_item("7001")
    sold("7001", 1, "50.00", days=5)
    sold("7001", 10, "50.00", days=40)
    sold("7001", 100, "50.00", days=200)

    assert only_item()["sales_allegro"]["quantity"] == 1
    assert only_item(sales_days=90)["sales_allegro"]["quantity"] == 11
    assert only_item(sales_days=0)["sales_allegro"]["quantity"] == 111


def test_the_list_says_which_day_the_sales_start_from():
    add_item("7001")

    body = client.get("/api/v1/catalog/items", params={"sales_days": 7}).json()
    everything = client.get("/api/v1/catalog/items", params={"sales_days": 0}).json()

    # seven days ending today, in the business timezone: today and the six days before it
    assert body["sales_from"] is not None
    assert (datetime.fromisoformat(body["sales_from"]).date() - (datetime.now(UTC) - timedelta(days=6)).date()).days in (-1, 0, 1)
    assert everything["sales_from"] is None
    assert client.get("/api/v1/catalog/items", params={"sales_days": -1}).status_code == 422
    assert client.get("/api/v1/catalog/items", params={"sales_days": 9999}).status_code == 422


def test_the_list_can_be_ordered_by_pieces_sold_both_marketplaces_together():
    add_item("1", name="A", erli={"external_id": "e1"})
    add_item("2", name="B")
    add_item("3", name="C")
    sold("1", 2, "10.00")
    sold("e1", 5, "10.00", source=OrderSource.ERLI)
    sold("2", 4, "10.00")

    assert names(client.get("/api/v1/catalog/items?sort=sold&descending=true")) == ["A", "B", "C"]
    assert names(client.get("/api/v1/catalog/items?sort=sold")) == ["C", "B", "A"]


def test_the_list_can_be_ordered_by_what_is_left_after_the_fees():
    add_item("1", name="A")
    add_item("2", name="B")
    # B sold fewer pieces but kept more of them
    sold("1", 10, "10.00", fee="60.00")
    sold("2", 2, "100.00", fee="20.00")

    assert names(client.get("/api/v1/catalog/items?sort=net&descending=true")) == ["B", "A"]
    assert names(client.get("/api/v1/catalog/items?sort=sold&descending=true")) == ["A", "B"]


def test_ordering_by_sales_is_still_paged_and_filtered():
    for n in range(5):
        add_item(str(n), name=f"Offer {n}", sku=None if n == 4 else f"S{n}")
        sold(str(n), n + 1, "10.00")

    page = client.get("/api/v1/catalog/items?sort=sold&descending=true&limit=2&offset=1").json()
    assert page["total"] == 5
    assert [item["name"] for item in page["items"]] == ["Offer 3", "Offer 2"]
    assert names(client.get("/api/v1/catalog/items?sort=sold&descending=true&flag=no_sku")) == ["Offer 4"]


def test_the_sales_need_the_same_permission_as_the_list():
    add_item("7001")
    sold("7001", 1, "50.00")

    assert viewer.get("/api/v1/catalog/items").json()["items"][0]["sales_allegro"]["quantity"] == 1
    assert stranger.get("/api/v1/catalog/items").status_code == 403
