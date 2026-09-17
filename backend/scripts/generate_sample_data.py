#!/usr/bin/env python3
"""
Generate sample order data for development and testing.

Usage:
    python scripts/generate_sample_data.py [--force]

--force skips the confirmation prompt when the database already has orders,
so the script can run unattended.
"""

import sys
from pathlib import Path
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from app.db.session import SessionLocal
from app.models.order import Order, OrderSource, OrderStatus, OrderStatusHistory

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
            db.query(Order).delete()
            db.commit()
            print("Existing orders and status history deleted.")

        # Generate orders
        created_count = 0
        now = datetime.now(UTC)

        for order_data in SAMPLE_ORDERS:
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

    except Exception as e:
        print(f"✗ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 Anvero Sample Data Generator")
    print("=" * 40)
    generate_sample_data(force="--force" in sys.argv)
