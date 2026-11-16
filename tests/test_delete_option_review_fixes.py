"""Review fix for A7 (mkim-nova's review of PR #38, point 1; specs/a7-delete-option.md).

Before A7 a room's Google options could never be deleted, so "the room has
Google options" also meant "the room has used its one search". Now the
creator can delete them all, and the search must still count as used:
no search form, and no second call to Google.

New file, because tests/test_delete_option.py was already reviewed.
"""

import pytest

from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
ALREADY_SUGGESTED_MESSAGE = "Places have already been suggested for this room."


class FakeResponse:
    def __init__(self, body):
        self.status_code = 200
        self.body = body
        self.text = str(body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post: counts calls and answers with places named after the requested type."""

    def __init__(self):
        self.calls = 0

    def __call__(self, url, **kwargs):
        self.calls += 1
        place_type = kwargs["json"]["includedTypes"][0]
        return FakeResponse({"places": [{"id": f"{place_type}-{self.calls}-{n}"} for n in range(15)]})


@pytest.fixture(autouse=True)
def google(app, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


SEARCH_FORM = {
    "category": "restaurant",
    "radius_m": "1000",
    "latitude": "38.7369876",
    "longitude": "-9.1534999",
    "min_rating": "",
    "max_price_level": "",
}

# mode -> the URL of its one search (C2a "Places nearby", C4 "Surprise me")
SEARCH_PATHS = {"nearby": "suggest", "surprise": "surprise"}


def create_room(client, mode):
    response = client.post("/rooms", data={"title": "Dinner", "mode": mode, "nickname": "Anna"})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def google_option_ids(app, room_id):
    with app.app_context():
        rows = get_db().execute(
            "SELECT id FROM options WHERE room_id = ? AND source = 'google' AND is_replaced = 0",
            (room_id,),
        ).fetchall()
    return [row["id"] for row in rows]


def all_options(app):
    with app.app_context():
        return [tuple(row) for row in get_db().execute("SELECT * FROM options ORDER BY id")]


def search_then_delete_all(app, client, mode):
    room_id = create_room(client, mode)
    path = SEARCH_PATHS[mode]
    response = client.post(f"/rooms/{room_id}/{path}", data=SEARCH_FORM)
    assert response.status_code in (302, 303)
    ids = google_option_ids(app, room_id)
    assert ids
    for option_id in ids:
        response = client.post(f"/rooms/{room_id}/options/{option_id}/delete")
        assert response.status_code in (302, 303)
    assert google_option_ids(app, room_id) == []
    return room_id, path


@pytest.mark.parametrize("mode", ["nearby", "surprise"])
def test_search_form_stays_hidden_after_deleting_every_google_option(app, client, google, mode):
    room_id, path = search_then_delete_all(app, client, mode)
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert f'action="/rooms/{room_id}/{path}"' not in html


@pytest.mark.parametrize("mode", ["nearby", "surprise"])
def test_second_search_after_deleting_every_google_option_never_calls_google(app, client, google, mode):
    room_id, path = search_then_delete_all(app, client, mode)
    calls_before = google.calls
    before = all_options(app)
    response = client.post(f"/rooms/{room_id}/{path}", data=SEARCH_FORM)
    assert response.status_code == 400
    assert ALREADY_SUGGESTED_MESSAGE in response.data.decode()
    assert google.calls == calls_before
    assert all_options(app) == before
