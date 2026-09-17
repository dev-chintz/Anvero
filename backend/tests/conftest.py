import os

# Point the suite at its own database before app.core.config is imported.
# The API test modules call Base.metadata.drop_all() on teardown, so sharing
# the development database would wipe local data on every test run.
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"

# Date-filter tests reason about calendar days in a specific zone; pin it so a
# different BUSINESS_TIMEZONE in a developer's .env cannot change the answers.
os.environ["BUSINESS_TIMEZONE"] = "Europe/Warsaw"
