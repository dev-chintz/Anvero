#!/usr/bin/env python3
"""
Generate sample order data for development and testing.

Usage:
    python scripts/generate_sample_data.py [--force]

--force skips the confirmation prompt when the database already has orders,
so the script can run unattended.
"""

import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.order import (
    Order,
    OrderAddress,
    OrderItem,
    OrderSource,
    OrderStatus,
    OrderStatusHistory,
    PaymentType,
)
from app.schemas.order import (
    Address,
    Customer,
    Delivery,
    Invoice,
    OrderDetails,
    OrderItemCreate,
    Payment,
    PickupPoint,
)
from app.services.order_details import apply_details

# Sample customer emails
CUSTOMER_EMAILS = [
    "customer1@example.com",
    "customer2@example.com",
    "john.doe@email.com",
    "jane.smith@email.com",
    "buyer123@test.com",
]

# Sample data
SAMPLE_ORDERS = [
    {
        "external_id": "ALG-001-2024",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.NEW,
        "customer_email": "customer1@example.com",
        "total_amount": Decimal("149.99"),
        "currency": "PLN",
        "days_ago": 0,
    },
    {
        "external_id": "ALG-002-2024",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.CONFIRMED,
        "customer_email": "customer2@example.com",
        "total_amount": Decimal("299.50"),
        "currency": "PLN",
        "days_ago": 1,
    },
    {
        "external_id": "ALG-003-2024",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.SHIPPED,
        "customer_email": "john.doe@email.com",
        "total_amount": Decimal("89.99"),
        "currency": "PLN",
        "days_ago": 2,
    },
    {
        "external_id": "ERLI-001-2024",
        "source": OrderSource.ERLI,
        "status": OrderStatus.DELIVERED,
        "customer_email": "jane.smith@email.com",
        "total_amount": Decimal("450.00"),
        "currency": "PLN",
        "days_ago": 3,
    },
    {
        "external_id": "ERLI-002-2024",
        "source": OrderSource.ERLI,
        "status": OrderStatus.NEW,
        "customer_email": "buyer123@test.com",
        "total_amount": Decimal("199.99"),
        "currency": "PLN",
        "days_ago": 0,
    },
    {
        "external_id": "ALG-004-2024",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.CONFIRMED,
        "customer_email": "customer1@example.com",
        "total_amount": Decimal("599.00"),
        "currency": "PLN",
        "days_ago": 1,
    },
    {
        "external_id": "ALG-005-2024",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.SHIPPED,
        "customer_email": "customer2@example.com",
        "total_amount": Decimal("124.50"),
        "currency": "PLN",
        "days_ago": 5,
    },
    {
        "external_id": "ERLI-003-2024",
        "source": OrderSource.ERLI,
        "status": OrderStatus.DELIVERED,
        "customer_email": "john.doe@email.com",
        "total_amount": Decimal("750.00"),
        "currency": "PLN",
        "days_ago": 7,
    },
    {
        "external_id": "ALG-006-2024",
        "source": OrderSource.ALLEGRO,
        "status": OrderStatus.CANCELLED,
        "customer_email": "jane.smith@email.com",
        "total_amount": Decimal("99.99"),
        "currency": "PLN",
        "days_ago": 2,
    },
    {
        "external_id": "ERLI-004-2024",
        "source": OrderSource.ERLI,
        "status": OrderStatus.NEW,
        "customer_email": "buyer123@test.com",
        "total_amount": Decimal("349.99"),
        "currency": "PLN",
        "days_ago": 0,
    },
]


# (first name, last name, street, postal code, city, phone)
SAMPLE_PEOPLE = [
    ("Jan", "Kowalski", "Prosta 1/4", "00-838", "Warszawa", "+48 600 100 200"),
    ("Anna", "Nowak", "Długa 15", "31-147", "Kraków", "+48 601 200 300"),
    ("Piotr", "Wiśniewski", "Ogrodowa 7", "80-001", "Gdańsk", "+48 602 300 400"),
    ("Maria", "Wójcik", "Lipowa 22", "50-001", "Wrocław", "+48 603 400 500"),
    ("Tomasz", "Kamiński", "Polna 3", "60-001", "Poznań", "+48 604 500 600"),
]

# (name, sku, unit price)
SAMPLE_PRODUCTS = [
    ("Kubek ceramiczny 350 ml", "KUB-350", Decimal("24.99")),
    ("Ręcznik bawełniany 70x140", "REC-70140", Decimal("39.90")),
    ("Lampka biurkowa LED", "LAM-LED-01", Decimal("89.00")),
    ("Organizer na biurko", "ORG-BIU", Decimal("34.50")),
    ("Zestaw noży kuchennych", "NOZ-SET5", Decimal("149.00")),
]


