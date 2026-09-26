"""The Finance page's figures: a period's sales and fees, per order and per product."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.integration import IntegrationCredential
from app.models.order import BillingEntry, Order, OrderItem, OrderSource, OrderStatus, Payout
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.finance import fee_kind, previous_period
from app.services.user_service import UserService

client = TestClient(app)
anonymous = TestClient(app)

engine = create_engine(
    settings.database_url,
    connect_args=({"check_same_thread": False} if "sqlite" in settings.database_url else {}),
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SEPTEMBER = {"date_from": "2026-09-01", "date_to": "2026-09-30"}


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
        operator = UserService(UserRepository(db)).create_user(
            UserCreate(email="finance-operator@example.com", password="operator-password-123")
        )
        client.headers["Authorization"] = f"Bearer {create_access_token(operator.id)}"
    finally:
        db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)


def setup_function():
    db = TestingSessionLocal()
    try:
        db.query(BillingEntry).delete()
        db.query(Payout).delete()
        db.query(OrderItem).delete()
        db.query(Order).delete()
        db.query(IntegrationCredential).delete()
        db.commit()
    finally:
        db.close()


def _order(
    total: str,
    ordered_at: datetime,
    source: OrderSource = OrderSource.ALLEGRO,
    items: list[tuple[str, int, str, str | None]] = (),
    item_ids: list[str] | None = None,
    **fields,
) -> str:
    """An order and its items (name, quantity, unit price, offer id); returns its marketplace id."""
    db = TestingSessionLocal()
    try:
        external_id = f"form-{uuid.uuid4()}"
        order = Order(
            external_id=external_id,
            source=source,
            status=fields.pop("status", OrderStatus.CONFIRMED),
            customer_email="buyer@example.com",
            total_amount=Decimal(total),
            currency="PLN",
            ordered_at=ordered_at,
            **fields,
        )
        for position, (name, quantity, price, offer_id) in enumerate(items):
            order.items.append(
                OrderItem(
                    position=position,
                    name=name,
                    quantity=quantity,
                    unit_price=Decimal(price),
                    offer_id=offer_id,
                    external_id=item_ids[position] if item_ids else None,
                )
            )
        db.add(order)
        db.commit()
        return external_id
    finally:
        db.close()


def _fee(
    amount: str,
    occurred_at: datetime,
    type_id: str = "SUC",
    type_name: str | None = "Prowizja od sprzedaży",
    order: str | None = None,
    offer: str | None = None,
    source: OrderSource = OrderSource.ALLEGRO,
    settlement: bool = False,
) -> None:
    db = TestingSessionLocal()
    try:
        db.add(
            BillingEntry(
                source=source,
                external_id=str(uuid.uuid4()),
                occurred_at=occurred_at,
                type_id=type_id,
                type_name=type_name,
                amount=Decimal(amount),
                currency="PLN",
                order_external_id=order,
                offer_id=offer,
                is_settlement=settlement,
            )
        )
        db.commit()
    finally:
        db.close()


def _day(month: int, day: int, hour: int = 12) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def test_finance_needs_a_login():
    assert anonymous.get("/api/v1/finance/summary", params=SEPTEMBER).status_code == 401


def test_the_previous_period_is_as_long_and_ends_the_day_before():
    from datetime import date

    assert previous_period(date(2026, 9, 1), date(2026, 9, 30)) == (date(2026, 8, 2), date(2026, 8, 31))


def test_fee_kinds():
    assert fee_kind("SUC", "Prowizja od sprzedaży") == "commission"
    assert fee_kind("HB4", "Opłata za dostawę InPost") == "delivery"
    assert fee_kind("NSP", "Opłata za wyróżnienie") == "other"
    # Erli's
    assert fee_kind("COMM", "naliczenie prowizji") == "commission"
    assert fee_kind("CRUC", "wykorzystanie rabatu transakcyjnego") == "commission"
    assert fee_kind("SHIP", "metoda dostawy ERLI.pl") == "delivery"
    assert fee_kind("SHAO", "dodatkowe koszty obsługi przesyłek wg taryfy Operatora") == "delivery"
    assert fee_kind("COKS", "naliczenie dodatkowej opłaty za obsługę płatności") == "other"


def test_summary_counts_sales_by_order_date_and_fees_by_booking_date():
    placed = _order("100.00", _day(9, 10))
    _order("50.00", _day(9, 12), source=OrderSource.ERLI)
    _fee("-12.00", _day(9, 10), order=placed)
    _fee("-8.99", _day(9, 11), type_id="HB4", type_name="Opłata za dostawę InPost", order=placed)
    # booked in September for an order placed in August: in September's fees, not its sales
    older = _order("40.00", _day(8, 30))
    _fee("-4.00", _day(9, 2), order=older)
    # a refund of a fee lowers the total
    _fee("2.00", _day(9, 15), order=placed)

    body = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()

    assert Decimal(body["sales"]) == Decimal("150.00")
    assert body["orders"] == 2
    assert Decimal(body["fees"]) == Decimal("22.99")
    allegro = next(row for row in body["by_source"] if row["source"] == "ALLEGRO")
    assert (Decimal(allegro["sales"]), allegro["orders"], Decimal(allegro["fees"])) == (
        Decimal("100.00"), 1, Decimal("22.99")
    )
    kinds = {row["type_id"]: Decimal(row["fees"]) for row in body["by_type"]}
    assert kinds == {"SUC": Decimal("14.00"), "HB4": Decimal("8.99")}
    # the largest first
    assert body["by_type"][0]["type_id"] == "SUC"
    assert Decimal(body["previous_sales"]) == Decimal("40.00")


def test_the_delivery_the_buyers_paid_is_set_beside_the_delivery_fees():
    erli = _order("21.86", _day(9, 10), source=OrderSource.ERLI, delivery_cost=Decimal("10.49"))
    _fee("-10.49", _day(9, 11), type_id="SHIP", type_name="metoda dostawy ERLI.pl", order=erli, source=OrderSource.ERLI)
    _fee("-2.20", _day(9, 10), type_id="COMM", type_name="naliczenie prowizji", order=erli, source=OrderSource.ERLI)
    smart = _order("40.00", _day(9, 12), delivery_cost=Decimal("0.00"))
    _fee("-8.99", _day(9, 12), type_id="HB4", type_name="Opłata za dostawę InPost", order=smart)

    body = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()

    by_source = {row["source"]: row for row in body["by_source"]}
    assert (Decimal(by_source["ERLI"]["delivery_paid"]), Decimal(by_source["ERLI"]["delivery_fees"])) == (
        Decimal("10.49"), Decimal("10.49")
    )
    assert (Decimal(by_source["ALLEGRO"]["delivery_paid"]), Decimal(by_source["ALLEGRO"]["delivery_fees"])) == (
        Decimal("0.00"), Decimal("8.99")
    )
    assert (Decimal(body["delivery_paid"]), Decimal(body["delivery_fees"])) == (Decimal("10.49"), Decimal("19.48"))


def test_summary_leaves_out_the_fees_settled_from_proceeds_but_reports_them():
    placed = _order("100.00", _day(9, 10))
    _fee("-12.00", _day(9, 10), order=placed)
    _fee("12.00", _day(9, 10, 13), type_id="PAD", type_name="Pobranie opłat z wpływów", settlement=True)

    body = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()

    assert Decimal(body["fees"]) == Decimal("12.00")
    (allegro,) = body["settlements"]
    assert (Decimal(allegro["fees"]), Decimal(allegro["settled"])) == (Decimal("12.00"), Decimal("12.00"))
    assert Decimal(allegro["unsettled"]) == Decimal("0.00")
    assert "PAD" not in {row["type_id"] for row in body["by_type"]}


def test_the_check_is_made_over_everything_read_as_a_month_can_split_a_fee_from_its_settlement():
    placed = _order("50.00", _day(8, 31))
    # the fee on the last day of August, taken from the proceeds on 1 September
    _fee("-10.00", _day(8, 31, 20), order=placed)
    _fee("10.00", _day(9, 1, 6), type_id="PAD", type_name="Pobranie opłat z wpływów", settlement=True)
    _fee("-3.00", _day(9, 2), order=placed)

    (allegro,) = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()["settlements"]

    assert (Decimal(allegro["fees"]), Decimal(allegro["settled"])) == (Decimal("3.00"), Decimal("10.00"))
    # over everything read, only the 3.00 of 2 September is still to be taken
    assert Decimal(allegro["unsettled"]) == Decimal("3.00")
    assert allegro["held_since"].startswith("2026-08-31")


def test_summary_leaves_out_cancelled_and_deleted_orders():
    _order("100.00", _day(9, 10))
    _order("70.00", _day(9, 10), status=OrderStatus.CANCELLED)
    _order("60.00", _day(9, 10), marketplace_cancelled_at=_day(9, 11))
    _order("50.00", _day(9, 10), deleted_at=_day(9, 11))

    body = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()

    assert (Decimal(body["sales"]), body["orders"]) == (Decimal("100.00"), 1)


def test_a_day_is_the_business_timezone_day():
    # 30 September, 23:30 in Warsaw is still September; 00:30 on 1 October is not
    _order("10.00", datetime(2026, 9, 30, 21, 30, tzinfo=UTC))
    _order("20.00", datetime(2026, 9, 30, 22, 30, tzinfo=UTC))

    body = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()

    assert Decimal(body["sales"]) == Decimal("10.00")


def test_a_period_ending_before_it_starts_is_refused():
    response = client.get("/api/v1/finance/summary", params={"date_from": "2026-09-30", "date_to": "2026-09-01"})
    assert response.status_code == 422


def test_orders_carry_every_fee_booked_for_them_by_kind():
    placed = _order("82.11", _day(9, 26))
    _fee("-9.85", _day(9, 26), order=placed)
    _fee("-8.99", _day(10, 2), type_id="HB4", type_name="Opłata za dostawę InPost", order=placed)
    _fee("-1.00", _day(9, 27), type_id="XYZ", type_name="Inna opłata", order=placed)

    body = client.get("/api/v1/finance/orders", params=SEPTEMBER).json()

    assert body["total"] == 1
    (row,) = body["items"]
    assert row["order_label"].startswith("AN-")
    assert [Decimal(row[k]) for k in ("sales", "commission", "delivery", "other", "fees")] == [
        Decimal("82.11"), Decimal("9.85"), Decimal("8.99"), Decimal("1.00"), Decimal("19.84")
    ]


def test_orders_sort_by_the_share_the_fees_took():
    cheap = _order("20.00", _day(9, 10))
    dear = _order("100.00", _day(9, 11))
    _fee("-10.00", _day(9, 10), order=cheap)
    _fee("-12.00", _day(9, 11), order=dear)

    newest = client.get("/api/v1/finance/orders", params=SEPTEMBER).json()["items"]
    by_share = client.get("/api/v1/finance/orders", params={**SEPTEMBER, "sort": "share"}).json()["items"]

    assert [Decimal(r["sales"]) for r in newest] == [Decimal("100.00"), Decimal("20.00")]
    assert [Decimal(r["sales"]) for r in by_share] == [Decimal("20.00"), Decimal("100.00")]


def test_products_get_their_offers_fees_and_a_share_of_the_rest():
    placed = _order(
        "68.85",
        _day(9, 26),
        items=[("Serduszko", 45, "1.30", "offer-1"), ("Tabliczka", 1, "10.35", "offer-2")],
    )
    _fee("-22.05", _day(9, 26), order=placed, offer="offer-1")
    _fee("-1.27", _day(9, 26), order=placed, offer="offer-2")
    # a delivery fee names no offer: shared by value, 58.50 to 10.35
    _fee("-6.89", _day(9, 26), type_id="HB4", type_name="Opłata za dostawę InPost", order=placed)

    items = client.get("/api/v1/finance/products", params=SEPTEMBER).json()["items"]

    by_name = {row["name"]: row for row in items}
    heart, plate = by_name["Serduszko"], by_name["Tabliczka"]
    assert (heart["quantity"], Decimal(heart["sales"])) == (45, Decimal("58.50"))
    assert Decimal(heart["fees"]) == Decimal("27.90")
    assert Decimal(plate["fees"]) == Decimal("2.31")
    assert Decimal(heart["fees"]) + Decimal(plate["fees"]) == Decimal("30.21")


def _payout(amount: str, paid_at: datetime, source: OrderSource = OrderSource.ERLI) -> None:
    db = TestingSessionLocal()
    try:
        db.add(
            Payout(
                source=source,
                external_id=str(uuid.uuid4()),
                paid_at=paid_at,
                amount=Decimal(amount),
                currency="PLN",
                operator="PAYU",
            )
        )
        db.commit()
    finally:
        db.close()


def test_payouts_count_by_the_day_paid_for_the_marketplaces_that_give_them():
    _order("100.00", _day(9, 10))
    _payout("43.59", _day(9, 1))
    _payout("22.37", _day(9, 26))
    _payout("10.00", _day(8, 20))

    body = client.get("/api/v1/finance/summary", params=SEPTEMBER).json()

    assert Decimal(body["paid_out"]) == Decimal("65.96")
    by_source = {row["source"]: row for row in body["by_source"]}
    assert Decimal(by_source["ERLI"]["paid_out"]) == Decimal("65.96")
    # Allegro's payouts are not read, so it has none to show rather than a zero
    assert by_source["ALLEGRO"]["paid_out"] is None


def test_without_any_payout_read_there_is_no_total():
    _order("100.00", _day(9, 10))
    assert client.get("/api/v1/finance/summary", params=SEPTEMBER).json()["paid_out"] is None


def test_an_erli_fee_goes_to_the_item_it_names_by_its_id():
    placed = _order(
        "42.51",
        _day(9, 26),
        source=OrderSource.ERLI,
        items=[("Baza", 1, "30.00", "112093_656974184_0"), ("Tabliczka", 1, "12.51", "112093_656974185_0")],
        item_ids=["345921069", "345921070"],
    )
    _fee("-8.58", _day(9, 26), type_id="COMM", type_name="naliczenie prowizji", order=placed, offer="345921069", source=OrderSource.ERLI)

    items = client.get("/api/v1/finance/products", params=SEPTEMBER).json()["items"]

    by_name = {row["name"]: Decimal(row["fees"]) for row in items}
    assert by_name == {"Baza": Decimal("8.58"), "Tabliczka": Decimal("0.00")}
