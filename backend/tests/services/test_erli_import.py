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


def test_an_import_run_as_the_script_does_notes_how_it_ended(session):
    from app.services.import_outcome import run_and_record

    run_and_record(
        session,
        PROVIDER,
        lambda: build_erli_import_service(session, client=_erli([_raw()])).sync_orders(),
    )

    credential = IntegrationCredentialRepository(session).get(PROVIDER)
    assert credential.last_import_at is not None
    assert (credential.last_import_created, credential.last_import_updated) == (1, 0)
    # Erli's key does not expire, so there is no token age to show
    assert credential.token_issued_at is None


def test_a_failed_import_run_as_the_script_does_notes_the_error(session):
    from app.integrations.base import IntegrationError
    from app.services.import_outcome import run_and_record

    build_erli_import_service(session, client=_erli([])).sync_orders()

    def failing():
        raise IntegrationError("Erli is unreachable")

    with pytest.raises(IntegrationError):
        run_and_record(session, PROVIDER, failing)

    credential = IntegrationCredentialRepository(session).get(PROVIDER)
    assert credential.last_import_error == "Erli is unreachable"


def test_the_import_uses_the_key_entered_in_settings_over_the_environments(session, monkeypatch):
    from app.core.config import settings
    from app.services import erli_settings

    monkeypatch.setattr(settings, "erli_api_key", "env-key")
    assert erli_settings.resolve_key(session).source == "environment"

    erli_settings.save_key(session, "typed-key", user_id=None)

    resolved = erli_settings.resolve_key(session)
    assert (resolved.value, resolved.source) == ("typed-key", "settings")
    assert erli_settings.build_erli_client(session).api_key == "typed-key"


def test_an_import_with_no_key_anywhere_is_not_configured(session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "erli_api_key", "")

    with pytest.raises(IntegrationNotConfigured):
        build_erli_import_service(session)
