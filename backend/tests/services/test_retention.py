"""Retention: personal data past its period is erased, and nothing brings it back."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal

from app.models.after_sales import AfterSalesCase, CaseAction, CaseKind
from app.models.marketplace_write import AppSetting, MarketplaceWrite, WriteOutcome
from app.models.message import Message, MessageDirection, MessageThread
from app.models.order import AddressType, Order, OrderAddress, OrderItem, OrderSource, OrderStatus
from app.repositories.after_sales_repository import AfterSalesRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.after_sales import SyncedCase
from app.schemas.message import SyncedThread
from app.services import retention
from app.services.retention import (
    ANONYMIZED_PAYLOAD,
    apply_retention,
    contact_cutoff,
    order_cutoff,
)

NOW = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)


def _order(session, external_id, ordered_at):
    order = Order(
        external_id=external_id,
        source=OrderSource.ALLEGRO,
        status=OrderStatus.DELIVERED,
        customer_email="anna@example.com",
        customer_login="anna_n",
        customer_first_name="Anna",
        customer_last_name="Nowak",
        customer_company_name="Nowak Design",
        customer_phone="+48 600 100 200",
        buyer_message="Proszę o szary kolor",
        internal_note="Anna dzwoniła",
        total_amount=Decimal("120.00"),
        currency="PLN",
        ordered_at=ordered_at,
        pickup_point_id="KRA010",
    )
    order.items.append(OrderItem(position=0, name="Kubek", quantity=2, unit_price=Decimal("60.00")))
    order.addresses.append(
        OrderAddress(
            type=AddressType.INVOICE,
            first_name="Anna",
            last_name="Nowak",
            company_name="Nowak Design",
            street="Długa 1",
            postal_code="30-001",
            city="Kraków",
            country_code="PL",
            phone="+48 600 100 200",
            tax_id="6751234567",
        )
    )
    session.add(order)
    session.commit()
    return order


def _thread(session, external_id, last_message_at):
    thread = MessageThread(
        source=OrderSource.ALLEGRO,
        external_id=external_id,
        interlocutor_login="anna_n",
        last_message_at=last_message_at,
        last_message_text="Kiedy wysyłka?",
    )
    thread.messages.append(
        Message(
            external_id=f"{external_id}-1",
            direction=MessageDirection.IN,
            author_login="anna_n",
            text="Kiedy wysyłka?",
            sent_at=last_message_at,
        )
    )
    session.add(thread)
    session.commit()
    return thread


def _case(session, external_id, opened_at, is_open=False):
    case = AfterSalesCase(
        source=OrderSource.ALLEGRO,
        external_id=external_id,
        kind=CaseKind.CLAIM,
        status="CLOSED",
        is_open=is_open,
        action=CaseAction.NONE,
        buyer_login="anna_n",
        buyer_email="anna@example.com",
        opened_at=opened_at,
        summary="Pęknięty kubek",
        detail="Proszę o zwrot",
    )
    session.add(case)
    session.commit()
    return case


def _write(session, created_at, order=None):
    write = MarketplaceWrite(
        created_at=created_at,
        source=OrderSource.ALLEGRO,
        order_id=order.id if order else None,
        action="shipment_create",
        payload=json.dumps({"receiver": {"name": "Anna Nowak", "street": "Długa 1"}}),
        outcome=WriteOutcome.SENT,
        detail='{"receiver": "Anna Nowak"}',
    )
    session.add(write)
    session.commit()
    return write


# --- the periods -------------------------------------------------------------------------


def test_an_order_is_kept_five_years_after_the_year_its_tax_was_due():
    # an order from 2020 is taxed in 2021 and kept through 2026
    assert order_cutoff(datetime(2026, 12, 31, 22, 0, tzinfo=UTC)).year == 2019
    # from 1 January 2027 in Poland (still 31 December in UTC), 2020 goes
    cutoff = order_cutoff(datetime(2026, 12, 31, 23, 30, tzinfo=UTC))
    assert cutoff == datetime(2020, 12, 31, 23, 0, tzinfo=UTC)


def test_contacts_are_kept_two_years():
    assert contact_cutoff(NOW) == datetime(2025, 3, 1, 12, 0, tzinfo=UTC)
    assert contact_cutoff(datetime(2028, 2, 29, tzinfo=UTC)) == datetime(2026, 2, 28, tzinfo=UTC)


# --- what is erased and what stays -------------------------------------------------------


def test_an_old_order_loses_its_personal_data_and_keeps_its_figures(session):
    order = _order(session, "OLD", datetime(2020, 6, 1, tzinfo=UTC))

    result = apply_retention(session, NOW)

    assert result.orders == 1
    session.refresh(order)
    assert order.anonymized_at is not None
    assert order.customer_email == ""
    assert (order.customer_login, order.customer_first_name, order.customer_last_name) == (None, None, None)
    assert (order.customer_company_name, order.customer_phone) == (None, None)
    assert (order.buyer_message, order.internal_note) == (None, None)
    address = order.addresses[0]
    assert (address.first_name, address.street, address.city, address.phone, address.tax_id) == (
        None, None, None, None, None,
    )
    assert address.country_code == "PL"
    # what the figures need stays
    assert order.total_amount == Decimal("120.00")
    assert order.order_number is not None
    assert [item.name for item in order.items] == ["Kubek"]
    assert order.pickup_point_id == "KRA010"


def test_an_order_inside_its_period_is_left_alone(session):
    order = _order(session, "NEW", datetime(2021, 1, 5, tzinfo=UTC))

    assert apply_retention(session, NOW).orders == 0
    session.refresh(order)
    assert order.anonymized_at is None
    assert order.customer_last_name == "Nowak"


def test_an_old_thread_loses_its_login_and_text(session):
    thread = _thread(session, "T-OLD", datetime(2024, 12, 1, tzinfo=UTC))
    kept = _thread(session, "T-NEW", datetime(2025, 6, 1, tzinfo=UTC))

    assert apply_retention(session, NOW).threads == 1

    session.refresh(thread)
    assert thread.anonymized_at is not None
    assert (thread.interlocutor_login, thread.last_message_text) == (None, None)
    assert [(m.author_login, m.text) for m in thread.messages] == [(None, "")]
    session.refresh(kept)
    assert kept.interlocutor_login == "anna_n"


def test_only_a_closed_old_case_is_anonymized(session):
    closed = _case(session, "C-OLD", datetime(2024, 1, 1, tzinfo=UTC))
    still_open = _case(session, "C-OPEN", datetime(2024, 1, 1, tzinfo=UTC), is_open=True)

    assert apply_retention(session, NOW).cases == 1

    session.refresh(closed)
    assert (closed.buyer_login, closed.buyer_email, closed.summary, closed.detail) == (None,) * 4
    session.refresh(still_open)
    assert still_open.buyer_email == "anna@example.com"


def test_old_writes_and_an_old_orders_writes_are_emptied(session):
    old_write = _write(session, datetime(2024, 1, 1, tzinfo=UTC))
    recent_write = _write(session, datetime(2026, 1, 1, tzinfo=UTC))
    order = _order(session, "OLD", datetime(2020, 6, 1, tzinfo=UTC))
    # recent, but the order it belongs to is being anonymized
    carried = _write(session, datetime(2026, 1, 1, tzinfo=UTC), order)

    assert apply_retention(session, NOW).writes == 2

    for write in (old_write, carried):
        session.refresh(write)
        assert (write.payload, write.detail) == (ANONYMIZED_PAYLOAD, None)
        assert write.action == "shipment_create"
    session.refresh(recent_write)
    assert "Anna" in recent_write.payload


def test_a_dry_run_counts_and_changes_nothing(session):
    order = _order(session, "OLD", datetime(2020, 6, 1, tzinfo=UTC))
    _write(session, datetime(2026, 1, 1, tzinfo=UTC), order)

    result = apply_retention(session, NOW, dry_run=True)

    assert (result.orders, result.writes) == (1, 1)
    session.refresh(order)
    assert order.anonymized_at is None
    assert order.customer_last_name == "Nowak"


def test_running_it_again_finds_nothing(session):
    _order(session, "OLD", datetime(2020, 6, 1, tzinfo=UTC))
    _thread(session, "T-OLD", datetime(2024, 1, 1, tzinfo=UTC))

    assert apply_retention(session, NOW).total == 2
    assert apply_retention(session, NOW).total == 0


# --- nothing brings it back ---------------------------------------------------------------


def test_a_sync_does_not_bring_an_anonymized_case_back(session):
    case = _case(session, "C-OLD", datetime(2024, 1, 1, tzinfo=UTC))
    apply_retention(session, NOW)
    data = SyncedCase(
        kind=CaseKind.CLAIM,
        external_id="C-OLD",
        status="CLOSED",
        is_open=False,
        opened_at=datetime(2024, 1, 1, tzinfo=UTC),
        buyer_login="anna_n",
        buyer_email="anna@example.com",
    )

    AfterSalesRepository(session).upsert(OrderSource.ALLEGRO, data, CaseAction.NONE, None)
    session.commit()

    session.refresh(case)
    assert case.buyer_email is None


def test_an_unchanged_thread_does_not_get_its_login_back(session):
    last = datetime(2024, 1, 1, tzinfo=UTC)
    thread = _thread(session, "T-OLD", last)
    apply_retention(session, NOW)

    # the marketplace reports it again, only its read flag differs
    MessageRepository(session).upsert_thread(
        OrderSource.ALLEGRO,
        SyncedThread(external_id="T-OLD", interlocutor_login="anna_n", last_message_at=last, read=True),
    )

    session.refresh(thread)
    assert thread.interlocutor_login is None
    assert thread.anonymized_at is not None
    assert thread.read is True


def test_a_buyer_writing_again_starts_a_new_contact(session):
    thread = _thread(session, "T-OLD", datetime(2024, 1, 1, tzinfo=UTC))
    apply_retention(session, NOW)

    MessageRepository(session).upsert_thread(
        OrderSource.ALLEGRO,
        SyncedThread(
            external_id="T-OLD", interlocutor_login="anna_n", last_message_at=NOW, read=False
        ),
    )

    session.refresh(thread)
    assert thread.interlocutor_login == "anna_n"
    assert thread.anonymized_at is None
    # the old messages stay erased
    assert [m.text for m in thread.messages] == [""]


# --- once a day ---------------------------------------------------------------------------


def test_the_daily_run_runs_once_a_day(session, monkeypatch):
    monkeypatch.setattr(retention, "SessionLocal", lambda: _Unclosed(session))
    _order(session, "OLD", datetime(2020, 6, 1, tzinfo=UTC))

    first = retention._run_if_not_run_today(NOW)
    second = retention._run_if_not_run_today(NOW)

    assert first is not None and first.orders == 1
    assert second is None
    assert session.get(AppSetting, retention.LAST_RUN_KEY).value == "2027-03-01"


def test_the_daily_loop_keeps_going(monkeypatch):
    runs = []
    monkeypatch.setattr(retention, "_run_if_not_run_today", runs.append)

    async def stop_after_two(_seconds):
        if len(runs) == 2:
            raise asyncio.CancelledError

    try:
        asyncio.run(retention.run_retention_daily(sleep=stop_after_two, clock=lambda: NOW))
    except asyncio.CancelledError:
        pass

    assert runs == [NOW, NOW]


class _Unclosed:
    """The test's own session, which the code under test must not close."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass
