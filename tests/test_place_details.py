"""Tests for C2b – Place Details, photos and card rules (specs/c2b-place-cards.md).

These tests never call Google: `requests.get` is replaced by a fake, and the
root conftest.py makes any other real request fail.
"""

import pytest
import requests

from app.services import places
from app.services.places import (
    PlacesError,
    PlacesUnavailable,
    build_card,
    distance_m,
    fetch_photo,
    format_distance,
    format_price_level,
    format_rating,
    get_place_details,
    load_cards,
)

FAKE_KEY = "fake-key-for-tests-0123456789"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
FIELD_MASK = "displayName,rating,priceLevel,location,photos"
PHOTO_NAME = "places/place-a/photos/photo-ref-1"
FALLBACK_NAME = "Place from Google Maps"

DETAIL_KEYS = {
    "name",
    "rating",
    "price_level",
    "latitude",
    "longitude",
    "photo_name",
    "photo_author",
    "photo_author_uri",
}


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None, invalid_json=False, content=b"", content_type=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.invalid_json = invalid_json
        self.content = content
        self.headers = {"Content-Type": content_type or "application/json"}
        self.text = "not json" if invalid_json else str(self.body)

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid JSON")
        return self.body


class FakeGet:
    """Replaces requests.get: answers by URL, records every call."""

    def __init__(self):
        self.responses = {}
        self.default = FakeResponse(status_code=404, body={"error": {}})
        self.error = None
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        response = self.responses.get(url, self.default)
        if isinstance(response, Exception):
            raise response
        return response

    def details_calls(self):
        return [call for call in self.calls if not call["url"].endswith("/media")]


@pytest.fixture
def fake_get(monkeypatch):
    fake = FakeGet()
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


def full_place(place_id="place-a", name="Pizza Roma"):
    """A Place Details answer with every field of the field mask."""
    return {
        "displayName": {"text": name, "languageCode": "en"},
        "rating": 4.5,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "location": {"latitude": 38.740, "longitude": -9.153},
        "photos": [
            {
                "name": f"places/{place_id}/photos/photo-ref-1",
                "authorAttributions": [
                    {"displayName": "Maria Silva", "uri": "https://maps.google.com/maria"}
                ],
            },
            {"name": f"places/{place_id}/photos/photo-ref-2", "authorAttributions": []},
        ],
    }


def answer(fake_get, place_id, body):
    fake_get.responses[DETAILS_URL + place_id] = FakeResponse(body=body)


# --- get_place_details: the request ----------------------------------------

def test_details_request_url_timeout_key_and_field_mask(fake_get):
    answer(fake_get, "place-a", full_place())
    get_place_details(FAKE_KEY, "place-a")
    assert len(fake_get.calls) == 1
    call = fake_get.calls[0]
    assert call["url"] == DETAILS_URL + "place-a"
    assert call["timeout"] == 5
    assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert call["headers"]["X-Goog-FieldMask"] == FIELD_MASK
    assert places.DETAILS_FIELD_MASK == FIELD_MASK
    assert "*" not in call["headers"]["X-Goog-FieldMask"]


# --- get_place_details: the answer -----------------------------------------

def test_details_returns_all_fields(fake_get):
    answer(fake_get, "place-a", full_place())
    assert get_place_details(FAKE_KEY, "place-a") == {
        "name": "Pizza Roma",
        "rating": 4.5,
        "price_level": 2,
        "latitude": 38.740,
        "longitude": -9.153,
        "photo_name": PHOTO_NAME,
        "photo_author": "Maria Silva",
        "photo_author_uri": "https://maps.google.com/maria",
    }


def test_details_missing_fields_are_none(fake_get):
    answer(fake_get, "place-a", {})
    details = get_place_details(FAKE_KEY, "place-a")
    assert set(details) == DETAIL_KEYS
    assert all(value is None for value in details.values())


