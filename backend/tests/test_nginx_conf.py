"""frontend/nginx.conf keeps a search term out of the web container's access log (docs/GDPR.md).

nginx is not started here. What is checked is the file's text, and the one regular expression that
does the work, run as Python's `re` (for this pattern PCRE, which nginx uses, reads it the same).
A mistake that only nginx would catch (a directive in the wrong place) is not caught: see
`docs/DEPLOYMENT.md` for how the file was tried.
"""

import re
from pathlib import Path

import pytest

CONF = (Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf").read_text(encoding="utf-8")

# what nginx can write a query in, or the address of a page that may carry one
LEAKY = re.compile(r"\$(request|request_uri|args|query_string|is_args|http_referer)(?![A-Za-z0-9_])")


def _log_format() -> tuple[str, str]:
    found = re.search(r"log_format\s+(\w+)\s+((?:'[^']*'\s*)+);", CONF)
    assert found, "nginx.conf defines no log_format of its own, so nginx's default (the whole request) is used"
    return found.group(1), found.group(2)


def _map_rules() -> tuple[re.Pattern, str]:
    block = re.search(r"map\s+\$request_uri\s+\$logged_uri\s*\{(.*?)\n\}", CONF, re.S)
    assert block, "nginx.conf does not map $request_uri to $logged_uri"
    rule = re.search(r'~(\S+)\s+"([^"]*)"\s*;', block.group(1))
    assert rule, "the map has no regular expression"
    assert re.search(r"default\s+\$request_uri\s*;", block.group(1)), "an address with no query is logged as it is"
    # nginx's (?<name>...) is Python's (?P<name>...)
    return re.compile(re.sub(r"\(\?<(\w+)>", r"(?P<\1>", rule.group(1))), rule.group(2)


def _logged(uri: str) -> str:
    pattern, template = _map_rules()
    found = pattern.match(uri)
    if not found:
        return uri
    return re.sub(r"\$(\w+)", lambda name: found.group(name.group(1)), template)


def test_every_access_log_uses_the_format_that_drops_the_query():
    name, _ = _log_format()
    directives = re.findall(r"^\s*access_log\s+([^;]+);", CONF, re.M)

    assert directives, "nginx.conf sets no access_log, so the image's default format is used"
    for directive in directives:
        assert directive.split()[1:] == [name], f"access_log {directive!r} does not use the format {name!r}"


def test_the_format_writes_the_address_without_its_query_and_without_the_referer():
    _, body = _log_format()

    assert "$logged_uri" in body
    assert not LEAKY.search(body), f"the log format writes {LEAKY.search(body).group(0)}"


@pytest.mark.parametrize(
    "uri, logged",
    [
        ("/api/v1/orders?search=Kowalski&limit=50", "/api/v1/orders?..."),
        ("/api/v1/production?status=NEW&search=jan.nowak%40example.com", "/api/v1/production?..."),
        ("/api/v1/orders?", "/api/v1/orders?..."),
        ("/?search=a?b", "/?..."),
        ("/api/v1/orders/12", "/api/v1/orders/12"),
        ("/assets/index-3f9a.js", "/assets/index-3f9a.js"),
    ],
)
def test_the_query_is_dropped_and_marked_and_an_address_without_one_is_left_alone(uri, logged):
    assert _logged(uri) == logged


def test_the_forwarded_address_is_still_the_clients_own():
    # the backend's login rate limit and its security log read the client from this header, so it
    # must replace whatever the client sent, not add to it (see the comment in nginx.conf)
    assert re.search(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr\s*;", CONF)
