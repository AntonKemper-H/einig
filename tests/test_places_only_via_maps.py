"""Tests for E1 – places only via Google Maps (specs/e1-places-only-via-maps.md)."""

import pytest

from app.db import get_db
from typed_option import add_typed_option


def create_room(client, mode="manual", nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def option_count(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM options WHERE room_id = ?", (room_id,)).fetchone()[0]


@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_room_page_has_no_field_for_typed_options(client, mode):
    room_id = create_room(client, mode=mode)
    html = client.get(f"/rooms/{room_id}").get_data(as_text=True)
    assert f'action="/rooms/{room_id}/options"' not in html
    assert "Add an option" not in html
    assert "Add option" not in html
    assert "own option" not in html


@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_find_a_place_on_google_maps_is_offered_in_every_mode(client, mode):
    room_id = create_room(client, mode=mode)
    html = client.get(f"/rooms/{room_id}").get_data(as_text=True)
    assert f'action="/rooms/{room_id}/find"' in html
    assert "Find on Google Maps" in html


def test_posting_a_typed_option_is_refused_and_saves_nothing(app, client):
    room_id = create_room(client)
    response = client.post(f"/rooms/{room_id}/options", data={"label": "Pizza place"})
    assert response.status_code in (404, 405)
    assert option_count(app, room_id) == 0


def test_a_typed_option_from_an_older_room_still_works(app, client):
    room_id = create_room(client)
    add_typed_option(client, room_id, "Pizza place")
    html = client.get(f"/rooms/{room_id}").get_data(as_text=True)
    assert "Pizza place" in html
    assert "Delete" in html
    with app.app_context():
        option_id = get_db().execute("SELECT id FROM options WHERE room_id = ?", (room_id,)).fetchone()[0]
    response = client.post(f"/rooms/{room_id}/options/{option_id}/delete")
    assert response.status_code in (302, 303)
    assert option_count(app, room_id) == 0
