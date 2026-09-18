import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, resolve_sqlite_path

REPO_ROOT = BACKEND_DIR.parent


def test_a_relative_sqlite_path_is_anchored_to_backend():
    url = resolve_sqlite_path("sqlite:///./anvero.db")

    assert Path(make_url(url).database) == (BACKEND_DIR / "anvero.db").resolve()


def test_a_bare_relative_sqlite_path_is_anchored_too():
    url = resolve_sqlite_path("sqlite:///data/anvero.db")

    assert Path(make_url(url).database) == (BACKEND_DIR / "data" / "anvero.db").resolve()


def test_an_absolute_sqlite_path_is_left_alone():
    absolute = str((REPO_ROOT / "elsewhere" / "anvero.db").resolve())

    url = resolve_sqlite_path(f"sqlite:///{absolute}")

    assert Path(make_url(url).database) == Path(absolute)


def test_in_memory_sqlite_is_left_alone():
    assert resolve_sqlite_path("sqlite://") == "sqlite://"
    assert resolve_sqlite_path("sqlite:///:memory:") == "sqlite:///:memory:"


def test_other_databases_pass_through_untouched_including_the_password():
    url = "postgresql+psycopg://postgres:s3cret@localhost:5432/anvero"

    assert resolve_sqlite_path(url) == url


def test_the_database_is_the_same_whichever_directory_a_command_runs_from():
    """Regression: from the project root, `sqlite:///./test.db` pointed at a
    new, empty file there instead of backend/test.db."""
    probe = (
        "import sys; sys.path.insert(0, 'backend'); "
        "from app.core.config import settings; print(settings.database_url)"
    )

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "DATABASE_URL": "sqlite:///./cwd_probe.db"},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    database = Path(make_url(result.stdout.strip()).database)
    assert database == (BACKEND_DIR / "cwd_probe.db").resolve()
