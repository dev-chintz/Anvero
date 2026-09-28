"""The updater's server: only the token gets in, one run at a time, and the
same two compose commands. Run with the backend's interpreter:
backend\\.venv\\Scripts\\python.exe -m pytest updater"""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from server import Updater, make_handler

TOKEN = "t" * 40


@pytest.fixture
def served():
    calls, gate = [], threading.Event()

    def fake_run(command, **_):
        calls.append(command)
        gate.wait(5)
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    updater = Updater("/project/docker-compose.yml", ["backend", "web"], run=fake_run)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(updater, TOKEN))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", calls, gate, updater
    gate.set()
    server.shutdown()


def _call(url, method="GET", token=TOKEN):
    request = urllib.request.Request(url, method=method, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_a_wrong_token_gets_nothing(served):
    url, calls, _, _ = served
    assert _call(f"{url}/update", "POST", token="wrong")[0] == 401
    assert _call(f"{url}/status", token="wrong")[0] == 401
    assert calls == []


def test_an_update_pulls_then_recreates_only_the_named_services(served):
    url, calls, gate, updater = served

    assert _call(f"{url}/update", "POST") == (202, {"started": True})
    # a second one while the first runs is refused
    assert _call(f"{url}/update", "POST")[0] == 409
    assert _call(f"{url}/status")[1]["running"] is True
    gate.set()
    for _ in range(50):
        if not updater.state["running"]:
            break
        time.sleep(0.05)

    base = ["docker", "compose", "-f", "/project/docker-compose.yml"]
    assert calls == [base + ["pull", "backend", "web"], base + ["up", "-d", "--no-deps", "backend", "web"]]
    status = _call(f"{url}/status")[1]
    assert (status["running"], status["result"]) == (False, "ok")


def test_a_failed_pull_stops_before_recreating():
    calls = []

    def failing(command, **_):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="pull access denied")

    updater = Updater("/c.yml", ["backend"], run=failing)
    updater._work()

    assert len(calls) == 1
    assert updater.state["result"] == "failed"
    assert "pull access denied" in updater.state["log"]
