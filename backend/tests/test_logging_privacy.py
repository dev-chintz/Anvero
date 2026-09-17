"""Personal data and tokens must not reach logs or error messages.

Regression: with DEBUG=true, the default in .env.example, the engine echoed
every statement with its values, so buyers' details and rotated Allegro
refresh tokens were printed to the console; and the access log wrote search
terms such as a buyer's email as part of the request URL.
"""

import logging
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.logging import DropQueryString, setup_logging
from app.db.base import Base
from app.db.session import engine
from app.models.integration import IntegrationCredential
from app.models.order import Order, OrderSource

BUYER_EMAIL = "private-buyer@example.com"
REFRESH_TOKEN = "secret-refresh-token-value"


@pytest.fixture
def app_db():
    """A session on the application's own engine, with its real settings."""
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        Base.metadata.drop_all(bind=engine)


def _order():
    return Order(
        id=uuid.uuid4(),
        external_id="PRIVACY-1",
        source=OrderSource.ALLEGRO,
        customer_email=BUYER_EMAIL,
        total_amount=Decimal("10.00"),
    )


def test_sql_echo_is_off_by_default_and_independent_of_debug():
    assert Settings.model_fields["sql_echo"].default is False
    assert engine.echo is False


def test_the_engine_hides_parameter_values():
    assert engine.hide_parameters is True


def test_a_database_error_does_not_carry_the_values(app_db):
    app_db.add(_order())
    app_db.commit()
    app_db.add(_order())

    with pytest.raises(IntegrityError) as excinfo:
        app_db.commit()

    assert BUYER_EMAIL not in str(excinfo.value)


def test_echoed_statements_do_not_show_values(app_db, caplog):
    engine.echo = True
    try:
        with caplog.at_level(logging.INFO, logger="sqlalchemy.engine"):
            app_db.add(_order())
            app_db.add(IntegrationCredential(provider="ALLEGRO", refresh_token=REFRESH_TOKEN, seed_fingerprint="x"))
            app_db.commit()
    finally:
        engine.echo = False

    assert "INSERT INTO orders" in caplog.text
    assert BUYER_EMAIL not in caplog.text
    assert REFRESH_TOKEN not in caplog.text


def _access_record(path):
    # the arguments uvicorn passes to its access log call
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:50000", "GET", path, "1.1", 200),
        None,
    )


def test_the_access_log_drops_query_strings():
    record = _access_record(f"/api/v1/orders?search={BUYER_EMAIL}&skip=0")

    DropQueryString().filter(record)

    message = record.getMessage()
    assert BUYER_EMAIL not in message
    assert '"GET /api/v1/orders?... HTTP/1.1" 200' in message


def test_a_path_without_a_query_string_is_logged_unchanged():
    record = _access_record("/api/v1/orders/stats")

    DropQueryString().filter(record)

    assert '"GET /api/v1/orders/stats HTTP/1.1"' in record.getMessage()


def test_setup_attaches_the_filter_to_the_access_log_once():
    setup_logging()
    setup_logging()

    filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(f, DropQueryString) for f in filters) == 1
