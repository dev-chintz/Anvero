"""Finding a newer published version, and asking the updater for it."""

import httpx2
import pytest

from app.core.config import settings
from app.services import updates
from app.services.updates import UpdateChecker, UpdateError

OLD = "a" * 40
MID = "b" * 40
NEW = "c" * 40


class FakeWeb:
    """GitHub and the registry: commits newest first, and the tags published."""

    def __init__(self, commits, published, github_status=200):
        self.commits = commits
        self.published = published
        self.github_status = github_status
        self.requests = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        url = str(request.url)
        if url.startswith("https://ghcr.io/token"):
            return httpx2.Response(200, json={"token": "anon"})
        if "/manifests/" in url:
            tag = url.rsplit("/", 1)[1]
            return httpx2.Response(200 if tag in self.published else 404)
        if self.github_status != 200:
            return httpx2.Response(self.github_status, json={})
        if "/compare/" in url:
            base, head = url.rsplit("/", 1)[1].split("...")
            shas = [c for c in reversed(self.commits)]
            start = shas.index(base) + 1
            end = shas.index(head) + 1
            between = shas[start:end]
            return httpx2.Response(
                200,
                json={
                    "ahead_by": len(between),
                    "commits": [
                        {"sha": s, "commit": {"message": f"Change {s[0]}\n\nbody", "committer": {"date": "2026-09-28T10:00:00Z"}}}
                        for s in between
                    ],
                },
            )
        if "/commits" in url:
            return httpx2.Response(200, json=[{"sha": s} for s in self.commits])
        return httpx2.Response(404)


def _checker(web):
    return UpdateChecker(httpx2.Client(transport=httpx2.MockTransport(web.handler)))


def test_the_newest_published_commit_is_offered_with_what_changed():
    # NEW is on main but its images are not built yet
    web = FakeWeb([NEW, MID, OLD], published={MID[:7], OLD[:7]})

    state = _checker(web).check(OLD)

    assert state.latest == MID
    assert state.available
    assert state.behind == 1
    assert [(c.sha, c.title) for c in state.changes] == [(MID[:7], "Change b")]


def test_nothing_is_offered_when_the_running_commit_is_the_newest_published():
    web = FakeWeb([NEW, OLD], published={OLD[:7]})

    state = _checker(web).check(OLD)

    assert state.latest == OLD
    assert not state.available
    assert state.behind == 0


def test_a_version_counts_only_when_both_images_are_published():
    web = FakeWeb([NEW, OLD], published={NEW[:7]})
    # the registry answers 200 for NEW under any image name, so check the
    # names asked for: backend, then web
    state = _checker(web).check(OLD)
    names = [str(r.url) for r in web.requests if "/manifests/" in str(r.url)]
    assert any("anvero-backend" in n for n in names)
    assert any("anvero-web" in n for n in names)
    assert state.latest == NEW


def test_off_an_image_the_version_is_unknown_and_nothing_is_offered():
    web = FakeWeb([NEW, OLD], published={NEW[:7], OLD[:7]})

    state = _checker(web).check(None)

    assert state.latest == NEW
    assert not state.available


def test_github_refusing_is_an_update_error():
    web = FakeWeb([NEW], published=set(), github_status=403)

    with pytest.raises(UpdateError, match="403"):
        _checker(web).check(OLD)


def test_a_failed_check_keeps_what_was_known_and_says_why(monkeypatch):
    monkeypatch.setattr(settings, "app_commit", OLD)
    good = FakeWeb([NEW, OLD], published={NEW[:7]})
    updates.check_now(_checker(good))

    state = updates.check_now(_checker(FakeWeb([NEW], published=set(), github_status=500)))

    assert state.latest == NEW
    assert state.available
    assert "500" in state.error


# --- the updater -----------------------------------------------------------------------------


def _updater_client(status_code, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(request)
        return httpx2.Response(status_code, json={"running": False, "result": "ok"})

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def test_without_a_token_the_updater_is_not_asked(monkeypatch):
    monkeypatch.setattr(settings, "updater_token", "")

    assert not updates.updater_configured()
    assert updates.updater_status() is None
    with pytest.raises(UpdateError, match="not set up"):
        updates.start_update()


def test_the_updater_is_asked_with_the_token(monkeypatch):
    monkeypatch.setattr(settings, "updater_token", "x" * 40)
    seen = []

    updates.start_update(_updater_client(202, seen))

    assert seen[0].method == "POST"
    assert str(seen[0].url).endswith("/update")
    assert seen[0].headers["Authorization"] == "Bearer " + "x" * 40


@pytest.mark.parametrize(("code", "message"), [(409, "already running"), (401, "refused"), (500, "500")])
def test_what_the_updater_refuses_is_said(monkeypatch, code, message):
    monkeypatch.setattr(settings, "updater_token", "x" * 40)

    with pytest.raises(UpdateError, match=message):
        updates.start_update(_updater_client(code))