@pytest.mark.parametrize("price_text", ["PRICE_LEVEL_UNSPECIFIED", "CHEAP", 3])
def test_details_unknown_price_level_is_none(fake_get, price_text):
    body = full_place()
    body["priceLevel"] = price_text
    answer(fake_get, "place-a", body)
    assert get_place_details(FAKE_KEY, "place-a")["price_level"] is None


@pytest.mark.parametrize(
    "photo_name",
    [
        "places/other-place/photos/photo-ref-1",
        "places/place-a/photos/ref with spaces",
        "places/place-a/photos/../../x",
        "places/place-a/photos/",
        "https://evil.example/photo.jpg",
    ],
)
def test_details_suspicious_photo_name_is_none(fake_get, photo_name):
    body = full_place()
    body["photos"][0]["name"] = photo_name
    answer(fake_get, "place-a", body)
    assert get_place_details(FAKE_KEY, "place-a")["photo_name"] is None


@pytest.mark.parametrize(
    "uri", ["javascript:alert(1)", "http://maps.google.com/maria", "", None]
)
def test_details_author_uri_must_be_https(fake_get, uri):
    body = full_place()
    body["photos"][0]["authorAttributions"][0]["uri"] = uri
    answer(fake_get, "place-a", body)
    details = get_place_details(FAKE_KEY, "place-a")
    assert details["photo_author_uri"] is None
    assert details["photo_author"] == "Maria Silva"


@pytest.mark.parametrize("place_id", ["../x", "a/b", "a?b", "a b", ""])
def test_details_rejects_unsafe_place_id_without_calling_google(fake_get, place_id):
    with pytest.raises(PlacesError):
        get_place_details(FAKE_KEY, place_id)
    assert fake_get.calls == []


# --- get_place_details: errors ---------------------------------------------

@pytest.mark.parametrize(
    "setup",
    ["timeout", "connection", "status", "invalid-json", "json-list"],
)
def test_details_errors_raise_places_error_without_key(fake_get, setup):
    if setup == "timeout":
        fake_get.error = requests.Timeout(f"timed out key={FAKE_KEY}")
    elif setup == "connection":
        fake_get.error = requests.ConnectionError(f"no network key={FAKE_KEY}")
    elif setup == "status":
        fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(
            status_code=403, body={"error": {"message": FAKE_KEY}}
        )
    elif setup == "invalid-json":
        fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(invalid_json=True)
    else:
        fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(body=[1, 2])
    with pytest.raises(PlacesError) as caught:
        get_place_details(FAKE_KEY, "place-a")
    assert FAKE_KEY not in str(caught.value)


@pytest.mark.parametrize(
    "error", [requests.Timeout("timed out"), requests.ConnectionError("no network")],
    ids=["timeout", "connection"],
)
def test_details_unreachable_raises_places_unavailable(fake_get, error):
    fake_get.error = error
    with pytest.raises(PlacesUnavailable):
        get_place_details(FAKE_KEY, "place-a")
    assert issubclass(PlacesUnavailable, PlacesError)


@pytest.mark.parametrize("setup", ["status", "invalid-json", "json-list"])
def test_details_bad_answer_is_not_places_unavailable(fake_get, setup):
    if setup == "status":
        fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=500, body={})
    elif setup == "invalid-json":
        fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(invalid_json=True)
    else:
        fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(body=[1, 2])
    with pytest.raises(PlacesError) as caught:
        get_place_details(FAKE_KEY, "place-a")
    assert not isinstance(caught.value, PlacesUnavailable)


# --- Formatting ------------------------------------------------------------

def test_distance_m():
    assert distance_m(38.737, -9.153, 38.737, -9.153) == 0
    assert 330 <= distance_m(38.737, -9.153, 38.740, -9.153) <= 336


@pytest.mark.parametrize(
    "metres, text",
    [
        (0, "0 m"),
        (334, "330 m"),
        (995, "1.0 km"),
        (1000, "1.0 km"),
        (1250, "1.2 km"),
        (12345, "12.3 km"),
    ],
)
def test_format_distance(metres, text):
    assert format_distance(metres) == text


