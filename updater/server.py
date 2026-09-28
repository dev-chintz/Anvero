"""Anvero's updater: pulls the newest images and recreates the backend and web
containers, when the backend asks (docs/DEPLOYMENT.md, "Updating from Settings").

It holds the Docker socket, which is as good as root on the NAS, so it is kept
small and closed: it listens only on the application's own Docker network (no
published port), answers only a request carrying UPDATER_TOKEN, and can do one
thing, the same two compose commands every time. Standard library only.

    GET  /status   what the last run did
    POST /update   start a run; 202, or 409 while one is running

Environment: UPDATER_TOKEN (required), COMPOSE_FILE (default
/project/docker-compose.yml, the application's own compose file mounted
read-only), UPDATE_SERVICES (default "backend web"), PORT (default 8080).
"""

import hmac
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG_KEPT = 4000


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Updater:
    def __init__(self, compose_file: str, services: list[str], run=subprocess.run):
        self.compose_file = compose_file
        self.services = services
        self._run = run
        self._lock = threading.Lock()
        self.state = {"running": False, "started_at": None, "finished_at": None, "result": None, "log": None}

    def commands(self) -> list[list[str]]:
        base = ["docker", "compose", "-f", self.compose_file]
        return [
            base + ["pull", *self.services],
            # --no-deps: only these; the updater itself is never recreated
            # from inside, which would cut its own run short
            base + ["up", "-d", "--no-deps", *self.services],
        ]

    def start(self) -> bool:
        """Start a run in the background; false when one is running."""
        with self._lock:
            if self.state["running"]:
                return False
            self.state.update(running=True, started_at=_now(), finished_at=None, result=None, log=None)
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self) -> None:
        log, result = [], "ok"
        for command in self.commands():
            log.append("$ " + " ".join(command))
            try:
                done = self._run(command, capture_output=True, text=True, timeout=900)
                log.append((done.stdout or "") + (done.stderr or ""))
                if done.returncode != 0:
                    result = "failed"
                    break
            except Exception as exc:  # a missing docker binary, a timeout
                log.append(repr(exc))
                result = "failed"
                break
        text = "\n".join(log)
        print(text, flush=True)
        with self._lock:
            self.state.update(running=False, finished_at=_now(), result=result, log=text[-LOG_KEPT:])


def make_handler(updater: Updater, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given.encode(), f"Bearer {token}".encode())

        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._authorized():
                return self._send(401, {"detail": "unauthorized"})
            if self.path != "/status":
                return self._send(404, {"detail": "not found"})
            self._send(200, dict(updater.state))

        def do_POST(self):
            if not self._authorized():
                return self._send(401, {"detail": "unauthorized"})
            if self.path != "/update":
                return self._send(404, {"detail": "not found"})
            if not updater.start():
                return self._send(409, {"detail": "an update is running"})
            self._send(202, {"started": True})

        def log_message(self, format, *args):
            # the path and code only, never the headers (the token)
            sys.stderr.write(f"{self.command} {self.path.split('?')[0]}\n")

    return Handler


def main() -> int:
    token = os.environ.get("UPDATER_TOKEN", "").strip()
    if len(token) < 32:
        print("UPDATER_TOKEN must be set to at least 32 random characters", file=sys.stderr)
        return 1
    updater = Updater(
        os.environ.get("COMPOSE_FILE", "/project/docker-compose.yml"),
        os.environ.get("UPDATE_SERVICES", "backend web").split(),
    )
    port = int(os.environ.get("PORT", "8080"))
    print(f"Anvero updater listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(updater, token)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
