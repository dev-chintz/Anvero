import os

# Point the suite at its own database before app.core.config is imported.
# The API test modules call Base.metadata.drop_all() on teardown, so sharing
# the development database would wipe local data on every test run.
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
