"""InPost's ShipX API: the requests the client makes and how it reads the answers.
Nothing here reaches the network."""

import json

import httpx2
import pytest

from app.integrations.base import (
    IntegrationAuthError,
    IntegrationNotConfigured,
    IntegrationUnavailable,
)
from app.integrations.inpost.client import PRODUCTION_URL, SANDBOX_URL, InpostClient


def _client(handler, environment="sandbox", token="secret-token", organization="777"):
    return InpostClient(
        token=token,
        organization_id=organization,
        environment=environment,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


def _json(body, status=200):
    return httpx2.Response(status, json=body)


def test_it_speaks_to_the_sandbox_or_to_production_as_told():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return _json({"id": 777})

    _client(handler, "sandbox").get_organization()
    _client(handler, "production").get_organization()

    assert seen == [
        f"{SANDBOX_URL}/v1/organizations/777",
        f"{PRODUCTION_URL}/v1/organizations/777",
    ]


def test_it_refuses_an_environment_it_does_not_know():
    with pytest.raises(ValueError, match="environment"):
        InpostClient(token="t", organization_id="1", environment="staging")


def test_every_request_carries_the_token_as_a_bearer_token():
    seen = []

    def handler(request):
        seen.append(request.headers["authorization"])
        return _json({})

    _client(handler, token="abc-123").get_organization()

    assert seen == ["Bearer abc-123"]


def test_it_is_configured_only_with_both_a_token_and_an_organization():
    assert InpostClient(token="t", organization_id="1").is_configured
    assert not InpostClient(token="", organization_id="1").is_configured
    assert not InpostClient(token="t", organization_id="").is_configured


def test_without_settings_nothing_is_sent():
    def handler(request):
        raise AssertionError("no request should be made")

    with pytest.raises(IntegrationNotConfigured):
        _client(handler, token="", organization="").get_organization()


def test_making_a_shipment_posts_the_body_to_the_organization():
    seen = {}

    def handler(request):
        seen["method"], seen["path"] = request.method, request.url.path
        seen["body"] = json.loads(request.content)
        return _json({"id": 4242, "status": "created", "tracking_number": None})

    payload = {"service": "inpost_locker_standard", "parcels": {"template": "small"}}
    answer = _client(handler).create_shipment(payload)

    assert (seen["method"], seen["path"]) == ("POST", "/v1/organizations/777/shipments")
    assert seen["body"] == payload
    assert answer["id"] == 4242


def test_a_shipment_is_read_by_its_own_address():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        return _json({"id": 4242, "status": "confirmed", "tracking_number": "620000000000000000000001"})

    answer = _client(handler).get_shipment("4242")

    assert seen == [("GET", "/v1/shipments/4242")]
    assert answer["tracking_number"] == "620000000000000000000001"


def test_a_shipment_is_cancelled_with_delete():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        return httpx2.Response(204)

    _client(handler).cancel_shipment("4242")

    assert seen == [("DELETE", "/v1/shipments/4242")]


def test_one_label_is_fetched_from_the_shipments_own_address_as_an_a6_pdf():
    seen = {}

    def handler(request):
        seen["method"], seen["path"] = request.method, request.url.path
        seen["params"] = dict(request.url.params)
        seen["accept"] = request.headers["accept"]
        return httpx2.Response(200, content=b"%PDF-1.4 one")

    pdf = _client(handler).fetch_labels(["4242"])

    assert (seen["method"], seen["path"]) == ("GET", "/v1/shipments/4242/label")
    assert seen["params"] == {"format": "pdf", "type": "A6"}
    assert seen["accept"] == "application/pdf"
    assert pdf == b"%PDF-1.4 one"


def test_several_labels_are_fetched_together_through_the_organizations_batch_address():
    seen = {}

    def handler(request):
        seen["method"], seen["path"] = request.method, request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, content=b"%PDF-1.4 many")

    pdf = _client(handler).fetch_labels(["41938", "41937"])

    assert (seen["method"], seen["path"]) == ("POST", "/v1/organizations/777/shipments/labels")
    # the ids as numbers, in the order given, and the size a label printer takes
    assert seen["body"] == {"shipment_ids": [41938, 41937], "format": "pdf", "type": "A6"}
    assert pdf == b"%PDF-1.4 many"


def test_labels_need_at_least_one_shipment():
    with pytest.raises(ValueError):
        _client(lambda request: _json({})).fetch_labels([])


def test_something_that_is_not_a_pdf_is_not_taken_for_a_label():
    with pytest.raises(IntegrationUnavailable, match="PDF"):
        _client(lambda request: httpx2.Response(200, content=b"<html>error</html>")).fetch_labels(["1"])


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_token_is_an_authorisation_error(status):
    with pytest.raises(IntegrationAuthError, match="refused the token"):
        _client(lambda request: _json({"message": "no"}, status)).get_organization()


def test_a_refusal_carries_inposts_own_words_and_the_fields_it_names():
    body = {
        "status": 400,
        "error": "validation_failed",
        "message": "Validation failed",
        "details": {"receiver": {"phone": ["invalid"]}},
    }

    with pytest.raises(IntegrationUnavailable) as caught:
        _client(lambda request: _json(body, 400)).create_shipment({})

    text = str(caught.value)
    assert "400 for the shipment" in text
    assert "Validation failed" in text
    assert "receiver" in text and "phone" in text


def test_a_refusal_without_a_readable_body_is_still_reported():
    with pytest.raises(IntegrationUnavailable) as caught:
        _client(lambda request: httpx2.Response(500, text="oops")).get_shipment("1")

    assert str(caught.value) == "InPost returned 500 for the shipment"


def test_too_many_requests_is_a_pause_not_a_failure_of_the_token():
    with pytest.raises(IntegrationUnavailable, match="slow down"):
        _client(lambda request: httpx2.Response(429)).get_shipment("1")


def test_an_unreachable_inpost_is_reported():
    def handler(request):
        raise httpx2.ConnectError("boom")

    with pytest.raises(IntegrationUnavailable, match="unreachable"):
        _client(handler).get_shipment("1")


def test_an_answer_that_is_not_json_is_reported():
    with pytest.raises(IntegrationUnavailable, match="JSON"):
        _client(lambda request: httpx2.Response(200, text="not json")).get_shipment("1")
