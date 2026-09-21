"""The Sandbox ordering script: reading the CSV, finding the offers, and the
client call behind it. The buying itself drives a browser and is not tested."""

import importlib.util
from pathlib import Path

import httpx2
import pytest

from app.integrations.allegro.client import AllegroClient

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "sandbox_order_from_csv.py"
spec = importlib.util.spec_from_file_location("sandbox_order_from_csv", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def _csv(tmp_path, rows, header="GTIN,EXTERNAL_ID,NAME"):
    path = tmp_path / "offers.csv"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def test_reads_the_external_ids_and_names_in_file_order(tmp_path):
    path = _csv(tmp_path, ["1,AGD-1,Blender", '2,AGD-2,"Monitor 27"" IPS"'])

    listings = script.read_listings(path)

    assert [(item.external_id, item.name) for item in listings] == [
        ("AGD-1", "Blender"),
        ("AGD-2", 'Monitor 27" IPS'),
    ]


def test_skips_blank_and_repeated_ids(tmp_path):
    path = _csv(tmp_path, ["1,AGD-1,A", "2,,B", "3,AGD-1,C"])

    assert [item.external_id for item in script.read_listings(path)] == ["AGD-1"]


def test_a_file_without_an_external_id_column_is_refused(tmp_path):
    path = _csv(tmp_path, ["1,A"], header="GTIN,NAME")

    with pytest.raises(ValueError):
        script.read_listings(path)


def test_the_offers_file_takes_urls_and_ids_and_only_sandbox_ones(tmp_path):
    path = tmp_path / "offers.txt"
    path.write_text(f"# comment\n123456\n{script.SANDBOX_URL}/oferta/789\n\n")

    offers = script.read_offers_file(path)

    assert [o.url for o in offers] == [
        f"{script.SANDBOX_URL}/oferta/123456",
        f"{script.SANDBOX_URL}/oferta/789",
    ]

    path.write_text("https://allegro.pl/oferta/1\n")
    with pytest.raises(ValueError):
        script.read_offers_file(path)


class FakeClient:
    def __init__(self, offers):
        self.offers = offers
        self.asked = []

    def fetch_offers_by_external_id(self, ids):
        self.asked.append(list(ids))
        return [o for o in self.offers if o["external"]["id"] in ids]


def _listings(*ids):
    return [script.Listing(i, f"name {i}") for i in ids]


def test_finds_offers_and_reports_the_listings_without_one():
    client = FakeClient(
        [
            {"id": "111", "name": "A", "external": {"id": "AGD-1"}},
            {"id": "333", "name": "C", "external": {"id": "AGD-3"}},
        ]
    )

    offers, missing = script.find_offers(client, _listings("AGD-1", "AGD-2", "AGD-3"))

    assert [(o.external_id, o.url) for o in offers] == [
        ("AGD-1", f"{script.SANDBOX_URL}/oferta/111"),
        ("AGD-3", f"{script.SANDBOX_URL}/oferta/333"),
    ]
    assert [m.external_id for m in missing] == ["AGD-2"]


def test_the_first_offer_wins_when_an_external_id_repeats():
    client = FakeClient(
        [
            {"id": "1", "name": "A", "external": {"id": "X"}},
            {"id": "2", "name": "A again", "external": {"id": "X"}},
        ]
    )

    offers, _ = script.find_offers(client, _listings("X"))

    assert [o.url.rsplit("/", 1)[1] for o in offers] == ["1"]


def test_asks_in_batches():
    client = FakeClient([])

    script.find_offers(client, _listings(*[f"ID{i}" for i in range(45)]))

    assert [len(batch) for batch in client.asked] == [20, 20, 5]


def test_the_client_asks_for_active_offers_by_external_id():
    seen = []

    def handler(request):
        if request.url.path == "/token":
            return httpx2.Response(200, json={"access_token": "a", "expires_in": 3600})
        seen.append(request)
        return httpx2.Response(200, json={"offers": [{"id": "1"}]})

    client = AllegroClient(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        api_url="https://api.test",
        auth_url="https://auth.test",
        user_agent="anvero-test",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )

    result = client.fetch_offers_by_external_id(["A", "B"])

    assert result == [{"id": "1"}]
    assert seen[0].url.path == "/sale/offers"
    assert seen[0].url.params.get_list("external.id") == ["A", "B"]
    assert seen[0].url.params["publication.status"] == "ACTIVE"
    assert client.fetch_offers_by_external_id([]) == []
