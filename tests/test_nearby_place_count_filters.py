"""E4 follow-up: the chosen number of places is applied AFTER the rating and price filters
(specs/e4-nearby-place-count.md).

Why this file exists: `tests/test_nearby_place_count.py` never sets a filter together with
`place_count`, so an implementation that cuts Google's raw list to N *before* filtering passed
all of its tests. Then four badly rated places at the top of Google's list would leave a room
with one place instead of five. A new file, because the reviewed one must not be edited.
Google is never called: `requests.post` is replaced by a fake.
"""

import pytest

from app.services import places
from tests.test_nearby_place_count import FAKE_KEY, create_room, saved_place_ids, suggest

BAD_RATING = 3.0
GOOD_RATING = 4.6
MIN_RATING = "4.5"
TOO_EXPENSIVE = "PRICE_LEVEL_VERY_EXPENSIVE"  # level 4
AFFORDABLE = "PRICE_LEVEL_MODERATE"  # level 2
MAX_PRICE_LEVEL = "2"


class FakeResponse:
    status_code = 200

    def __init__(self, items):
        self.items = items

    def json(self):
        return {"places": self.items}


class FakeGoogle:
    """Replaces requests.post: always answers with the same places, in this order."""

    def __init__(self):
        self.items = []
        self.calls = 0

    def __call__(self, url, **kwargs):
        self.calls += 1
        return FakeResponse(self.items)


@pytest.fixture
def google(monkeypatch, app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


def ids(numbers):
    return [f"place-{number:02d}" for number in numbers]


def test_the_count_is_applied_after_the_rating_filter(app, client, google):
    # Google's first four places are rated too low, eight good ones follow.
    google.items = [
        {"id": f"place-{number:02d}", "rating": BAD_RATING if number < 4 else GOOD_RATING}
        for number in range(12)
    ]
    room_id = create_room(client)
    assert suggest(client, room_id, place_count="5", min_rating=MIN_RATING).status_code in (302, 303)
    # The first FIVE that pass the filter, not the first five Google sent (of which one would pass).
    assert saved_place_ids(app, room_id) == ids(range(4, 9))


def test_the_count_is_applied_after_the_price_filter(app, client, google):
    # Google's first four places are too expensive, eight affordable ones follow.
    google.items = [
        {"id": f"place-{number:02d}", "priceLevel": TOO_EXPENSIVE if number < 4 else AFFORDABLE}
        for number in range(12)
    ]
    room_id = create_room(client)
    assert suggest(client, room_id, place_count="5", max_price_level=MAX_PRICE_LEVEL).status_code in (302, 303)
    assert saved_place_ids(app, room_id) == ids(range(4, 9))


def test_fewer_places_than_chosen_pass_the_filter_so_all_that_pass_are_saved(app, client, google):
    # Only the last three of twelve places are rated well enough; the count asks for ten.
    google.items = [
        {"id": f"place-{number:02d}", "rating": GOOD_RATING if number >= 9 else BAD_RATING}
        for number in range(12)
    ]
    room_id = create_room(client)
    assert suggest(client, room_id, place_count="10", min_rating=MIN_RATING).status_code in (302, 303)
    assert saved_place_ids(app, room_id) == ids(range(9, 12))