@pytest.mark.parametrize("level, text", [(0, "Free"), (1, "€"), (2, "€€"), (4, "€€€€"), (None, "")])
def test_format_price_level(level, text):
    assert format_price_level(level) == text


@pytest.mark.parametrize("rating, text", [(4, "4.0 ★"), (4.56, "4.6 ★"), (None, "")])
def test_format_rating(rating, text):
    assert format_rating(rating) == text


# --- build_card ------------------------------------------------------------

def manual_option(label="Pizza place"):
    return {"id": 1, "source": "manual", "label": label, "place_id": None}


def google_option(place_id="place-a"):
    return {"id": 2, "source": "google", "label": None, "place_id": place_id}


def full_details(**changes):
    details = {
        "name": "Pizza Roma",
        "rating": 4.5,
        "price_level": 2,
        "latitude": 38.740,
        "longitude": -9.153,
        "photo_name": PHOTO_NAME,
        "photo_author": "Maria Silva",
        "photo_author_uri": "https://maps.google.com/maria",
    }
    details.update(changes)
    return details


def test_build_card_manual_option():
    assert build_card(manual_option(), None, 38.737, -9.153) == {
        "source": "manual",
        "label": "Pizza place",
    }


def test_build_card_google_option_with_details():
    assert build_card(google_option(), full_details(), 38.737, -9.153) == {
        "source": "google",
        "name": "Pizza Roma",
        "photo_name": PHOTO_NAME,
        "photo_author": "Maria Silva",
        "photo_author_uri": "https://maps.google.com/maria",
        "rating_text": "4.5 ★",
        "price_text": "€€",
        "distance_text": "330 m",
        "details_missing": False,
    }


def test_build_card_without_centre_or_location_has_no_distance():
    assert build_card(google_option(), full_details(), None, None)["distance_text"] == ""
    no_location = full_details(latitude=None, longitude=None)
    assert build_card(google_option(), no_location, 38.737, -9.153)["distance_text"] == ""


def test_build_card_without_name_uses_fallback_name():
    card = build_card(google_option(), full_details(name=None), 38.737, -9.153)
    assert card["name"] == FALLBACK_NAME
    assert card["details_missing"] is False


def test_build_card_without_details():
    assert build_card(google_option(), None, 38.737, -9.153) == {
        "source": "google",
        "name": FALLBACK_NAME,
        "photo_name": None,
        "photo_author": None,
        "photo_author_uri": None,
        "rating_text": "",
        "price_text": "",
        "distance_text": "",
        "details_missing": True,
    }


# --- load_cards ------------------------------------------------------------

def test_load_cards_keeps_order_and_calls_google_once_per_google_option(fake_get):
    answer(fake_get, "place-a", full_place("place-a", "Pizza Roma"))
    answer(fake_get, "place-b", full_place("place-b", "Sushi Bar"))
    options = [google_option("place-b"), manual_option("Cinema"), google_option("place-a")]
    cards = load_cards(FAKE_KEY, options, 38.737, -9.153)
    assert [card.get("name") or card.get("label") for card in cards] == [
        "Sushi Bar",
        "Cinema",
        "Pizza Roma",
    ]
    assert sorted(call["url"] for call in fake_get.calls) == [
        DETAILS_URL + "place-a",
        DETAILS_URL + "place-b",
    ]


def test_load_cards_error_for_one_place_only_affects_that_card(fake_get):
    answer(fake_get, "place-a", full_place("place-a", "Pizza Roma"))
    fake_get.responses[DETAILS_URL + "place-b"] = FakeResponse(status_code=500, body={})
    cards = load_cards(FAKE_KEY, [google_option("place-a"), google_option("place-b")], 38.737, -9.153)
    assert cards[0]["name"] == "Pizza Roma"
    assert cards[0]["details_missing"] is False
    assert cards[1]["name"] == FALLBACK_NAME
    assert cards[1]["details_missing"] is True


