"""Fills the guide's scratch database with an invented shop and writes a login token for it.

Everything here is made up: the buyers, their addresses, the products, the messages. No real order or
person is used, so the screenshots can be committed. Run through tools/guide/make.ps1 (docs/GUIDE.md).
"""

import hashlib
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sample_env  # noqa: E402  (sets the environment first)

sys.path.insert(0, str(sample_env.BACKEND))

from PIL import Image, ImageDraw  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.catalog import CatalogImage, CatalogItem, CatalogListing  # noqa: E402
from app.models.integration import IntegrationCredential, IntegrationSettings  # noqa: E402
from app.models.marketplace_write import AppSetting  # noqa: E402
from app.models.message import Message, MessageDirection, MessageThread  # noqa: E402
from app.models.order import (  # noqa: E402
    AddressType,
    PaymentOperation,
    BillingEntry,
    Order,
    OrderAddress,
    OrderItem,
    OrderItemPacking,
    OrderShipment,
    OrderSource,
    OrderStatus,
    OrderStatusHistory,
    PaymentType,
)
from app.models.production_check import ProductionCheck  # noqa: E402
from app.models.shipping_label import LabelStatus, ShippingLabel  # noqa: E402
from app.repositories.after_sales_repository import AfterSalesRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.schemas.after_sales import SyncedCase  # noqa: E402
from app.schemas.gdpr import ControllerWrite  # noqa: E402
from app.schemas.user import PermissionGrant, UserCreate  # noqa: E402
from app.services import gdpr  # noqa: E402
from app.services.after_sales import classify  # noqa: E402
from app.services.user_service import UserService  # noqa: E402
from app.models.after_sales import CaseKind  # noqa: E402

rng = random.Random(20261001)
NOW = datetime.now(UTC)
PICTURES = sample_env.WORK / "pictures"

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

# ---- the products ------------------------------------------------------------------------------

HOME = [("1", "Dom i ogród"), ("20", "Kuchnia")]
CATEGORIES = {
    "cups": HOME + [("300", "Kubki")],
    "plates": HOME + [("301", "Talerze")],
    "bowls": HOME + [("302", "Miski")],
    "jugs": HOME + [("303", "Dzbanki")],
    "pots": [("1", "Dom i ogród"), ("40", "Ogród"), ("400", "Doniczki")],
    "decor": [("1", "Dom i ogród"), ("60", "Dekoracje"), ("600", "Świeczniki")],
}
COLOURS = [(236, 190, 120), (120, 170, 220), (150, 205, 160), (225, 150, 150), (190, 160, 220), (200, 200, 130)]

# sku, name, price, cost, category, stock, active, on Erli
PRODUCTS = [
    ("KUB-350N", "Kubek ceramiczny niebieski 350 ml", "49.00", "14.00", "cups", 12, True, True),
    ("KUB-350Z", "Kubek ceramiczny zielony 350 ml", "49.00", "14.00", "cups", 2, True, True),
    ("TAL-006", "Zestaw 6 talerzy obiadowych", "189.90", "62.00", "plates", 5, True, True),
    ("TAL-022", "Talerz głęboki 22 cm", "24.50", "8.00", "plates", 40, True, False),
    ("DON-018", "Doniczka ceramiczna matowa 18 cm", "39.00", "11.00", "pots", 7, True, True),
    ("DON-024", "Doniczka ceramiczna matowa 24 cm", "59.00", "17.00", "pots", 3, False, True),
    ("MIS-028", "Miska do sałatek 28 cm", "79.00", None, "bowls", 9, True, True),
    ("DZB-120", "Dzbanek ceramiczny 1,2 l", "89.00", "26.00", "jugs", 4, True, True),
    ("POD-004", "Podstawki pod kubek, komplet 4 szt.", "34.00", None, "cups", 25, True, False),
    ("SWI-001", "Świecznik ceramiczny", "44.00", "12.00", "decor", 6, True, False),
]


