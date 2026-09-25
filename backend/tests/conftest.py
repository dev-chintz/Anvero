import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _test_database_url() -> str:
    """The database the suite runs against.

    TEST_DATABASE_URL, from the environment or backend/.env, selects a real
    server such as PostgreSQL; without it the suite uses its own SQLite file,
    so a fresh clone runs the tests with no setup.

    The API test modules call Base.metadata.drop_all() on teardown, so the
    suite refuses a TEST_DATABASE_URL naming the development database: running
    the tests would wipe it.
    """
    env_file = dotenv_values(BACKEND_DIR / ".env")
    test_url = os.environ.get("TEST_DATABASE_URL") or env_file.get("TEST_DATABASE_URL")
    if not test_url:
        return "sqlite:///./test_suite.db"

    dev_url = os.environ.get("DATABASE_URL") or env_file.get("DATABASE_URL")
    if dev_url:
        test, dev = make_url(test_url), make_url(dev_url)
        if (test.host, test.port, test.database) == (dev.host, dev.port, dev.database):
            raise pytest.UsageError(
                "TEST_DATABASE_URL names the same database as DATABASE_URL; "
                "the test suite drops every table, so it needs a database of its own"
            )
    return test_url


# Point the suite at its own database before app.core.config is imported.
os.environ["DATABASE_URL"] = _test_database_url()

# Date-filter tests reason about calendar days in a specific zone; pin it so a
# different BUSINESS_TIMEZONE in a developer's .env cannot change the answers.
os.environ["BUSINESS_TIMEZONE"] = "Europe/Warsaw"

# The API refuses to start without a strong signing key. A fixed one keeps the
# suite independent of whatever a developer's .env holds.
os.environ["SECRET_KEY"] = "test-suite-signing-key-not-used-anywhere-else-0123456789"

# No test starts the backend's own schedule (and a developer's .env must not
# change what the app does when a test starts it).
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["ALLEGRO_IMPORT_INTERVAL_MINUTES"] = "15"

# Never let a test reach the real Allegro API with a developer's credentials.
# A refresh there rotates the token: the replacement would be stored in the
# test database and the developer's real one would stop working a minute
# later, silently. Empty values make any unpatched client report "not
# configured" instead.
for _name in (
    "ALLEGRO_CLIENT_ID",
    "ALLEGRO_CLIENT_SECRET",
    "ALLEGRO_REFRESH_TOKEN",
    "ALLEGRO_USER_AGENT",
):
    os.environ[_name] = ""


@pytest.fixture
def session():
    """A session on a freshly created schema, dropped after the test.

    On SQLite each test gets its own in-memory database. With
    TEST_DATABASE_URL it is the suite's database server instead, so the
    repository code that branches on dialect runs on the dialect it was
    written for; an in-memory SQLite here left the PostgreSQL branches
    untested even when the rest of the suite ran on PostgreSQL.
    """
    # imported here, not at the top: app.core.config must not load before
    # DATABASE_URL is set above
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import settings
    from app.db.base import Base

    if make_url(settings.database_url).get_backend_name() == "sqlite":
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(settings.database_url)

    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Give every test its own login rate-limit budget.

    The limiter is process-wide, so once the suite makes more than five login
    attempts in a minute, later tests would get 429 depending only on order.
    """
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
