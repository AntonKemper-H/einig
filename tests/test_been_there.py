"""Tests for C5 – F13 "Been there": replacement rules and Google calls (specs/c5-been-there.md).

These tests never call Google: `requests.post` is replaced by a fake for every test.
"""

import json
import random

import pytest
import requests

from app.services import places
from app.services import surprise

FAKE_KEY = "fake-key-for-tests-0123456789"
CENTRE = (38.737, -9.153)

RESTAURANT_TYPES = [
    "italian_restaurant",
    "japanese_restaurant",
    "mexican_restaurant",
    "indian_restaurant",
    "thai_restaurant",
    "greek_restaurant",
    "vietnamese_restaurant",
    "turkish_restaurant",
    "chinese_restaurant",
    "korean_restaurant",
    "spanish_restaurant",
    "lebanese_restaurant",
    "vegan_restaurant",
]
BAR_TYPES = ["bar", "pub", "wine_bar", "bar_and_grill"]


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post. `places_for(place_type)` returns the result dicts for one call."""

    def __init__(self, places_for):
        self.places_for = places_for
        self.calls = []
        self.problem = None  # an exception to raise or a status code to answer with

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.problem, int):
            return FakeResponse(status_code=self.problem)
        if self.problem is not None:
            raise self.problem
        place_type = kwargs["json"]["includedTypes"][0]
        return FakeResponse(body={"places": self.places_for(place_type)})

    def types(self):
        return [call["json"]["includedTypes"][0] for call in self.calls]


def numbered_places(place_type):
    return [{"id": f"{place_type}-{number}"} for number in range(15)]


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle(numbered_places)
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


def find(rng=None, subcategories=("thai_restaurant", "greek_restaurant"), known=(), **changes):
    arguments = {
        "api_key": FAKE_KEY,
        "latitude": CENTRE[0],
        "longitude": CENTRE[1],
        "radius_m": 1500,
        "subcategories": list(subcategories),
        "max_price_level": None,
        "min_rating": None,
        "known_place_ids": set(known),
        "rng": rng or random.Random(1),
    }
    arguments.update(changes)
    return surprise.find_replacement(**arguments)


# --- Constants and filters -------------------------------------------------

def test_replacement_limit_is_five():
    assert surprise.MAX_REPLACEMENTS_PER_ROOM == 5


def test_read_filters_reads_c4_filters():
    text = json.dumps(
        {"category": "restaurant", "min_rating": 4.5, "max_price_level": 3, "requested_radius_m": 1000}
    )
    assert surprise.read_filters(text) == {
        "category": "restaurant",
        "min_rating": 4.5,
        "max_price_level": 3,
    }


def test_read_filters_with_null_values():
    text = json.dumps({"category": "bar", "min_rating": None, "max_price_level": None})
    assert surprise.read_filters(text) == {
        "category": "bar",
        "min_rating": None,
        "max_price_level": None,
    }


def test_read_filters_turns_int_rating_into_float():
    filters = surprise.read_filters(json.dumps({"category": "cafe", "min_rating": 4}))
    assert filters["min_rating"] == 4.0
    assert isinstance(filters["min_rating"], float)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "not json {",
        "[1, 2, 3]",
        "{}",
        json.dumps({"category": "movie_theater", "min_rating": "high", "max_price_level": "3"}),
        json.dumps({"category": 7, "min_rating": [4.0], "max_price_level": 2.5}),
        json.dumps({"category": "restaurant", "min_rating": True, "max_price_level": True}),
    ],
)
def test_read_filters_never_raises_and_gives_none_for_bad_values(text):
    filters = surprise.read_filters(text)
    assert set(filters) == {"category", "min_rating", "max_price_level"}
    assert filters["min_rating"] is None
    assert filters["max_price_level"] is None
    if filters["category"] is not None:
        assert filters["category"] == "restaurant"


# --- Which sub-categories are searched ---------------------------------------

def test_replacement_subcategories_same_kind_first_then_one_other():
    for seed in range(30):
        result = surprise.replacement_subcategories(
            "restaurant", "thai_restaurant", ["thai_restaurant", "greek_restaurant"], random.Random(seed)
        )
        assert len(result) == 2
        assert result[0] == "thai_restaurant"
        assert result[1] in RESTAURANT_TYPES
        assert result[1] != "thai_restaurant"


def test_replacement_subcategories_prefers_an_unused_one():
    # Every bar type except "wine_bar" is already on an active option.
    for seed in range(30):
        result = surprise.replacement_subcategories(
            "bar", "pub", ["bar", "pub", "bar_and_grill"], random.Random(seed)
        )
        assert result == ["pub", "wine_bar"]


def test_replacement_subcategories_falls_back_to_any_other_when_all_are_used():
    seen = set()
    for seed in range(50):
        result = surprise.replacement_subcategories("bar", "pub", list(BAR_TYPES), random.Random(seed))
        assert result[0] == "pub"
        assert len(result) == 2
        assert result[1] in BAR_TYPES and result[1] != "pub"
        seen.add(result[1])
    assert len(seen) > 1


def test_replacement_subcategories_without_main_category_searches_only_same_kind():
    assert surprise.replacement_subcategories(
        None, "thai_restaurant", ["thai_restaurant"], random.Random(1)
    ) == ["thai_restaurant"]


def test_replacement_subcategories_is_random_but_repeatable():
    active = ["thai_restaurant", "greek_restaurant"]
    first = surprise.replacement_subcategories("restaurant", "thai_restaurant", active, random.Random(7))
    again = surprise.replacement_subcategories("restaurant", "thai_restaurant", active, random.Random(7))
    assert first == again
    seconds = {
        surprise.replacement_subcategories("restaurant", "thai_restaurant", active, random.Random(seed))[1]
        for seed in range(50)
    }
    assert len(seconds) > 1


# --- Which place is picked ---------------------------------------------------

def test_pick_replacement_never_returns_a_known_place():
    place_ids = ["a", "b", "c", "d"]
    for seed in range(30):
        assert surprise.pick_replacement(place_ids, {"a", "c"}, random.Random(seed)) in {"b", "d"}


def test_pick_replacement_returns_none_when_nothing_is_new():
    assert surprise.pick_replacement(["a", "b"], {"a", "b"}, random.Random(1)) is None
    assert surprise.pick_replacement([], set(), random.Random(1)) is None


def test_pick_replacement_is_random_not_always_the_first():
    place_ids = [f"place-{number}" for number in range(15)]
    picks = {surprise.pick_replacement(place_ids, set(), random.Random(seed)) for seed in range(50)}
    assert len(picks) > 1


# --- The Google calls --------------------------------------------------------

def test_find_replacement_with_a_new_place_in_the_same_kind(google):
    result = find(known={"thai_restaurant-0"})
    assert len(google.calls) == 1
    call = google.calls[0]
    assert call["json"]["includedTypes"] == ["thai_restaurant"]
    circle = call["json"]["locationRestriction"]["circle"]
    assert circle["center"] == {"latitude": CENTRE[0], "longitude": CENTRE[1]}
    assert circle["radius"] == 1500
    assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert call["timeout"] == 5
    place_id, subcategory = result
    assert subcategory == "thai_restaurant"
    assert place_id.startswith("thai_restaurant-")
    assert place_id != "thai_restaurant-0"


def test_find_replacement_tries_the_second_kind_when_the_first_has_nothing_new(google):
    known = {f"thai_restaurant-{number}" for number in range(15)}
    place_id, subcategory = find(known=known)
    assert google.types() == ["thai_restaurant", "greek_restaurant"]
    assert subcategory == "greek_restaurant"
    assert place_id.startswith("greek_restaurant-")


def test_find_replacement_returns_none_after_at_most_two_calls(google):
    google.places_for = lambda place_type: []
    assert find() is None
    assert len(google.calls) == 2


def test_find_replacement_applies_price_and_rating_filters(google):
    google.places_for = lambda place_type: [
        {"id": f"{place_type}-expensive", "rating": 4.8, "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE"},
        {"id": f"{place_type}-bad", "rating": 3.0, "priceLevel": "PRICE_LEVEL_INEXPENSIVE"},
        {"id": f"{place_type}-good", "rating": 4.6, "priceLevel": "PRICE_LEVEL_MODERATE"},
    ]
    for seed in range(10):
        place_id, _ = find(rng=random.Random(seed), max_price_level=2, min_rating=4.5)
        assert place_id == "thai_restaurant-good"


def test_find_replacement_stops_at_once_on_timeout(google):
    google.problem = requests.Timeout("too slow")
    with pytest.raises(places.PlacesError):
        find()
    assert len(google.calls) == 1


def test_find_replacement_raises_on_error_status(google):
    google.problem = 403
    with pytest.raises(places.PlacesError):
        find()
    assert len(google.calls) == 1
