"""The copies of the offers' pictures: what is fetched, what is refused, and where it is kept."""

import hashlib

import httpx2
import pytest

from app.services.catalog_images import (
    FILE_NAME,
    MAX_BYTES,
    ImageRejected,
    ImageStore,
    allowed_address,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"body-of-a-picture" * 4
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body" * 4
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"x" * 20
URL = "https://a.allegroimg.com/original/abc"


def _store(tmp_path, handler):
    return ImageStore(tmp_path, httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_a_picture_is_kept_under_its_hash(tmp_path):
    stored = _store(tmp_path, lambda request: httpx2.Response(200, content=PNG)).download(URL)

    digest = hashlib.sha256(PNG).hexdigest()
    assert stored.file_name == f"{digest}.png"
    assert (stored.content_type, stored.byte_size) == ("image/png", len(PNG))
    assert (tmp_path / digest[:2] / f"{digest}.png").read_bytes() == PNG


def test_the_kind_is_what_the_bytes_say_not_what_the_server_says(tmp_path):
    store = _store(tmp_path, lambda request: httpx2.Response(200, content=WEBP, headers={"Content-Type": "image/jpeg"}))

    assert store.download(URL).file_name.endswith(".webp")


def test_the_same_picture_is_one_file(tmp_path):
    store = _store(tmp_path, lambda request: httpx2.Response(200, content=JPEG))

    first, second = store.download(URL), store.download(URL + "-copy")

    assert first.file_name == second.file_name
    assert len(list(tmp_path.rglob("*.jpg"))) == 1


def test_nothing_half_written_is_left(tmp_path):
    _store(tmp_path, lambda request: httpx2.Response(200, content=PNG)).download(URL)

    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize(
    "url",
    [
        "http://a.allegroimg.com/x.png",
        "https://evil.example/x.png",
        "https://allegroimg.com.evil.example/x.png",
        "https://notallegroimg.com/x.png",
        "file:///etc/passwd",
        "",
    ],
)
def test_an_address_outside_the_marketplaces_is_refused_without_a_request(tmp_path, url):
    def handler(request):
        raise AssertionError("no request may be made")

    with pytest.raises(ImageRejected, match="address"):
        _store(tmp_path, handler).download(url)


def test_the_marketplaces_own_hosts_are_allowed():
    for url in ("https://a.allegroimg.com/x", "https://allegro.pl/x", "https://i.erli.pl/a.webp", "https://x.allegrosandbox.pl/y"):
        assert allowed_address(url)


def test_a_page_of_html_served_as_a_picture_is_refused(tmp_path):
    store = _store(tmp_path, lambda request: httpx2.Response(200, content=b"<html>nope</html>", headers={"Content-Type": "image/png"}))

    with pytest.raises(ImageRejected, match="not a picture"):
        store.download(URL)
    assert not list(tmp_path.rglob("*.*"))


def test_an_error_status_is_refused_with_it(tmp_path):
    with pytest.raises(ImageRejected, match="404"):
        _store(tmp_path, lambda request: httpx2.Response(404)).download(URL)


def test_a_redirect_is_not_followed(tmp_path):
    def handler(request):
        return httpx2.Response(302, headers={"Location": "https://evil.example/x.png"})

    with pytest.raises(ImageRejected, match="302"):
        _store(tmp_path, handler).download(URL)


def test_a_picture_too_large_is_refused(tmp_path):
    big = PNG + b"0" * (MAX_BYTES + 1)

    with pytest.raises(ImageRejected, match="too large"):
        _store(tmp_path, lambda request: httpx2.Response(200, content=big)).download(URL)


def test_an_unreachable_server_is_refused(tmp_path):
    def handler(request):
        raise httpx2.ConnectError("down")

    with pytest.raises(ImageRejected, match="unreachable"):
        _store(tmp_path, handler).download(URL)


def test_only_our_own_file_names_are_looked_up(tmp_path):
    store = ImageStore(tmp_path)
    good = "a" * 64 + ".png"

    assert store.path_for(good) == tmp_path / "aa" / good
    for bad in ("../" + good, "a" * 64, "a" * 63 + ".png", good + ".exe", "A" * 64 + ".png", "..", ""):
        assert store.path_for(bad) is None
    assert FILE_NAME.match(good)


def test_has_says_whether_the_file_is_there(tmp_path):
    store = _store(tmp_path, lambda request: httpx2.Response(200, content=PNG))
    stored = store.download(URL)

    assert store.has(stored.file_name)
    assert not store.has("b" * 64 + ".png")
    assert not store.has(None)