def test_load_cards_error_status_for_first_place_still_loads_the_others(fake_get):
    fake_get.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=404, body={})
    answer(fake_get, "place-b", full_place("place-b", "Sushi Bar"))
    cards = load_cards(FAKE_KEY, [google_option("place-a"), google_option("place-b")], 38.737, -9.153)
    assert len(fake_get.calls) == 2
    assert cards[0]["details_missing"] is True
    assert cards[1]["name"] == "Sushi Bar"


@pytest.mark.parametrize(
    "error", [requests.Timeout("timed out"), requests.ConnectionError("no network")],
    ids=["timeout", "connection"],
)
def test_load_cards_stops_calling_google_after_it_is_unreachable(fake_get, error):
    fake_get.responses[DETAILS_URL + "place-a"] = error
    answer(fake_get, "place-b", full_place("place-b", "Sushi Bar"))
    answer(fake_get, "place-c", full_place("place-c", "Café Lisboa"))
    options = [google_option("place-a"), google_option("place-b"), google_option("place-c")]
    cards = load_cards(FAKE_KEY, options, 38.737, -9.153)
    assert len(fake_get.calls) == 1
    assert [card["details_missing"] for card in cards] == [True, True, True]
    assert all(card["name"] == FALLBACK_NAME for card in cards)


@pytest.mark.parametrize("api_key", ["", None])
def test_load_cards_without_key_does_not_call_google(fake_get, api_key):
    cards = load_cards(api_key, [google_option("place-a"), manual_option()], 38.737, -9.153)
    assert fake_get.calls == []
    assert cards[0]["details_missing"] is True
    assert cards[1] == {"source": "manual", "label": "Pizza place"}


# --- fetch_photo -----------------------------------------------------------

def photo_url(photo_name=PHOTO_NAME):
    return f"https://places.googleapis.com/v1/{photo_name}/media"


def test_fetch_photo_request_and_result(fake_get):
    fake_get.responses[photo_url()] = FakeResponse(content=b"\xff\xd8jpeg-bytes", content_type="image/jpeg")
    assert fetch_photo(FAKE_KEY, PHOTO_NAME) == (b"\xff\xd8jpeg-bytes", "image/jpeg")
    assert len(fake_get.calls) == 1
    call = fake_get.calls[0]
    assert call["url"] == photo_url()
    assert call["params"] == {"maxWidthPx": 400}
    assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert call["timeout"] == 5


@pytest.mark.parametrize(
    "photo_name",
    ["places/a/photos/../../x", "places/a/b", "https://evil.example/x", "places/a/photos/", ""],
)
def test_fetch_photo_rejects_bad_name_without_calling_google(fake_get, photo_name):
    with pytest.raises(PlacesError):
        fetch_photo(FAKE_KEY, photo_name)
    assert fake_get.calls == []


@pytest.mark.parametrize("setup", ["network", "status", "not-image"])
def test_fetch_photo_errors_raise_places_error_without_key(fake_get, setup):
    if setup == "network":
        fake_get.error = requests.ConnectionError(f"no network key={FAKE_KEY}")
    elif setup == "status":
        fake_get.responses[photo_url()] = FakeResponse(status_code=403, body={"error": FAKE_KEY})
    else:
        fake_get.responses[photo_url()] = FakeResponse(
            content=b"<html>", content_type="text/html"
        )
    with pytest.raises(PlacesError) as caught:
        fetch_photo(FAKE_KEY, PHOTO_NAME)
    assert FAKE_KEY not in str(caught.value)


# --- Network guard (root conftest.py) --------------------------------------

def test_real_requests_are_blocked_in_tests():
    with pytest.raises(requests.ConnectionError):
        requests.get("https://places.googleapis.com/v1/places/place-a", timeout=5)


def test_unfaked_details_call_fails_safely():
    with pytest.raises(PlacesError):
        get_place_details(FAKE_KEY, "place-a")
