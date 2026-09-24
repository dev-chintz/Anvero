"""Safe mode, and the one door every marketplace write goes through."""

import json

import pytest

from app.models.marketplace_write import MarketplaceWrite, WriteOutcome
from app.models.order import OrderSource
from app.models.user import User
from app.services.marketplace_writes import (
    MarketplaceWriter,
    list_writes,
    safe_mode_on,
    set_safe_mode,
)

# `session` comes from tests/conftest.py


class FakeSend:
    def __init__(self, answer=None, error=None):
        self.calls = 0
        self.answer = answer
        self.error = error

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.answer


def _operator(session):
    user = User(email="operator@example.com", hashed_password="x")
    session.add(user)
    session.commit()
    return user


def _write(session, send, **kwargs):
    return MarketplaceWriter(session).write(
        OrderSource.ALLEGRO,
        "fulfillment_status",
        {"status": "SENT", "order": "abc"},
        send,
        **kwargs,
    )


def test_safe_mode_is_on_until_someone_switches_it_off(session):
    assert safe_mode_on(session) is True


def test_in_safe_mode_nothing_is_sent_but_everything_is_recorded(session):
    send = FakeSend()

    result = _write(session, send)

    assert send.calls == 0
    assert result.outcome is WriteOutcome.DRY_RUN
    (record,) = session.query(MarketplaceWrite).all()
    assert record.outcome is WriteOutcome.DRY_RUN
    assert json.loads(record.payload) == {"order": "abc", "status": "SENT"}
    assert record.detail is None


def test_with_safe_mode_off_it_is_sent_and_the_answer_kept(session):
    operator = _operator(session)
    set_safe_mode(session, False, operator.id)
    send = FakeSend(answer={"id": "shipment-1"})

    result = _write(session, send, user_id=operator.id)

    assert send.calls == 1
    assert result.outcome is WriteOutcome.SENT
    assert result.response == {"id": "shipment-1"}
    (record,) = list_writes(session)
    assert json.loads(record.detail) == {"id": "shipment-1"}
    assert record.user_email == "operator@example.com"


def test_a_failed_send_is_recorded_and_raised(session):
    set_safe_mode(session, False, None)

    with pytest.raises(RuntimeError, match="Allegro said no"):
        _write(session, FakeSend(error=RuntimeError("Allegro said no")))

    (record,) = list_writes(session)
    assert (record.outcome, record.detail) == (WriteOutcome.FAILED, "Allegro said no")


def test_switching_it_back_on_stops_the_very_next_write(session):
    set_safe_mode(session, False, None)
    set_safe_mode(session, True, None)
    send = FakeSend()

    assert _write(session, send).outcome is WriteOutcome.DRY_RUN
    assert send.calls == 0


def test_the_log_is_newest_first_and_per_order(session):
    import uuid

    from app.models.order import Order

    order = Order(
        external_id="A-1", source=OrderSource.ALLEGRO, customer_email="b@example.com",
        total_amount=10, currency="PLN",
    )
    session.add(order)
    session.commit()
    _write(session, FakeSend())
    _write(session, FakeSend(), order_id=order.id)

    assert [w.order_id for w in list_writes(session)] == [order.id, None]
    assert [w.order_id for w in list_writes(session, order_id=order.id)] == [order.id]
    assert list_writes(session, order_id=uuid.uuid4()) == []
