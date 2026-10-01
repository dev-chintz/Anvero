"""The copies of the offers' pictures kept on this server (docs/CATALOG.md, "Pictures").

A picture is downloaded once from the address Allegro gave and stored under its own hash:
`<root>/<first two characters>/<sha256>.<jpg|png|webp|gif>`. The same picture used by two offers is
one file, a changed picture is a new file, and a file name says nothing a stranger could guess
from, so the folder can be served without a login (the browser's `<img>` sends none).
"""

import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx2

from app.core.config import settings

logger = logging.getLogger(__name__)

# where pictures may come from: Allegro's and Erli's own servers, and nowhere else, since the
# address comes out of an API answer and this server fetches it
ALLOWED_HOST_SUFFIXES = ("allegroimg.com", "allegro.pl", "allegrosandbox.pl", "erli.pl")
# a picture larger than this is refused rather than held in memory
MAX_BYTES = 15 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30.0

FILE_NAME = re.compile(r"^[0-9a-f]{64}\.(jpg|png|webp|gif)$")
MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}


class ImageRejected(Exception):
    """A picture that was not stored, and why, in words short enough for a table cell."""


@dataclass(frozen=True)
class StoredImage:
    file_name: str
    content_type: str
    byte_size: int


def _sniff(head: bytes) -> str | None:
    """The kind of picture the first bytes say it is; a page of HTML served as one is none."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def allowed_address(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES)


class ImageStore:
    def __init__(self, root: Path | None = None, http: httpx2.Client | None = None):
        self.root = root if root is not None else settings.catalog_images_path
        # redirects are not followed: the address was checked, where it would lead is not
        self._http = http or httpx2.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)

    def path_for(self, file_name: str) -> Path | None:
        """Where a stored picture is, or None for a name that is not one of ours."""
        if not FILE_NAME.match(file_name):
            return None
        return self.root / file_name[:2] / file_name

    def has(self, file_name: str | None) -> bool:
        path = self.path_for(file_name) if file_name else None
        return path is not None and path.is_file()

    def download(self, url: str) -> StoredImage:
        """Fetch a picture and keep it. Raises ImageRejected with the reason when it cannot be."""
        if not allowed_address(url):
            raise ImageRejected("address not allowed")
        try:
            with self._http.stream("GET", url, headers={"Accept": "image/*", "User-Agent": "Anvero"}) as response:
                if response.status_code != 200:
                    raise ImageRejected(f"HTTP {response.status_code}")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ImageRejected("too large")
        except httpx2.HTTPError as exc:
            raise ImageRejected(f"unreachable: {type(exc).__name__}") from exc

        kind = _sniff(bytes(data[:16]))
        if kind is None:
            raise ImageRejected("not a picture")
        file_name = f"{hashlib.sha256(data).hexdigest()}.{kind}"
        path = self.root / file_name[:2] / file_name
        if not path.is_file():
            self._write(path, bytes(data))
        return StoredImage(file_name=file_name, content_type=MEDIA_TYPES[kind], byte_size=len(data))

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        """Whole or not at all: a half-written file would be served as a broken picture."""
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".part")
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