def sample_details(index: int, total: Decimal) -> OrderDetails:
    """Plausible details for sample order `index`, varied across orders.

    The items are priced so that, with delivery, they add up to the order's
    total, as they would on a real order.
    """
    first, last, street, postal_code, city, phone = SAMPLE_PEOPLE[
        index % len(SAMPLE_PEOPLE)
    ]
    name, sku, price = SAMPLE_PRODUCTS[index % len(SAMPLE_PRODUCTS)]
    delivery_cost = Decimal("12.99")
    items = [OrderItemCreate(name=name, sku=sku, quantity=1, unit_price=price)]
    # the rest of the total becomes a second line, so totals stay consistent
    remainder = total - price - delivery_cost
    if remainder > 0:
        extra_name, extra_sku, _ = SAMPLE_PRODUCTS[(index + 2) % len(SAMPLE_PRODUCTS)]
        items.append(
            OrderItemCreate(name=extra_name, sku=extra_sku, quantity=1, unit_price=remainder)
        )
    else:
        items[0] = items[0].model_copy(update={"unit_price": total - delivery_cost})

    home = Address(
        first_name=first,
        last_name=last,
        street=street,
        postal_code=postal_code,
        city=city,
        country_code="PL",
        phone=phone,
    )
    by_locker = index % 3 == 0
    cash_on_delivery = index % 4 == 1
    wants_invoice = index % 3 == 2

    return OrderDetails(
        customer=Customer(
            login=f"{first.lower()}_{index}",
            first_name=first,
            last_name=last,
            phone=phone,
        ),
        items=items,
        delivery=Delivery(
            method="InPost Paczkomat 24/7" if by_locker else "Kurier DPD",
            cost=delivery_cost,
            address=home,
            pickup_point=(
                PickupPoint(
                    id=f"{city[:3].upper()}01M",
                    name=f"Paczkomat {city[:3].upper()}01M",
                    address=Address(
                        street="Handlowa 2",
                        postal_code=postal_code,
                        city=city,
                        country_code="PL",
                    ),
                )
                if by_locker
                else None
            ),
        ),
        payment=(
            Payment(type=PaymentType.CASH_ON_DELIVERY)
            if cash_on_delivery
            else Payment(type=PaymentType.ONLINE, provider="P24", paid_amount=total)
        ),
        invoice=Invoice(
            required=wants_invoice,
            address=(
                Address(
                    company_name=f"{last} Handel Sp. z o.o.",
                    street=street,
                    postal_code=postal_code,
                    city=city,
                    country_code="PL",
                    tax_id="5260250274",
                )
                if wants_invoice
                else None
            ),
        ),
        buyer_message="Proszę o staranne zapakowanie." if index % 4 == 0 else None,
        seller_note="Stały klient, wysyłka priorytetowa." if index % 5 == 0 else None,
    )


def generate_sample_data(force: bool = False):
    """Generate and insert sample orders into the database."""
    db = SessionLocal()

    try:
        # Check if data already exists
        existing_count = db.query(Order).count()
        if existing_count > 0:
            print(f"Database already contains {existing_count} orders.")
            if not force:
                response = (
                    input("Do you want to clear and regenerate? (y/n): ")
                    .strip()
                    .lower()
                )
                if response != "y":
                    print("Cancelled.")
                    return

            # bulk delete bypasses the ORM cascade, and SQLite does not
            # enforce foreign keys by default, so clear the children first
            # rather than leaving orphaned history rows behind
            db.query(OrderStatusHistory).delete()
            db.query(OrderItem).delete()
            db.query(OrderAddress).delete()
            db.query(Order).delete()
            db.commit()
            print("Existing orders, their details and status history deleted.")

        # Generate orders
        created_count = 0
        now = datetime.now(UTC)

        for index, order_data in enumerate(SAMPLE_ORDERS):
            order = Order(
                id=uuid.uuid4(),
                external_id=order_data["external_id"],
                source=order_data["source"],
                status=order_data["status"],
                customer_email=order_data["customer_email"],
                total_amount=order_data["total_amount"],
                currency=order_data["currency"],
                # spread over past days, or every sample would count as ordered
                # today and date filters would have nothing to separate
                ordered_at=now - timedelta(days=order_data["days_ago"]),
                created_at=now - timedelta(days=order_data["days_ago"]),
                updated_at=now - timedelta(days=order_data["days_ago"]),
            )
            apply_details(order, sample_details(index, order_data["total_amount"]))
            if order.paid_amount is not None:
                order.paid_at = order.ordered_at
            db.add(order)
            created_count += 1

        db.commit()
        print(f"✓ Successfully created {created_count} sample orders")

        # Print summary
        print("\n📊 Generated orders summary:")
        by_source = db.query(Order.source, func.count()).group_by(Order.source).all()
        for source, count in by_source:
            print(f"  - {source.value}: {count} orders")

        by_status = db.query(Order.status, func.count()).group_by(Order.status).all()
        for status, count in by_status:
            print(f"  - {status.value}: {count} orders")

        total_revenue = db.query(func.sum(Order.total_amount)).scalar() or 0
        print(f"\n💰 Total revenue: {total_revenue:,.2f} PLN")

    except Exception as e:  # noqa: BLE001 -- CLI script: report and roll back on any failure
        print(f"✗ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 Anvero Sample Data Generator")
    print("=" * 40)
    generate_sample_data(force="--force" in sys.argv)
