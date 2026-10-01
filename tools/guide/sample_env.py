"""The environment of the guide's screenshots: its own SQLite database and pictures folder, no
schedule, and a made-up setup. Imported before anything of the application is, by the seed and by
the server, so neither can touch the real database (docs/GUIDE.md)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
# where the scratch database, the pictures and the token live; never in Git
WORK = Path(os.environ.get("GUIDE_WORK", ROOT / "tools" / "guide" / ".work")).resolve()
WORK.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{(WORK / 'guide.db').as_posix()}"
os.environ["CATALOG_IMAGES_DIR"] = str(WORK / "pictures")
os.environ["SCHEDULER_ENABLED"] = "false"
# a version, so the Updates tab shows what a deployed server shows; checking for a newer one is off
os.environ["APP_COMMIT"] = "6284a58c0ffee0123456789abcdef0123456789a"
os.environ["UPDATE_CHECK_MINUTES"] = "0"
# a made-up key, so Erli counts as connected; the application is never started with the scheduler, and
# nothing in the screenshots presses a button that calls a marketplace
os.environ["ERLI_API_KEY"] = "guide-sample-not-a-real-key"
for _name in ("ALLEGRO_CLIENT_ID", "ALLEGRO_CLIENT_SECRET", "ALLEGRO_REFRESH_TOKEN", "ALLEGRO_USER_AGENT"):
    os.environ[_name] = ""
