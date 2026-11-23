"""Tests for E4 – choose how many places "Places nearby" suggests (specs/e4-nearby-place-count.md)."""

import re

import pytest

from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
COUNT_MESSAGE = "Please choose how many places to suggest."


class FakeResponse:
    def __init__(self, place_ids):
        self.status_code = 200
        self.body = {"places": [{"id": place_id} for place_id in place_ids]}

    def json(self):
        return self.body


class FakeGoogle:
    def __init__(self, place_ids):
        self.place_ids = place_ids
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.place_ids)


@pytest.fixture
def google(monkeypatch, app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGoogle([f"place-{number:02d}" for number in range(12)])
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


def create_room(client, mode="nearby"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": mode, "nickname": "Anna"})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def suggest(client, room_id, **changes):
    form = {
        "category": "restaurant",
        "radius_m": "1000",
        "latitude": "38.7369876",
        "longitude": "-9.1534999",
        "min_rating": "",
        "max_price_level": "",
    }
    form.update(changes)
    return client.post(f"/rooms/{room_id}/suggest", data=form)


def saved_place_ids(app, room_id):
    with app.app_context():
        rows = get_db().execute(
            "SELECT place_id FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()
    return [row["place_id"] for row in rows]


def count_select(html):
    match = re.search(r'<select[^>]*name="place_count"[^>]*>(.*?)</select>', html, flags=re.DOTALL)
    return match.group(1) if match else None


def test_the_nearby_form_offers_5_10_and_15(client, google):
    room_id = create_room(client)
    select = count_select(client.get(f"/rooms/{room_id}").get_data(as_text=True))
    assert select is not None
    assert re.findall(r'<option[^>]*value="([^"]*)"', select) == ["5", "10", "15"]
    selected = re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', select)
    assert selected and selected.group(1) == "15"


def test_the_surprise_form_has_no_count(client, google):
    room_id = create_room(client, mode="surprise")
    html = client.get(f"/rooms/{room_id}").get_data(as_text=True)
    assert f'action="/rooms/{room_id}/surprise"' in html
    assert count_select(html) is None


def test_five_saves_the_first_five_in_googles_order(app, client, google):
    room_id = create_room(client)
    assert suggest(client, room_id, place_count="5").status_code in (302, 303)
    assert saved_place_ids(app, room_id) == [f"place-{number:02d}" for number in range(5)]


def test_fewer_places_than_chosen_are_all_saved(app, client, google):
    google.place_ids = ["place-a", "place-b", "place-c"]
    room_id = create_room(client)
    assert suggest(client, room_id, place_count="10").status_code in (302, 303)
    assert saved_place_ids(app, room_id) == ["place-a", "place-b", "place-c"]


def test_without_a_count_up_to_fifteen_are_saved(app, client, google):
    room_id = create_room(client)
    assert suggest(client, room_id).status_code in (302, 303)
    assert len(saved_place_ids(app, room_id)) == 12


def test_google_is_still_asked_for_fifteen(client, google):
    room_id = create_room(client)
    suggest(client, room_id, place_count="5")
    assert google.calls[0]["json"]["maxResultCount"] == 15


def test_an_invalid_count_is_rejected_and_nothing_changes(app, client, google):
    room_id = create_room(client)
    response = suggest(client, room_id, place_count="7", radius_m="2000")
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert COUNT_MESSAGE in html
    assert saved_place_ids(app, room_id) == []
    assert google.calls == []
    assert re.search(r'<option[^>]*value="2000"[^>]*selected', html)
