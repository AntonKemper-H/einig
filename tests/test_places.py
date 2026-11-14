"""Tests for C2a – the Google Places call and the search form rules (specs/c2-places-search.md).

These tests never call Google: `requests.post` is always replaced by a fake.
"""

import math

import pytest
import requests

from app.services import places
from app.services.places import PlacesError, round_coordinate, search_nearby, validate_search

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
FIELD_MASK = "places.id,places.rating,places.priceLevel"
FAKE_KEY = "fake-key-for-tests-0123456789"


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

    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse(body={"places": []})
        self.error = error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response


def place(place_id, rating=None, price_level=None):
    """One result as Google sends it (only the fields of our field mask)."""
    result = {"id": place_id}
    if rating is not None:
        result["rating"] = rating
    if price_level is not None:
        result["priceLevel"] = price_level
    return result


@pytest.fixture
def fake_google(monkeypatch):
    """A fake Google that finds nothing; tests set .response or .error as needed."""
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


def search(max_price_level=None, min_rating=None):
    """Call search_nearby with fixed, valid arguments."""
    return search_nearby(
        api_key=FAKE_KEY,
        latitude=38.737,
        longitude=-9.153,
        radius_m=1000,
        category="restaurant",
        max_price_level=max_price_level,
        min_rating=min_rating,
    )


# --- The request -----------------------------------------------------------

def test_sends_one_post_to_nearby_search_with_timeout(fake_google):
    search()
    assert len(fake_google.calls) == 1
    call = fake_google.calls[0]
    assert call["url"] == NEARBY_URL
    assert call["timeout"] == 5


def test_sends_api_key_and_field_mask_headers(fake_google):
    search()
    headers = fake_google.calls[0]["headers"]
    assert headers["X-Goog-Api-Key"] == FAKE_KEY
    assert headers["X-Goog-FieldMask"] == FIELD_MASK
    assert "*" not in headers["X-Goog-FieldMask"]
    assert places.SEARCH_FIELD_MASK == FIELD_MASK


def test_sends_category_count_centre_and_radius(fake_google):
    search()
    body = fake_google.calls[0]["json"]
    assert body["includedTypes"] == ["restaurant"]
    assert body["maxResultCount"] == 15
    circle = body["locationRestriction"]["circle"]
    assert circle["center"] == {"latitude": 38.737, "longitude": -9.153}
    assert circle["radius"] == 1000


# --- The response ----------------------------------------------------------

def test_returns_place_ids_in_google_order(fake_google):
    fake_google.response = FakeResponse(body={"places": [place("c"), place("a"), place("b")]})
    assert search() == ["c", "a", "b"]


def test_response_without_places_returns_empty_list(fake_google):
    fake_google.response = FakeResponse(body={})
    assert search() == []


def test_skips_results_without_id_and_duplicates(fake_google):
    fake_google.response = FakeResponse(
        body={"places": [place("a"), {"rating": 4.0}, place("b"), place("a")]}
    )
    assert search() == ["a", "b"]


def test_max_price_level_drops_expensive_and_keeps_unknown(fake_google):
    fake_google.response = FakeResponse(
        body={
            "places": [
                place("free", price_level="PRICE_LEVEL_FREE"),
                place("cheap", price_level="PRICE_LEVEL_INEXPENSIVE"),
                place("moderate", price_level="PRICE_LEVEL_MODERATE"),
                place("expensive", price_level="PRICE_LEVEL_EXPENSIVE"),
                place("very", price_level="PRICE_LEVEL_VERY_EXPENSIVE"),
                place("unknown"),
            ]
        }
    )
    assert search(max_price_level=2) == ["free", "cheap", "moderate", "unknown"]


def test_min_rating_drops_lower_and_unrated_keeps_exact(fake_google):
    fake_google.response = FakeResponse(
        body={
            "places": [
                place("low", rating=3.9),
                place("exact", rating=4.0),
                place("high", rating=4.7),
                place("unrated"),
            ]
        }
    )
    assert search(min_rating=4.0) == ["exact", "high"]


def test_without_filters_all_results_are_kept(fake_google):
    fake_google.response = FakeResponse(
        body={
            "places": [
                place("a", rating=1.0, price_level="PRICE_LEVEL_VERY_EXPENSIVE"),
                place("b"),
            ]
        }
    )
    assert search() == ["a", "b"]


# --- Errors ----------------------------------------------------------------

@pytest.mark.parametrize(
    "error",
    [requests.Timeout("timed out"), requests.ConnectionError("no network")],
    ids=["timeout", "connection-error"],
)
def test_network_errors_raise_places_error(fake_google, error):
    fake_google.error = error
    with pytest.raises(PlacesError):
        search()


@pytest.mark.parametrize("status_code", [400, 403, 429, 500])
def test_non_200_status_raises_places_error(fake_google, status_code):
    fake_google.response = FakeResponse(status_code=status_code, body={"error": {}})
    with pytest.raises(PlacesError):
        search()


def test_invalid_json_raises_places_error(fake_google):
    fake_google.response = FakeResponse(invalid_json=True)
    with pytest.raises(PlacesError):
        search()


