"""An Erli import end to end, against a fake Erli, into the test database."""

import httpx2
import pytest

from app.integrations.base import IntegrationNotConfigured
from app.integrations.erli.client import ErliClient
from app.models.order import Order, OrderSource, OrderStatus
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.services.erli_import import PROVIDER, build_erli_import_service

# `session` comes from tests/conftest.py


def _erli(orders, api_key="key-123"):
    return ErliClient(
        api_key=api_key,
        api_url="https://erli.test/svc/shop-api",
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=orders))
        ),
    )


def _raw(order_id="erli-1", **overrides):
    order = {
        "id": order_id,
        "status": "purchased",
        "user": {"email": "kupujacy@proxy.erli.pl", "deliveryAddress": {"city": "Kraków"}},
        "items": [{"id": 1, "externalId": "p-1", "quantity": 1, "unitPrice": 2500, "name": "Talerz"}],
        "delivery": {"name": "Kurier", "price": 1000},
        "totalPrice": 3500,
        "currency": "PLN",
        "payment": {"status": "COMPLETED"},
        "sellerStatus": "created",
        "created": "2026-09-20T10:00:00Z",
        "updated": "2026-09-20T10:00:00Z",
        "cursor": "1;1",
    }
    order.update(overrides)
    return order


def test_an_import_stores_erli_orders_and_where_it_got_to(session):
    result = build_erli_import_service(session, client=_erli([_raw()])).sync_orders()

    assert (result.created, result.updated) == (1, 0)
    stored = session.query(Order).one()
    assert (stored.source, stored.external_id, stored.status) == (
        OrderSource.ERLI,
        "erli-1",
        OrderStatus.NEW,
    )
    assert IntegrationCredentialRepository(session).last_synced_at(PROVIDER) is not None


def test_the_key_itself_is_never_stored(session):
    build_erli_import_service(session, client=_erli([], api_key="secret-key")).sync_orders()

    row = IntegrationCredentialRepository(session).get(PROVIDER)
    assert "secret-key" not in (row.refresh_token, row.seed_fingerprint)


def test_another_key_starts_the_sync_over(session):
    build_erli_import_service(session, client=_erli([], api_key="shop-a")).sync_orders()

    build_erli_import_service(session, client=_erli([], api_key="shop-b"))

    assert IntegrationCredentialRepository(session).last_synced_at(PROVIDER) is None


def test_a_status_erli_moves_is_followed(session):
    build_erli_import_service(session, client=_erli([_raw()])).sync_orders()

    moved = _raw(deliveryTracking={"status": "sent", "vendor": "inpost", "trackingNumber": "1234"})
    build_erli_import_service(session, client=_erli([moved])).sync_orders()

    stored = session.query(Order).one()
    assert stored.status is OrderStatus.SHIPPED
    assert [s.waybill for s in stored.shipments] == ["1234"]


def test_without_a_key_there_is_no_import(session):
    with pytest.raises(IntegrationNotConfigured):
        build_erli_import_service(session, client=_erli([], api_key=""))
