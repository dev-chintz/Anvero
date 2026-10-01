"""The backend on the guide's scratch database, as it looks when everything works (docs/GUIDE.md)."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sample_env  # noqa: E402  (sets the environment first)

sys.path.insert(0, str(sample_env.BACKEND))

import uvicorn  # noqa: E402

from app.services.allegro_sync import schedule_state  # noqa: E402
from app.services.message_sync import message_schedule_state  # noqa: E402
from app.services.schedule import erli_schedule_state  # noqa: E402

# the schedule is off in this process, so the status page would warn that imports are set but not running;
# these are what a running one reports, for the screenshot
now = datetime.now(UTC)
for state in (schedule_state, erli_schedule_state, message_schedule_state):
    state.interval_minutes = 15
    state.running = True
    state.started_at = now - timedelta(hours=2)
    state.last_run_at = now - timedelta(minutes=6)
    state.next_run_at = now + timedelta(minutes=9)

uvicorn.run("app.main:app", app_dir=str(sample_env.BACKEND), host="127.0.0.1", port=8000)