@pytest.mark.parametrize(
    "setup",
    ["timeout", "status", "invalid-json"],
)
def test_places_error_never_contains_the_key(fake_google, setup):
    if setup == "timeout":
        fake_google.error = requests.Timeout(f"timed out for key={FAKE_KEY}")
    elif setup == "status":
        fake_google.response = FakeResponse(status_code=403, body={"error": {"message": FAKE_KEY}})
    else:
        fake_google.response = FakeResponse(invalid_json=True)
    with pytest.raises(PlacesError) as caught:
        search()
    assert FAKE_KEY not in str(caught.value)


# --- Rounding --------------------------------------------------------------

def test_round_coordinate_rounds_to_three_decimals():
    assert round_coordinate(38.7369876) == 38.737
    assert round_coordinate(-9.1534999) == -9.153
    assert round_coordinate(10.0) == 10.0


# --- Form rules ------------------------------------------------------------

def valid_form(**changes):
    """A valid search form as the browser sends it (all values are text)."""
    form = {
        "category": "restaurant",
        "radius_m": "1000",
        "latitude": "38.7369876",
        "longitude": "-9.1534999",
        "min_rating": "",
        "max_price_level": "",
    }
    form.update(changes)
    return form


def test_validate_search_accepts_valid_form_with_typed_values():
    cleaned, errors = validate_search(valid_form(min_rating="4.0", max_price_level="2"))
    assert errors == []
    assert cleaned == {
        "category": "restaurant",
        "radius_m": 1000,
        "latitude": 38.737,
        "longitude": -9.153,
        "min_rating": 4.0,
        "max_price_level": 2,
    }


def test_validate_search_empty_filters_mean_no_filter():
    cleaned, errors = validate_search(valid_form())
    assert errors == []
    assert cleaned["min_rating"] is None
    assert cleaned["max_price_level"] is None


@pytest.mark.parametrize("category", ["restaurant", "bar", "cafe", "movie_theater"])
def test_validate_search_accepts_every_category(category):
    _, errors = validate_search(valid_form(category=category))
    assert errors == []


@pytest.mark.parametrize("radius", ["500", "1000", "2000", "5000"])
def test_validate_search_accepts_every_radius(radius):
    cleaned, errors = validate_search(valid_form(radius_m=radius))
    assert errors == []
    assert cleaned["radius_m"] == int(radius)


@pytest.mark.parametrize("category", ["", "museum", "Restaurant", None])
def test_validate_search_rejects_unknown_or_missing_category(category):
    form = valid_form()
    if category is None:
        del form["category"]
    else:
        form["category"] = category
    _, errors = validate_search(form)
    assert errors == ["Please choose a category."]


@pytest.mark.parametrize("radius", ["", "750", "-1000", "abc", "1000.0", "50000"])
def test_validate_search_rejects_unknown_radius(radius):
    _, errors = validate_search(valid_form(radius_m=radius))
    assert errors == ["Please choose a radius."]


@pytest.mark.parametrize(
    "latitude, longitude",
    [
        ("", ""),
        ("38.7", ""),
        ("", "-9.1"),
        ("north", "-9.1"),
        ("nan", "-9.1"),
        ("38.7", "inf"),
        ("90.5", "-9.1"),
        ("-91", "-9.1"),
        ("38.7", "180.1"),
        ("38.7", "-181"),
    ],
)
def test_validate_search_rejects_bad_location(latitude, longitude):
    _, errors = validate_search(valid_form(latitude=latitude, longitude=longitude))
    assert errors == ["Please share your location so we can search nearby."]


def test_validate_search_rejects_missing_location_fields():
    form = valid_form()
    del form["latitude"]
    del form["longitude"]
    _, errors = validate_search(form)
    assert errors == ["Please share your location so we can search nearby."]


def test_validate_search_accepts_location_at_the_limits():
    cleaned, errors = validate_search(valid_form(latitude="-90", longitude="180"))
    assert errors == []
    assert cleaned["latitude"] == -90.0
    assert cleaned["longitude"] == 180.0
    assert not math.isnan(cleaned["latitude"])


@pytest.mark.parametrize("min_rating", ["3", "5", "abc", "4.2", "-1"])
def test_validate_search_rejects_unknown_min_rating(min_rating):
    _, errors = validate_search(valid_form(min_rating=min_rating))
    assert errors == ["Please choose a valid minimum rating."]


@pytest.mark.parametrize("max_price_level", ["0", "5", "cheap", "1.5"])
def test_validate_search_rejects_unknown_price_level(max_price_level):
    _, errors = validate_search(valid_form(max_price_level=max_price_level))
    assert errors == ["Please choose a valid price level."]


def test_validate_search_returns_every_message_at_once():
    _, errors = validate_search(
        {
            "category": "museum",
            "radius_m": "7",
            "latitude": "",
            "longitude": "",
            "min_rating": "9",
            "max_price_level": "9",
        }
    )
    assert errors == [
        "Please choose a category.",
        "Please choose a radius.",
        "Please share your location so we can search nearby.",
        "Please choose a valid minimum rating.",
        "Please choose a valid price level.",
    ]