def picture(seed: int) -> str:
    colour = COLOURS[seed % len(COLOURS)]
    image = Image.new("RGB", (480, 480), (245, 242, 236))
    draw = ImageDraw.Draw(image)
    draw.ellipse((70, 70, 410, 410), fill=colour)
    draw.ellipse((140, 140, 340, 340), fill=tuple(min(255, c + 25) for c in colour))
    draw.rectangle((200, 200, 280, 280), fill=(255, 255, 255))
    out = BytesIO()
    image.save(out, "PNG")
    data = out.getvalue()
    name = f"{hashlib.sha256(data).hexdigest()}.png"
    path = PICTURES / name[:2] / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return name


# ---- the people --------------------------------------------------------------------------------

FIRST = ["Anna", "Jan", "Katarzyna", "Piotr", "Maria", "Tomasz", "Agnieszka", "Michał", "Ewa", "Paweł", "Joanna", "Marcin", "Magdalena", "Krzysztof", "Monika"]
LAST = ["Nowak", "Kowalski", "Wiśniewska", "Wójcik", "Kowalczyk", "Kamiński", "Lewandowska", "Zieliński", "Szymańska", "Woźniak", "Dąbrowska", "Kozłowski", "Jankowska", "Mazur", "Krawczyk"]
CITIES = [("Warszawa", "00-001"), ("Kraków", "30-001"), ("Gdańsk", "80-001"), ("Wrocław", "50-001"), ("Poznań", "60-001"), ("Łódź", "90-001"), ("Lublin", "20-001"), ("Katowice", "40-001"), ("Szczecin", "70-001"), ("Białystok", "15-001")]
STREETS = ["Lipowa", "Polna", "Słoneczna", "Leśna", "Ogrodowa", "Krótka", "Kwiatowa", "Parkowa"]

