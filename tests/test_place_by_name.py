"""Tests for C6 – F23 find a place by name: the Google call and the form rules
(specs/c6-find-place-by-name.md).

These tests never call Google: `requests.post` is always replaced by a fake.
The new functions are looked up on the module inside each test (places.search_by_name),
so every test fails on its own until they exist.
"""

import pytest
import requests

from app.services import places
from app.services.places import PlacesError

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress"
FAKE_KEY = "fake-key-for-tests-0123456789"
FALLBACK_NAME = "Place from Google Maps"


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    """Looks like a requests.Response with a status code and a JSON body."""

    def __init__(self, status_code=200, body=None, invalid_json=False):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.invalid_json = invalid_json
        self.text = "not json" if invalid_json else str(self.body)

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid JSON")
        return self.body


class FakeGoogle:
    """Replaces requests.post: records every call and returns a prepared response."""

    def __init__(self):
        self.response = FakeResponse(body={"places": []})
        self.error = None
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response


def match(place_id, name=None, address=None):
    """One result as Google sends it (only the fields of our field mask)."""
    result = {"id": place_id}
    if name is not None:
        result["displayName"] = {"text": name, "languageCode": "en"}
    if address is not None:
        result["formattedAddress"] = address
    return result


@pytest.fixture
def fake_google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


def search(name="Luigi's", latitude=None, longitude=None):
    return places.search_by_name(
        api_key=FAKE_KEY, name=name, latitude=latitude, longitude=longitude
    )


# --- The request -----------------------------------------------------------

def test_sends_one_post_to_text_search_with_timeout(fake_google):
    search()
    assert len(fake_google.calls) == 1
    assert fake_google.calls[0]["url"] == TEXT_SEARCH_URL
    assert fake_google.calls[0]["timeout"] == 5


def test_sends_key_content_type_and_exact_field_mask(fake_google):
    search()
    headers = fake_google.calls[0]["headers"]
    assert headers["X-Goog-Api-Key"] == FAKE_KEY
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Goog-FieldMask"] == FIELD_MASK
    assert "*" not in headers["X-Goog-FieldMask"]
    assert places.NAME_SEARCH_FIELD_MASK == FIELD_MASK


def test_sends_text_query_and_page_size_five_only(fake_google):
    search(name="Luigi's")
    body = fake_google.calls[0]["json"]
    assert body["textQuery"] == "Luigi's"
    assert body["pageSize"] == 5
    assert "maxResultCount" not in body
    assert "locationRestriction" not in body


def test_sends_location_bias_circle_with_radius_5000(fake_google):
    search(latitude=38.737, longitude=-9.153)
    body = fake_google.calls[0]["json"]
    assert body["locationBias"] == {
        "circle": {"center": {"latitude": 38.737, "longitude": -9.153}, "radius": 5000}
    }
    assert set(body) == {"textQuery", "pageSize", "locationBias"}


@pytest.mark.parametrize("latitude, longitude", [(None, None), (38.737, None), (None, -9.153)])
def test_sends_no_location_bias_without_full_location(fake_google, latitude, longitude):
    search(latitude=latitude, longitude=longitude)
    body = fake_google.calls[0]["json"]
    assert "locationBias" not in body
    assert set(body) == {"textQuery", "pageSize"}


# --- The answer ------------------------------------------------------------

def test_returns_id_name_and_address_in_googles_order(fake_google):
    fake_google.response = FakeResponse(
        body={
            "places": [
                match("place-b", "Luigi's Pizzeria", "Rua A 1, Lisboa"),
                match("place-a", "Luigi's Bar", "Rua B 2, Lisboa"),
            ]
        }
    )
    assert search() == [
        {"place_id": "place-b", "name": "Luigi's Pizzeria", "address": "Rua A 1, Lisboa"},
        {"place_id": "place-a", "name": "Luigi's Bar", "address": "Rua B 2, Lisboa"},
    ]


def test_returns_at_most_five_matches(fake_google):
    fake_google.response = FakeResponse(
        body={"places": [match(f"place-{number}", f"Name {number}", "Street") for number in range(8)]}
    )
    result = search()
    assert [found["place_id"] for found in result] == [f"place-{number}" for number in range(5)]


def test_response_without_places_returns_empty_list(fake_google):
    fake_google.response = FakeResponse(body={})
    assert search() == []


def test_skips_bad_and_duplicate_results(fake_google):
    fake_google.response = FakeResponse(
        body={
            "places": [
                {"displayName": {"text": "No id"}},
                match("", "Empty id", "Street"),
                match("../evil", "Bad id", "Street"),
                "not a dict",
                match("place-1", "First", "Street 1"),
                match("place-1", "Again", "Street 2"),
                match("place-2", "Second", "Street 3"),
            ]
        }
    )
    assert [found["place_id"] for found in search()] == ["place-1", "place-2"]


def test_missing_name_and_address_get_fallbacks(fake_google):
    fake_google.response = FakeResponse(
        body={"places": [match("place-1"), {"id": "place-2", "displayName": {"text": ""}, "formattedAddress": 7}]}
    )
    assert search() == [
        {"place_id": "place-1", "name": FALLBACK_NAME, "address": ""},
        {"place_id": "place-2", "name": FALLBACK_NAME, "address": ""},
    ]


# --- Errors ----------------------------------------------------------------

@pytest.mark.parametrize(
    "error", [requests.Timeout("slow"), requests.ConnectionError("no network " + FAKE_KEY)]
)
def test_timeout_and_connection_error_raise_places_error(fake_google, error):
    fake_google.error = error
    with pytest.raises(PlacesError) as raised:
        search()
    assert FAKE_KEY not in str(raised.value)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(status_code=403, body={"error": {"message": "bad key"}}),
        FakeResponse(status_code=500),
        FakeResponse(invalid_json=True),
        FakeResponse(body=["not", "an", "object"]),
    ],
)
def test_bad_answers_raise_places_error_without_key(fake_google, response):
    fake_google.response = response
    with pytest.raises(PlacesError) as raised:
        search()
    assert FAKE_KEY not in str(raised.value)


# --- Form rules ------------------------------------------------------------

def test_validate_name_accepts_and_strips():
    assert places.validate_name("  Luigi's  ") == ("Luigi's", [])


def test_validate_name_accepts_exactly_80_characters():
    name = "x" * 80
    assert places.validate_name(name) == (name, [])


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_validate_name_rejects_empty(value):
    name, errors = places.validate_name(value)
    assert name == ""
    assert errors == ["Please enter a name to search for."]


def test_validate_name_rejects_more_than_80_characters():
    _, errors = places.validate_name("x" * 81)
    assert errors == ["A name can be at most 80 characters."]
