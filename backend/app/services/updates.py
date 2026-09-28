"""Knowing a newer version exists, and asking for it (`DEPLOYMENT.md`, "Updating
from Settings"; `DECISIONS.md`, "Updates from Settings").

A version is a commit on `main` whose images the publish workflow has pushed:
only a commit whose Checks passed gets them, so what is offered has been
through the tests. The backend knows its own commit from `APP_COMMIT`, which
the image sets. Every so often it reads the newest commits on GitHub (the
repository is public, so no token), takes the newest whose backend and web
images are both on GHCR, and when that is not its own, lists what changed in
between.

Updating is not done here: a container cannot recreate itself. The backend
asks the updater container, which holds the Docker socket and is reachable
only on the application's own network, with a shared token; it pulls the
images and recreates the backend and web containers, which then migrate as
they always do on start.
"""

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx2

from app.core.config import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
REGISTRY = "https://ghcr.io"
IMAGES = ("anvero-backend", "anvero-web")
# how far back the newest published commit is looked for
COMMITS_LOOKED_AT = 20
# the list of changes shown is cut here
CHANGES_SHOWN = 30
TIMEOUT_SECONDS = 10
UPDATER_TIMEOUT_SECONDS = 5


class UpdateError(Exception):
    """GitHub, the registry or the updater could not be asked, or refused."""


@dataclass
class Change:
    sha: str
    title: str
    date: str | None


@dataclass
class UpdateState:
    current: str | None = None
    latest: str | None = None
    # how many commits the latest is ahead of the current; null when unknown
    behind: int | None = None
    changes: list[Change] = field(default_factory=list)
    checked_at: datetime | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.current and self.latest and self.latest != self.current)


def short(sha: str | None) -> str | None:
    return sha[:7] if sha else None


class UpdateChecker:
    def __init__(self, http: httpx2.Client | None = None):
        self._http = http or httpx2.Client(timeout=TIMEOUT_SECONDS)

    def _get_json(self, url: str, **params):
        try:
            response = self._http.get(
                url, params=params or None, headers={"Accept": "application/vnd.github+json"}
            )
        except httpx2.HTTPError as exc:
            raise UpdateError(f"GitHub could not be reached: {exc}") from exc
        if response.status_code != 200:
            raise UpdateError(f"GitHub answered {response.status_code}")
        return response.json()

    def _image_exists(self, image: str, tag: str) -> bool:
        owner = settings.update_repository.split("/")[0].lower()
        name = f"{owner}/{image}"
        try:
            token = self._http.get(
                f"{REGISTRY}/token", params={"scope": f"repository:{name}:pull"}
            ).json()["token"]
            response = self._http.head(
                f"{REGISTRY}/v2/{name}/manifests/{tag}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": ", ".join(
                        (
                            "application/vnd.oci.image.index.v1+json",
                            "application/vnd.docker.distribution.manifest.list.v2+json",
                            "application/vnd.oci.image.manifest.v1+json",
                            "application/vnd.docker.distribution.manifest.v2+json",
                        )
                    ),
                },
            )
        except (httpx2.HTTPError, KeyError, ValueError) as exc:
            raise UpdateError(f"The image registry could not be reached: {exc}") from exc
        return response.status_code == 200

    def _published(self, sha: str) -> bool:
        tag = short(sha)
        return all(self._image_exists(image, tag) for image in IMAGES)

    def check(self, current: str | None, now: datetime | None = None) -> UpdateState:
        """The newest published version, and what changed since `current`.
        Raises UpdateError when it cannot be told."""
        repo = settings.update_repository
        commits = self._get_json(
            f"{GITHUB_API}/repos/{repo}/commits", sha="main", per_page=COMMITS_LOOKED_AT
        )
        latest = None
        for commit in commits:
            sha = commit["sha"]
            if current and sha == current:
                # nothing newer is published than what runs
                latest = sha
                break
            if self._published(sha):
                latest = sha
                break
        state = UpdateState(current=current, latest=latest, checked_at=now or datetime.now(UTC))
        if not state.available:
            state.behind = 0 if current and latest == current else None
            return state
        compared = self._get_json(f"{GITHUB_API}/repos/{repo}/compare/{current}...{latest}")
        state.behind = compared.get("ahead_by")
        # oldest first from GitHub; newest first here
        state.changes = [
            Change(
                sha=short(c["sha"]),
                title=c["commit"]["message"].splitlines()[0],
                date=c["commit"].get("committer", {}).get("date"),
            )
            for c in reversed(compared.get("commits", []))
        ][:CHANGES_SHOWN]
        return state


# what the last check found, shared by the loop and the endpoint
_state = UpdateState(current=settings.app_commit or None)
_lock = threading.Lock()


def current_state() -> UpdateState:
    with _lock:
        return _state


def check_now(checker: UpdateChecker | None = None) -> UpdateState:
    """Ask again and keep the answer; a failure is kept as the state's error,
    with what was known before."""
    global _state
    current = settings.app_commit or None
    try:
        state = (checker or UpdateChecker()).check(current)
    except UpdateError as exc:
        logger.warning("Checking for an update failed: %s", exc)
        with _lock:
            _state.current = current
            _state.error = str(exc)
            _state.checked_at = datetime.now(UTC)
            return _state
    with _lock:
        _state = state
        return _state


async def run_update_checks(
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Check for an update now and every `update_check_minutes`, until cancelled."""
    while True:
        await asyncio.to_thread(check_now)
        await sleep(settings.update_check_minutes * 60)


# --- the updater ---------------------------------------------------------------------------


def updater_configured() -> bool:
    return bool(settings.updater_token.strip())


def _updater(method: str, path: str, http: httpx2.Client | None = None):
    client = http or httpx2.Client(timeout=UPDATER_TIMEOUT_SECONDS)
    try:
        response = client.request(
            method,
            f"{settings.updater_url.rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {settings.updater_token.strip()}"},
        )
    except httpx2.HTTPError as exc:
        raise UpdateError(f"The updater could not be reached: {exc}") from exc
    return response


def updater_status(http: httpx2.Client | None = None) -> dict | None:
    """What the updater says about its last run; null when it is not set up
    or does not answer."""
    if not updater_configured():
        return None
    try:
        response = _updater("GET", "/status", http)
    except UpdateError:
        return None
    return response.json() if response.status_code == 200 else None


def start_update(http: httpx2.Client | None = None) -> None:
    """Ask the updater to pull the new images and recreate the containers."""
    if not updater_configured():
        raise UpdateError("The updater is not set up (UPDATER_TOKEN)")
    response = _updater("POST", "/update", http)
    if response.status_code == 409:
        raise UpdateError("An update is already running")
    if response.status_code == 401:
        raise UpdateError("The updater refused the token")
    if response.status_code != 202:
        raise UpdateError(f"The updater answered {response.status_code}")