db = SessionLocal()
try:
    # ---- the team ---------------------------------------------------------------------------
    users = UserService(UserRepository(db))
    admin = users.create_user(UserCreate(email="admin@example.com", password="guide-sample-not-a-real-password-1"))
    users.create_user(
        UserCreate(
            email="anna.magazyn@example.com",
            password="guide-sample-not-a-real-password-2",
            role="user",
            permissions=[PermissionGrant(area="orders", level="manage"), PermissionGrant(area="labels", level="manage")],
        )
    )
    users.create_user(
        UserCreate(
            email="piotr.ksiegowosc@example.com",
            password="guide-sample-not-a-real-password-3",
            role="user",
            permissions=[PermissionGrant(area="finance", level="view")],
        )
    )

    # ---- the catalog --------------------------------------------------------------------------
    items: dict[str, CatalogItem] = {}
    for index, (sku, name, price, cost, category, stock, active, on_erli) in enumerate(PRODUCTS, start=1):
        path = CATEGORIES[category]
        item = CatalogItem(
            source=OrderSource.ALLEGRO,
            offer_id=str(17000000000 + index),
            name=name,
            sku=sku,
            price=Decimal(price),
            currency="PLN",
            stock=stock,
            status="ACTIVE" if active else "INACTIVE",
            category_id=path[-1][0],
            category_path=[{"id": i, "name": n} for i, n in path],
            category_ids="|" + "|".join(i for i, _ in path) + "|",
            unit_cost=Decimal(cost) if cost else None,
            cost_updated_at=NOW if cost else None,
            last_seen_at=NOW,
        )
        for position in range(3 if index % 3 else 2):
            file_name = picture(index + position)
            item.images.append(
                CatalogImage(
                    position=position,
                    url=f"https://a.allegroimg.com/original/{index:02d}{position}",
                    file_name=file_name,
                    content_type="image/png",
                    byte_size=4321,
                    fetched_at=NOW,
                )
            )
        if on_erli:
            item.listings.append(
                CatalogListing(
                    source=OrderSource.ERLI,
                    external_id=f"erli-{index}",
                    matched_by="EXTERNAL_REFERENCE" if index % 2 else "SKU",
                    price=Decimal(price) + Decimal("3.00"),
                    currency="PLN",
                    stock=max(stock - 1, 0),
                    status="ACTIVE",
                    category_path=[{"id": i, "name": n} for i, n in path[:-1]] + [{"id": "9" + path[-1][0], "name": "Dom i kuchnia" if index == 3 else path[-1][1]}],
                    category_match="DIFFERENT" if index == 3 else "SAME",
                    seen_at=NOW,
                )
            )
        db.add(item)
        items[sku] = item
    db.add(
        AppSetting(
            key="catalog_sync",
            value=f'{{"at": "{(NOW - timedelta(hours=2)).isoformat()}", "error": null, "items": {len(PRODUCTS)}, "added": 0, "gone": 0, "images_downloaded": 0, "images_pending": 0, "erli_error": null, "erli_matched": 7, "erli_unmatched": 1}}',
        )
    )
    db.flush()

    # ---- the orders ---------------------------------------------------------------------------
    DELIVERIES = [
        ("Allegro Paczkomaty InPost", "inpost-id", True, "9.99"),
        ("Allegro Kurier DPD", "dpd-id", False, "13.99"),
        ("Allegro Odbiór w punkcie DHL POP", "dhl-id", False, "10.99"),
    ]
    orders: list[Order] = []
    # age in days, status, source; chosen so every queue has something in it
    PLAN = (
        [(0.1, OrderStatus.NEW), (0.3, OrderStatus.NEW), (0.5, OrderStatus.NEW), (0.8, OrderStatus.NEW), (1.0, OrderStatus.CONFIRMED), (1.2, OrderStatus.CONFIRMED)]
        + [(1.6, OrderStatus.CONFIRMED), (2.1, OrderStatus.CONFIRMED), (2.4, OrderStatus.READY_FOR_SHIPMENT), (2.6, OrderStatus.READY_FOR_SHIPMENT), (3.2, OrderStatus.CONFIRMED)]
        + [(3.5, OrderStatus.SHIPPED), (4.0, OrderStatus.SHIPPED), (5.0, OrderStatus.SHIPPED), (6.0, OrderStatus.DELIVERED), (7.0, OrderStatus.DELIVERED)]
        + [(9.0, OrderStatus.DELIVERED), (11.0, OrderStatus.DELIVERED), (13.0, OrderStatus.SHIPPED), (15.0, OrderStatus.DELIVERED), (18.0, OrderStatus.DELIVERED)]
        + [(21.0, OrderStatus.DELIVERED), (24.0, OrderStatus.DELIVERED), (27.0, OrderStatus.CANCELLED), (30.0, OrderStatus.DELIVERED), (33.0, OrderStatus.DELIVERED)]
        + [(38.0, OrderStatus.DELIVERED), (42.0, OrderStatus.DELIVERED), (47.0, OrderStatus.DELIVERED), (52.0, OrderStatus.DELIVERED)]
    )
    skus = list(items)
    for number, (age, status) in enumerate(PLAN):
        erli = number % 4 == 3
        source = OrderSource.ERLI if erli else OrderSource.ALLEGRO
        first, last = rng.choice(FIRST), rng.choice(LAST)
        login = f"{first.lower()}_{last.lower()}{rng.randint(1, 99)}".replace("ł", "l").replace("ń", "n").replace("ś", "s").replace("ż", "z").replace("ó", "o").replace("ą", "a").replace("ę", "e").replace("ć", "c").replace("ź", "z")
        city, postal = rng.choice(CITIES)
        placed = NOW - timedelta(days=age)
        # two shipped orders get three items, so the order page has something to show
        chosen = rng.sample(skus, k=3 if number in (12, 13) else rng.choice([1, 1, 1, 2, 3]))
        delivery = DELIVERIES[0] if erli else rng.choice(DELIVERIES)
        total_items = Decimal("0")
        order = Order(
            external_id=(f"erli-{3000 + number}" if erli else str(uuid.UUID(int=rng.getrandbits(128)))),
            source=source,
            status=status,
            marketplace_status=status,
            customer_email=f"{login}@example.com",
            customer_login=login,
            customer_first_name=first,
            customer_last_name=last,
            customer_phone=f"+48 500 {rng.randint(100, 999)} {rng.randint(100, 999)}",
            currency="PLN",
            ordered_at=placed,
            status_set_at=placed,
            status_changed_at=placed + timedelta(hours=3),
            delivery_method=("Erli InPost Paczkomaty" if erli else delivery[0]),
            delivery_method_id=delivery[1],
            delivery_cost=Decimal(delivery[3]),
            delivery_smart=delivery[2],
            payment_type=PaymentType.CASH_ON_DELIVERY if number == 20 else PaymentType.ONLINE,
            payment_provider=None if number == 20 else "PAYU",
            invoice_required=number in (14, 15, 16),
            invoice_is_company=number == 17,
            payment_id=str(uuid.UUID(int=rng.getrandbits(128))),
            total_amount=Decimal("0"),
        )
        for position, sku in enumerate(chosen):
            quantity = rng.choice([1, 1, 1, 2, 3])
            price = items[sku].price
            total_items += price * quantity
            order.items.append(
                OrderItem(
                    position=position,
                    name=items[sku].name,
                    sku=sku,
                    offer_id=(f"erli-{skus.index(sku) + 1}" if erli else items[sku].offer_id),
                    quantity=quantity,
                    unit_price=price,
                    image_url=f"/api/v1/catalog/images/{items[sku].images[0].file_name}",
                    tax_rate="23.00",
                )
            )
        order.total_amount = total_items + order.delivery_cost
        # two new orders are not paid for yet
        unpaid = status is OrderStatus.NEW and number in (1, 3)
        if not unpaid:
            order.paid_amount = order.total_amount
            order.paid_at = placed + timedelta(minutes=4)
        if source is OrderSource.ALLEGRO and status in (OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.READY_FOR_SHIPMENT):
            order.dispatch_by = placed + timedelta(days=2)
        order.addresses.append(
            OrderAddress(
                type=AddressType.DELIVERY,
                first_name=first,
                last_name=last,
                street=f"ul. {rng.choice(STREETS)} {rng.randint(1, 80)}/{rng.randint(1, 30)}",
                postal_code=postal,
                city=city,
                country_code="PL",
                phone=order.customer_phone,
            )
        )
        # the buyer's own address, which the non-invoiced record must show
        order.addresses.append(
            OrderAddress(
                type=AddressType.BUYER,
                first_name=first,
                last_name=last,
                street=order.addresses[0].street,
                postal_code=postal,
                city=city,
                country_code="PL",
            )
        )
        if delivery[2]:
            order.pickup_point_id = f"{city[:3].upper()}{rng.randint(10, 99)}M"
            order.pickup_point_name = f"Paczkomat {order.pickup_point_id}"
        if status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            order.shipments.append(
                OrderShipment(
                    position=0,
                    carrier_id="INPOST" if delivery[2] else "DPD",
                    carrier_name="InPost" if delivery[2] else "DPD",
                    waybill=f"6{rng.randint(10**22, 10**23 - 1)}" if delivery[2] else f"1{rng.randint(10**12, 10**13 - 1)}",
                    shipped_at=placed + timedelta(days=1),
                    tracking_status="DELIVERED" if status is OrderStatus.DELIVERED else "IN_TRANSIT",
                    tracking_updated_at=placed + timedelta(days=2),
                )
            )
        order.status_history.append(
            OrderStatusHistory(from_status=OrderStatus.NEW, to_status=status, changed_at=placed + timedelta(hours=3), changed_by_user_id=admin.id)
        ) if status is not OrderStatus.NEW else None
        if number in (4, 9):
            order.starred = True
        if number in (6, 12):
            order.flagged = True
        if number == 5:
            order.internal_note = "Klientka prosiła o dodatkowe zabezpieczenie przy pakowaniu."
            order.buyer_message = "Proszę o staranne zapakowanie, to prezent."
        db.add(order)
        orders.append(order)
    db.flush()

    # ---- the fees the marketplaces charged, and the subscription -----------------------------------
    for order in orders:
        if order.status is OrderStatus.CANCELLED:
            continue
        goods = order.total_amount - order.delivery_cost
        erli = order.source is OrderSource.ERLI
        db.add(
            BillingEntry(
                source=order.source,
                external_id=str(uuid.uuid4()),
                occurred_at=order.ordered_at + timedelta(days=1),
                type_id="COMM" if erli else "SUC",
                type_name="Prowizja od sprzedaży",
                amount=-(goods * Decimal("0.10" if erli else "0.11")).quantize(Decimal("0.01")),
                currency="PLN",
                order_external_id=order.external_id,
                offer_id=order.items[0].offer_id,
            )
        )
        if not erli and order.delivery_cost > Decimal("10"):
            db.add(
                BillingEntry(
                    source=order.source,
                    external_id=str(uuid.uuid4()),
                    occurred_at=order.ordered_at + timedelta(days=1),
                    type_id="DXP",
                    type_name="Opłata za dostawę",
                    amount=-order.delivery_cost,
                    currency="PLN",
                    order_external_id=order.external_id,
                )
            )
    db.add(
        BillingEntry(
            source=OrderSource.ALLEGRO,
            external_id=str(uuid.uuid4()),
            occurred_at=NOW - timedelta(days=12),
            type_id="SB2",
            type_name="Abonament profesjonalny",
            amount=Decimal("-199.00"),
            currency="PLN",
            order_external_id=None,
        )
    )

    # ---- the money that reached the payment operator, which the non-invoiced record traces ----------
    for order in orders:
        if order.paid_at is None or order.status is OrderStatus.CANCELLED or order.payment_type is not PaymentType.ONLINE:
            continue
        db.add(
            PaymentOperation(
                source=order.source,
                fingerprint=hashlib.sha256(order.payment_id.encode()).hexdigest(),
                type="CONTRIBUTION",
                group="INCOME",
                occurred_at=order.paid_at,
                amount=order.paid_amount,
                currency="PLN",
                wallet_operator="PAYU",
                wallet_type="AVAILABLE",
                wallet_balance=order.paid_amount,
                payment_id=order.payment_id,
                marketplace_id="allegro-pl",
            )
        )

    # ---- packing, production, labels ----------------------------------------------------------
    waiting = [o for o in orders if o.status in (OrderStatus.NEW, OrderStatus.CONFIRMED, OrderStatus.READY_FOR_SHIPMENT)]
    if len(waiting) > 6:
        db.add(OrderItemPacking(order_id=waiting[6].id, position=0, packed_quantity=1, updated_by_user_id=admin.id))
    db.add(ProductionCheck(key="sku:KUB-350N", quantity=3, checked_by_user_id=admin.id))
    for label_number, order in enumerate([o for o in orders if o.status in (OrderStatus.CONFIRMED, OrderStatus.READY_FOR_SHIPMENT) and o.source is OrderSource.ALLEGRO][:4]):
        db.add(
            ShippingLabel(
                order_id=order.id,
                created_at=NOW - timedelta(hours=5 + label_number * 3),
                printed_at=NOW - timedelta(hours=1) if label_number == 0 else None,
                created_by_user_id=admin.id,
                command_id=str(uuid.uuid4()),
                shipment_id=str(uuid.uuid4()),
                status=LabelStatus.CREATED,
                delivery_method_id=order.delivery_method_id or "inpost-id",
                carrier_id="INPOST",
                waybill=f"6{rng.randint(10**22, 10**23 - 1)}",
                length_cm=Decimal("20"),
                width_cm=Decimal("15"),
                height_cm=Decimal("10"),
                weight_kg=Decimal("1.2"),
            )
        )

    # ---- messages -----------------------------------------------------------------------------
    TALKS = [
        ("Czy mogę jeszcze zmienić adres dostawy? Wpisałam stary.", "Dzień dobry, oczywiście: proszę podać nowy adres, zmienię go przed wysyłką.", False),
        ("Kiedy mogę się spodziewać paczki?", "Dzień dobry, paczka zostanie nadana jutro, numer przesyłki dostanie Pani w wiadomości od Allegro.", True),
        ("Dzień dobry, czy kubek jest odporny na zmywarkę?", None, False),
        ("Przesyłka dotarła uszkodzona, jak mogę złożyć reklamację?", None, False),
        ("Dziękuję, wszystko w porządku, piękny kubek!", None, True),
        ("Czy da się dokupić jeszcze dwa takie same talerze?", "Tak, mamy je w ofercie: proszę o numer zamówienia, połączę z poprzednim, żeby nie płacić dostawy dwa razy.", False),
    ]
    allegro_orders = [o for o in orders if o.source is OrderSource.ALLEGRO]
    for index, (question, reply, read) in enumerate(TALKS):
        order = allegro_orders[index * 2]
        sent = NOW - timedelta(hours=3 + index * 7)
        thread = MessageThread(
            source=OrderSource.ALLEGRO,
            external_id=str(uuid.uuid4()),
            interlocutor_login=order.customer_login,
            order_external_id=order.external_id,
            last_message_at=sent if reply is None else sent + timedelta(hours=1),
            last_message_text=(question if reply is None else reply)[:200],
            read=read,
            aside=False,
        )
        thread.messages.append(Message(direction=MessageDirection.IN, author_login=order.customer_login, text=question, sent_at=sent, created_in_anvero=False))
        if reply:
            thread.messages.append(Message(direction=MessageDirection.OUT, author_login="sklep", text=reply, sent_at=sent + timedelta(hours=1), created_in_anvero=False))
        db.add(thread)

    # ---- returns, claims, disputes -------------------------------------------------------------
    cases = AfterSalesRepository(db)
    CASES = [
        (CaseKind.RETURN, "DELIVERED", 2, "NOT_AS_DESCRIBED", "Kubek ma inny odcień niż na zdjęciu", None),
        (CaseKind.CLAIM, "CLAIM_SUBMITTED", 4, None, "Talerz pękł po pierwszym użyciu", NOW + timedelta(days=6)),
        (CaseKind.DISPUTE, "DISPUTE_ONGOING", 3, "DAMAGED", "Przesyłka uszkodzona w transporcie", None),
        (CaseKind.RETURN, "FINISHED", 20, "CHANGED_MIND", "Zwrot z powodu zmiany decyzji", None),
    ]
    for number, (kind, status, days, reason, summary, due) in enumerate(CASES):
        order = allegro_orders[number * 3 + 1]
        case = SyncedCase(
            kind=kind,
            external_id=f"case-{number + 1}",
            status=status,
            is_open=status != "FINISHED",
            opened_at=NOW - timedelta(days=days),
            reference_number=f"{number + 1}/2026",
            order_external_id=order.external_id,
            buyer_login=order.customer_login,
            reason=reason,
            summary=summary,
            marketplace_due_at=due,
        )
        action, due_at = classify(case, NOW)
        cases.upsert(OrderSource.ALLEGRO, case, action, due_at)

    # ---- the connections, as they look when everything works ----------------------------------------------------
    db.add(IntegrationSettings(provider="ALLEGRO", client_id="sample-client-id", client_secret="sample-secret", user_agent="Anvero sample", environment="production"))
    db.add(
        IntegrationCredential(
            provider="ALLEGRO",
            refresh_token="sample-refresh-token",
            seed_fingerprint="sample",
            account_login="manufaktura_demo",
            last_import_at=NOW - timedelta(minutes=7),
            last_import_created=0,
            last_import_updated=0,
            last_synced_at=NOW - timedelta(minutes=7),
            last_billing_synced_at=NOW - timedelta(minutes=7),
        )
    )
    db.add(
        IntegrationCredential(
            provider="ERLI", refresh_token="", seed_fingerprint="sample", last_import_at=NOW - timedelta(minutes=7), last_import_created=0, last_import_updated=0
        )
    )
    db.commit()

    # ---- who the data controller is: made up, like the rest ------------------------------------
    gdpr.set_controller(
        db,
        ControllerWrite(
            name="Manufaktura Przykładowa sp. z o.o.",
            tax_id="0000000000",
            address="ul. Przykładowa 1, 00-000 Miasto",
            email="rodo@example.com",
            phone="+48 000 000 000",
        ),
        admin.id,
    )

    # the first import and the ledger, so the sales report has something to show
    try:
        from app.services.non_invoiced.ledger import write_ledger

        for source in (OrderSource.ALLEGRO, OrderSource.ERLI):
            write_ledger(db, source, NOW - timedelta(days=90), NOW)
    except Exception as exc:  # the report is then empty, which is still a screenshot
        print("ledger not written:", type(exc).__name__, exc)

    orders_with_numbers = [(o.order_number, str(o.id)) for o in orders]
    (sample_env.WORK / "orders.txt").write_text("\n".join(f"{n}\t{i}" for n, i in orders_with_numbers), encoding="utf-8")
    (sample_env.WORK / "token.txt").write_text(create_access_token(admin.id), encoding="utf-8")
    print(f"seeded {len(orders)} orders, {len(items)} offers")
finally:
    db.close()
