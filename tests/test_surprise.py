"""Tests for C4 – F12 Surprise mode: selection rules and search rounds (specs/c4-surprise-mode.md).

These tests never call Google: `requests.post` is replaced by a fake for every test.
"""

import random

import pytest
import requests

from app.services import places
from app.services import surprise

FAKE_KEY = "fake-key-for-tests-0123456789"
CATEGORY_MESSAGE = "Please choose a category."
RADIUS_MESSAGE = "Please choose a radius."
LOCATION_MESSAGE = "Please share your location so we can search nearby."
RATING_MESSAGE = "Please choose a valid minimum rating."
PRICE_MESSAGE = "Please choose a valid price level."

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
CAFE_TYPES = ["cafe", "coffee_shop", "tea_house", "dessert_shop"]


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post. Answers each Nearby Search with places of the requested type.

    `places_for(place_type, radius)` returns the list of result dicts for one call,
    so a test can decide how many places exist at which radius.
    """

    def __init__(self, places_for):
        self.places_for = places_for
        self.calls = []
        self.fail_on_call = None  # (call number starting at 1, exception or status code)

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call[0]:
            problem = self.fail_on_call[1]
            if isinstance(problem, int):
                return FakeResponse(status_code=problem)
            raise problem
        body = kwargs["json"]
        place_type = body["includedTypes"][0]
        radius = body["locationRestriction"]["circle"]["radius"]
        return FakeResponse(body={"places": self.places_for(place_type, radius)})

    def types(self):
        return [call["json"]["includedTypes"][0] for call in self.calls]

    def radii(self):
        return [call["json"]["locationRestriction"]["circle"]["radius"] for call in self.calls]


def many_places(place_type, radius):
    """15 places per type, with ids that show their type."""
    return [{"id": f"{place_type}-{number}"} for number in range(15)]


def no_places(place_type, radius):
    return []


@pytest.fixture
def google(monkeypatch):
    fake = FakeGoogle(many_places)
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


def run_search(**changes):
    arguments = {
        "api_key": FAKE_KEY,
        "latitude": 38.737,
        "longitude": -9.153,
        "radius_m": 1000,
        "category": "restaurant",
        "max_price_level": None,
        "min_rating": None,
        "rng": random.Random(1),
    }
    arguments.update(changes)
    return surprise.surprise_search(**arguments)


# --- Constants -------------------------------------------------------------

def test_subcategories_and_constants():
    assert surprise.SUBCATEGORIES == {
        "restaurant": RESTAURANT_TYPES,
        "bar": BAR_TYPES,
        "cafe": CAFE_TYPES,
    }
    assert surprise.SUBCATEGORIES_PER_SEARCH == 4
    assert surprise.SURPRISE_OPTION_COUNT == 5
    assert surprise.WIDENING_FACTOR == 1.5
    assert surprise.MAX_WIDENINGS == 3


# --- choose_subcategories --------------------------------------------------

def test_choose_subcategories_picks_four_different_restaurant_types():
    chosen = surprise.choose_subcategories("restaurant", random.Random(3))
    assert len(chosen) == 4
    assert len(set(chosen)) == 4
    assert set(chosen) <= set(RESTAURANT_TYPES)


@pytest.mark.parametrize("category, types", [("bar", BAR_TYPES), ("cafe", CAFE_TYPES)])
def test_choose_subcategories_uses_all_types_of_small_categories(category, types):
    chosen = surprise.choose_subcategories(category, random.Random(3))
    assert sorted(chosen) == sorted(types)


def test_choose_subcategories_is_random_but_repeatable():
    first = surprise.choose_subcategories("restaurant", random.Random(42))
    again = surprise.choose_subcategories("restaurant", random.Random(42))
    assert first == again
    seen = {tuple(sorted(surprise.choose_subcategories("restaurant", random.Random(seed)))) for seed in range(30)}
    assert len(seen) > 1


# --- widened_radius --------------------------------------------------------

@pytest.mark.parametrize("radius, widened", [(1000, 1500), (1500, 2250), (2250, 3375), (500, 750)])
def test_widened_radius(radius, widened):
    assert surprise.widened_radius(radius) == widened


# --- pick_varied -----------------------------------------------------------

def four_full_lists():
    return [(place_type, [f"{place_type}-{n}" for n in range(15)]) for place_type in BAR_TYPES]


def test_pick_varied_takes_one_per_subcategory_before_a_second():
    picked = surprise.pick_varied(four_full_lists(), 5, random.Random(7))
    assert len(picked) == 5
    first_four_types = [subcategory for _, subcategory in picked[:4]]
    assert sorted(first_four_types) == sorted(BAR_TYPES)
    # The fifth place repeats exactly one sub-category.
    all_types = [subcategory for _, subcategory in picked]
    assert len(set(all_types)) == 4


def test_pick_varied_returns_place_and_subcategory_pairs():
    picked = surprise.pick_varied(four_full_lists(), 5, random.Random(7))
    for place_id, subcategory in picked:
        assert place_id.startswith(subcategory + "-")


def test_pick_varied_never_more_than_count_and_fewer_if_not_enough():
    assert len(surprise.pick_varied(four_full_lists(), 3, random.Random(1))) == 3
    small = [("bar", ["a"]), ("pub", ["b", "c"])]
    picked = surprise.pick_varied(small, 5, random.Random(1))
    assert sorted(place_id for place_id, _ in picked) == ["a", "b", "c"]


def test_pick_varied_skips_duplicates_and_empty_lists():
    results = [("bar", ["same"]), ("pub", ["same", "pub-2"]), ("wine_bar", []), ("bar_and_grill", ["grill-1"])]
    picked = surprise.pick_varied(results, 5, random.Random(1))
    place_ids = [place_id for place_id, _ in picked]
    assert sorted(place_ids) == ["grill-1", "pub-2", "same"]
    assert len(place_ids) == len(set(place_ids))
    assert "wine_bar" not in [subcategory for _, subcategory in picked]


def test_pick_varied_skipped_duplicate_takes_next_place_of_same_subcategory():
    # "bar" picks "same" first; "pub" must then take its other place in the same round.
    results = [("bar", ["same"]), ("pub", ["same", "pub-2"])]
    picked = surprise.pick_varied(results, 2, random.Random(1))
    assert ("pub-2", "pub") in picked
    assert ("same", "bar") in picked


def test_pick_varied_is_random_but_repeatable_and_leaves_input_unchanged():
    results = four_full_lists()
    copy = [(subcategory, list(ids)) for subcategory, ids in results]
    first = surprise.pick_varied(results, 5, random.Random(11))
    again = surprise.pick_varied(results, 5, random.Random(11))
    assert first == again
    assert results == copy
    seen = {tuple(surprise.pick_varied(results, 5, random.Random(seed))) for seed in range(20)}
    assert len(seen) > 1


def test_count_distinct():
    results = [("bar", ["a", "b"]), ("pub", ["b", "c"]), ("wine_bar", [])]
    assert surprise.count_distinct(results) == 3


# --- surprise_search -------------------------------------------------------

def test_search_with_plenty_of_places_makes_four_calls(google):
    result = run_search(radius_m=1000)
    assert len(google.calls) == 4
    assert len(set(google.types())) == 4
    assert set(google.types()) <= set(RESTAURANT_TYPES)
    assert google.radii() == [1000] * 4
    for call in google.calls:
        assert call["url"] == "https://places.googleapis.com/v1/places:searchNearby"
        assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
        assert call["timeout"] == 5
        center = call["json"]["locationRestriction"]["circle"]["center"]
        assert center == {"latitude": 38.737, "longitude": -9.153}
    assert result["radius_m"] == 1000
    assert len(result["choices"]) == 5
    subcategories = [subcategory for _, subcategory in result["choices"]]
    assert len(set(subcategories)) == 4
    assert set(subcategories) == set(google.types())


def test_search_widens_when_too_few_places(google):
    def few_then_many(place_type, radius):
        if radius < 1500:
            return [{"id": f"{place_type}-only"}] if place_type == google.types()[0] else []
        return many_places(place_type, radius)

    google.places_for = few_then_many
    result = run_search(radius_m=1000)
    assert google.radii() == [1000] * 4 + [1500] * 4
    assert google.types()[:4] == google.types()[4:]
    assert result["radius_m"] == 1500
    assert len(result["choices"]) == 5


def test_search_widens_at_most_three_times(google):
    google.places_for = no_places
    result = run_search(radius_m=1000)
    assert len(google.calls) == 16
    assert google.radii() == [1000] * 4 + [1500] * 4 + [2250] * 4 + [3375] * 4
    assert result == {"choices": [], "radius_m": 3375}


def test_search_returns_the_few_places_it_found(google):
    def two_places(place_type, radius):
        return [{"id": "one"}, {"id": "two"}]

    google.places_for = two_places
    result = run_search(radius_m=1000)
    assert len(google.calls) == 16
    assert sorted(place_id for place_id, _ in result["choices"]) == ["one", "two"]


def test_search_applies_filters_to_every_call(google):
    def mixed(place_type, radius):
        return [
            {"id": f"{place_type}-cheap-good", "priceLevel": "PRICE_LEVEL_INEXPENSIVE", "rating": 4.6},
            {"id": f"{place_type}-expensive", "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE", "rating": 4.8},
            {"id": f"{place_type}-bad", "priceLevel": "PRICE_LEVEL_INEXPENSIVE", "rating": 3.0},
            {"id": f"{place_type}-cheap-good-2", "priceLevel": "PRICE_LEVEL_MODERATE", "rating": 4.5},
        ]

    google.places_for = mixed
    result = run_search(max_price_level=2, min_rating=4.5)
    for place_id, _ in result["choices"]:
        assert "expensive" not in place_id
        assert "bad" not in place_id
    assert len(result["choices"]) == 5


def test_search_stops_at_first_timeout(google):
    google.fail_on_call = (2, requests.Timeout("too slow"))
    with pytest.raises(places.PlacesError):
        run_search()
    assert len(google.calls) == 2


@pytest.mark.parametrize("failing_call", [1, 3])
def test_search_error_status_raises(google, failing_call):
    google.fail_on_call = (failing_call, 500)
    with pytest.raises(places.PlacesError):
        run_search()
    assert len(google.calls) == failing_call


# --- validate_surprise -----------------------------------------------------

def surprise_form(**changes):
    form = {
        "category": "restaurant",
        "radius_m": "1000",
        "latitude": "38.7369876",
        "longitude": "-9.1534999",
        "min_rating": "4.0",
        "max_price_level": "2",
    }
    form.update(changes)
    return form


@pytest.mark.parametrize("category", ["restaurant", "bar", "cafe"])
def test_validate_surprise_accepts_valid_form(category):
    cleaned, errors = surprise.validate_surprise(surprise_form(category=category))
    assert errors == []
    assert cleaned == {
        "category": category,
        "radius_m": 1000,
        "latitude": 38.737,
        "longitude": -9.153,
        "min_rating": 4.0,
        "max_price_level": 2,
    }


@pytest.mark.parametrize("category", ["movie_theater", "italian_restaurant", "", None])
def test_validate_surprise_rejects_other_categories(category):
    form = surprise_form()
    if category is None:
        del form["category"]
    else:
        form["category"] = category
    _, errors = surprise.validate_surprise(form)
    assert errors == [CATEGORY_MESSAGE]


def test_validate_surprise_returns_every_message():
    form = surprise_form(
        category="movie_theater", radius_m="42", latitude="", min_rating="5", max_price_level="9"
    )
    _, errors = surprise.validate_surprise(form)
    assert sorted(errors) == sorted(
        [CATEGORY_MESSAGE, RADIUS_MESSAGE, LOCATION_MESSAGE, RATING_MESSAGE, PRICE_MESSAGE]
    )
