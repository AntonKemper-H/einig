"""Tests for E2 – small map for every match of the search by name (specs/e2-match-maps.md)."""

import pytest

from app.services import places

EMBED_KEY = "fake-embed-key-for-tests-9876543210"
API_KEY = "fake-server-key-for-tests-0123456789"
MATCHES = [
    {"place_id": "ChIJplace-one", "name": "Trattoria Luigi", "address": "Hauptstrasse 1, Berlin"},
    {"place_id": "ChIJplace-two", "name": "Trattoria Luigi", "address": "Bahnhofstrasse 9, Hamburg"},
]


@pytest.fixture
def room(app, client, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = API_KEY
    app.config["GOOGLE_MAPS_EMBED_KEY"] = EMBED_KEY
    monkeypatch.setattr(places, "search_by_name", lambda *args, **kwargs: MATCHES)
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": "Anna"})
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def find(client, room_id):
    response = client.post(f"/rooms/{room_id}/find", data={"name": "Trattoria Luigi"})
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_every_match_has_its_own_map(app, client, room):
    html = find(client, room)
    assert html.count("<iframe") == len(MATCHES)
    for match in MATCHES:
        assert places.map_embed_url(EMBED_KEY, match["place_id"]).replace("&", "&amp;") in html
    assert 'loading="lazy"' in html


def test_map_is_before_the_add_button_of_its_match(client, room):
    html = find(client, room)
    first_map = html.index("<iframe")
    first_button = html.index("Add this place")
    assert first_map < first_button


def test_server_key_never_appears(client, room):
    assert API_KEY not in find(client, room)


def test_without_embed_key_matches_have_no_map(app, client, room):
    app.config["GOOGLE_MAPS_EMBED_KEY"] = ""
    html = find(client, room)
    assert "<iframe" not in html
    assert html.count("Add this place") == len(MATCHES)


def test_an_invalid_place_id_gets_no_map(app, client, room, monkeypatch):
    bad = [{"place_id": "bad id\"><script>", "name": "Evil", "address": "x"}]
    monkeypatch.setattr(places, "search_by_name", lambda *args, **kwargs: bad)
    assert "<iframe" not in find(client, room)


def test_page_jumps_to_the_matches(client, room):
    html = find(client, room)
    assert 'id="find-results" tabindex="-1" autofocus>Which one do you mean?' in html
