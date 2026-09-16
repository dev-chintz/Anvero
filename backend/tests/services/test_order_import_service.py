from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.order import Order, OrderSource, OrderStatus
from app.repositories.order_repository import OrderRepository
from app.schemas.order import OrderCreate
from app.services.order_import_service import OrderImportService


class FakeAdapter:
    """Stands in for AllegroAdapter: the import service only needs the port."""

    source = OrderSource.ALLEGRO

    def __init__(self, orders):
        self.orders = orders

    def fetch_orders(self, limit: int = 100, offset: int = 0):
        return self.orders


def _order(external_id="ALG-1", email="buyer@example.com", amount="100.00"):
    return OrderCreate(
        external_id=external_id,
        source=OrderSource.ALLEGRO,
        status=OrderStatus.NEW,
        customer_email=email,
        total_amount=Decimal(amount),
        currency="PLN",
    )


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _service(session, orders):
    return OrderImportService(OrderRepository(session), FakeAdapter(orders))


def test_imports_new_orders(session):
    result = _service(session, [_order("ALG-1"), _order("ALG-2")]).import_orders()

    assert (result.created, result.updated, result.total) == (2, 0, 2)
    assert session.query(Order).count() == 2


def test_re_import_does_not_duplicate(session):
    orders = [_order("ALG-1")]
    _service(session, orders).import_orders()

    result = _service(session, orders).import_orders()

    assert (result.created, result.updated) == (0, 1)
    assert session.query(Order).count() == 1


def test_re_import_keeps_the_status_the_operator_set(session):
    """The Anvero status is the operator's, recorded in the status history.

    A sync overwriting it would silently undo their work, so an order already
    present keeps its status even though the marketplace still reports NEW.
    """
    orders = [_order("ALG-1")]
    _service(session, orders).import_orders()

    stored = session.query(Order).one()
    OrderRepository(session).update_status(stored, OrderStatus.SHIPPED)

    _service(session, orders).import_orders()

    assert session.query(Order).one().status is OrderStatus.SHIPPED


def test_re_import_refreshes_the_fields_the_marketplace_owns(session):
    _service(session, [_order("ALG-1", email="old@example.com", amount="100.00")]).import_orders()

    _service(
        session, [_order("ALG-1", email="new@example.com", amount="250.00")]
    ).import_orders()

    stored = session.query(Order).one()
    assert stored.customer_email == "new@example.com"
    assert stored.total_amount == Decimal("250.00")


def test_an_order_from_another_marketplace_is_not_a_duplicate(session):
    """Order numbers collide across marketplaces."""
    _service(session, [_order("SHARED")]).import_orders()

    erli = _order("SHARED")
    erli = erli.model_copy(update={"source": OrderSource.ERLI})
    result = _service(session, [erli]).import_orders()

    assert result.created == 1
    assert session.query(Order).count() == 2
