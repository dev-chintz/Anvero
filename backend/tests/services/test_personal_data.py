"""One buyer's request: finding, exporting and erasing what is held about them."""

import json
from datetime import UTC, datetime

import pytest

from app.models.order import Order
from app.services.personal_data import anonymize_person, export_person, find_person
from app.services.retention import apply_retention
from tests.services.test_retention import _case, _order, _thread, _write

NOW = datetime(2027, 3, 1, 12, 0, tzinfo=UTC)


def test_a_login_or_an_email_is_required(session):
    with pytest.raises(ValueError):
        find_person(session, login=" ", email=None)


def test_the_buyer_is_found_by_login_ignoring_case_with_their_orders_threads_and_cases(session):
    order = _order(session, "O-1", datetime(2026, 5, 1, tzinfo=UTC))
    other = _order(session, "O-2", datetime(2026, 5, 1, tzinfo=UTC))
    other.customer_login, other.customer_email = "someone_else", "else@example.com"
    session.commit()
    by_login = _thread(session, "T-1", datetime(2026, 5, 2, tzinfo=UTC))
    # names no one, but is about the buyer's order
    by_order = _thread(session, "T-2", datetime(2026, 5, 3, tzinfo=UTC))
    by_order.interlocutor_login = None
    by_order.order_external_id = "O-1"
    _case(session, "C-1", datetime(2026, 5, 4, tzinfo=UTC))
    session.commit()

    person = find_person(session, login="ANNA_N")

    assert [o.external_id for o in person.orders] == [order.external_id]
    assert {t.external_id for t in person.threads} == {by_login.external_id, by_order.external_id}
    assert [c.external_id for c in person.cases] == ["C-1"]


def test_the_buyer_is_found_by_email_alone(session):
    _order(session, "O-1", datetime(2026, 5, 1, tzinfo=UTC))

    assert len(find_person(session, email="Anna@Example.com").orders) == 1
    assert find_person(session, email="nobody@example.com").empty


def test_the_export_holds_everything_and_is_json(session):
    order = _order(session, "O-1", datetime(2026, 5, 1, tzinfo=UTC))
    _write(session, datetime(2026, 5, 2, tzinfo=UTC), order)
    _thread(session, "T-1", datetime(2026, 5, 2, tzinfo=UTC))

    data = export_person(session, find_person(session, login="anna_n"))

    text = json.dumps(data, ensure_ascii=False)
    exported = data["orders"][0]
    assert exported["customer_last_name"] == "Nowak"
    assert exported["addresses"][0]["street"] == "Długa 1"
    assert exported["items"][0]["name"] == "Kubek"
    assert "Anna Nowak" in exported["sent_to_marketplace"][0]["payload"]
    assert data["message_threads"][0]["messages"][0]["text"] == "Kiedy wysyłka?"
    assert "Nowak" in text


def test_erasing_keeps_a_company_invoice_while_the_tax_period_runs(session):
    recent = _order(session, "O-NEW", datetime(2026, 5, 1, tzinfo=UTC))
    old = _order(session, "O-OLD", datetime(2019, 5, 1, tzinfo=UTC))
    thread = _thread(session, "T-1", datetime(2026, 5, 2, tzinfo=UTC))

    result = anonymize_person(session, find_person(session, login="anna_n"), NOW)

    assert (result.orders, result.invoices_kept, result.threads) == (2, 1, 1)
    session.refresh(recent)
    assert recent.anonymized_at is not None
    assert (recent.customer_last_name, recent.customer_email) == (None, "")
    invoice = recent.addresses[0]
    assert (invoice.company_name, invoice.tax_id, invoice.street) == ("Nowak Design", "6751234567", "Długa 1")
    assert (invoice.first_name, invoice.phone) == (None, None)
    session.refresh(old)
    assert old.addresses[0].tax_id is None
    session.refresh(thread)
    assert thread.interlocutor_login is None
    # and the buyer is no longer found by the login
    assert find_person(session, login="anna_n").orders == []


def test_retention_erases_a_kept_invoice_once_its_period_is_over(session):
    recent = _order(session, "O-NEW", datetime(2026, 5, 1, tzinfo=UTC))
    anonymize_person(session, find_person(session, login="anna_n"), NOW)

    # 2026 is taxed in 2027 and kept through 2032
    assert apply_retention(session, datetime(2032, 12, 1, tzinfo=UTC)).orders == 0
    assert apply_retention(session, datetime(2033, 1, 2, tzinfo=UTC)).orders == 1

    session.refresh(recent)
    assert recent.addresses[0].tax_id is None
    assert session.query(Order).count() == 1
