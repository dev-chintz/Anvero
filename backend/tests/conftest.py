import os

import pytest

# Point the suite at its own database before app.core.config is imported.
# The API test modules call Base.metadata.drop_all() on teardown, so sharing
# the development database would wipe local data on every test run.
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"

# Date-filter tests reason about calendar days in a specific zone; pin it so a
# different BUSINESS_TIMEZONE in a developer's .env cannot change the answers.
os.environ["BUSINESS_TIMEZONE"] = "Europe/Warsaw"

# The API refuses to start without a strong signing key. A fixed one keeps the
# suite independent of whatever a developer's .env holds.
os.environ["SECRET_KEY"] = "test-suite-signing-key-not-used-anywhere-else-0123456789"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Give every test its own login rate-limit budget.

    The limiter is process-wide, so once the suite makes more than five login
    attempts in a minute, later tests would get 429 depending only on order.
    """
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
