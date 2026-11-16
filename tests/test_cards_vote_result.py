"""Tests for C2c – place cards on the rating page and real names on the result page
(specs/c2c-cards-vote-result.md).

These tests never call Google: `requests.get` is replaced by a fake, and the
root conftest.py makes any other real request fail.
"""

import pytest

from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
FAKE_EMBED_KEY = "fake-embed-key-0123"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
FALLBACK_NAME = "Place from Google Maps"
DETAILS_MISSING = "Details are not available right now."
CENTRE = (38.737, -9.153)

NAMES = {"place-a": "Pizza Roma", "place-b": "Sushi Bar", "place-c": "Café Lisboa"}


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.content = b""
        self.headers = {"Content-Type": "application/json"}
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGet:
    """Replaces requests.get: answers by URL (or raises a prepared exception), records every call."""

    def __init__(self):
        self.responses = {}
        self.default = FakeResponse(status_code=404, body={"error": {}})
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        response = self.responses.get(url, self.default)
        if isinstance(response, Exception):
            raise response
        return response

    def detail_place_ids(self):
        return [
            call["url"][len(DETAILS_URL):]
            for call in self.calls
            if call["url"].startswith(DETAILS_URL) and not call["url"].endswith("/media")
        ]


def place_body(place_id, name):
    return {
        "displayName": {"text": name},
        "rating": 4.5,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "location": {"latitude": 38.740, "longitude": -9.153},
        "photos": [
            {
                "name": f"places/{place_id}/photos/photo-ref-1",
                "authorAttributions": [{"displayName": "Maria Silva", "uri": "https://maps.google.com/maria"}],
            }
        ],
    }


@pytest.fixture(autouse=True)
def google(monkeypatch):
    fake = FakeGet()
    for place_id, name in NAMES.items():
        fake.responses[DETAILS_URL + place_id] = FakeResponse(body=place_body(place_id, name))
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


@pytest.fixture(autouse=True)
def api_keys(app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    app.config["GOOGLE_MAPS_EMBED_KEY"] = FAKE_EMBED_KEY


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    response = client.post(
        "/rooms", data={"title": "Dinner on Friday", "mode": "nearby", "nickname": nickname}
    )
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def setup_options(app, room_id, place_ids, manual_labels=()):
    """Store Google options (with the room's centre) and manual options directly; return {key: option id}."""
    ids = {}
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE rooms SET search_center_lat = ?, search_center_lng = ?, radius_m = 1000 WHERE id = ?",
            (CENTRE[0], CENTRE[1], room_id),
        )
        for place_id in place_ids:
            db.execute(
                "INSERT INTO options (room_id, source, place_id, category) VALUES (?, 'google', ?, 'restaurant')",
                (room_id, place_id),
            )
        for label in manual_labels:
            db.execute(
                "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)", (room_id, label)
            )
        for row in db.execute("SELECT id, place_id, label FROM options WHERE room_id = ?", (room_id,)):
            ids[row["place_id"] or row["label"]] = row["id"]
        db.commit()
    return ids


def set_status(app, room_id, status):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def participant_id(app, room_id, nickname="Anna"):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM participants WHERE room_id = ? AND nickname = ?", (room_id, nickname)
        ).fetchone()["id"]


def add_votes(app, room_id, option_ids, rating="yes", nickname="Anna"):
    person = participant_id(app, room_id, nickname)
    with app.app_context():
        db = get_db()
        for option_id in option_ids:
            db.execute(
                "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, ?)",
                (room_id, person, option_id, rating),
            )
        db.commit()


def close_with_winner(app, room_id, winner_option_id):
    """Close the room as B3 does: store the winner and delete the search centre."""
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE rooms SET status = 'closed', winner_option_id = ?,"
            " search_center_lat = NULL, search_center_lng = NULL WHERE id = ?",
            (winner_option_id, room_id),
        )
        db.commit()


def get_page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.data.decode()


def count_list(html):
    """The part of the result page below "How the options were rated"."""
    return html.split("How the options were rated", 1)[1]


# --- Rating page -----------------------------------------------------------

def test_next_google_card_is_loaded_alone(app, client, google):
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a", "place-b", "place-c"])
    set_status(app, room_id, "voting")
    html = get_page(client, f"/rooms/{room_id}/vote")

    assert len(google.calls) == 1
    shown = google.detail_place_ids()[0]
    assert NAMES[shown] in html
    for other in set(NAMES) - {shown}:
        assert NAMES[other] not in html
    assert f'<img src="/photo/places/{shown}/photos/photo-ref-1"' in html
    assert "4.5 ★ · €€ · 330 m" in html
    assert "Google Maps" in html
    assert 'name="option_id"' in html
    for label in ("Rather yes", "Fine with me", "Rather not"):
        assert label in html


def test_next_manual_card_does_not_call_google(app, client, google):
    room_id = create_room(client)
    ids = setup_options(app, room_id, ["place-a"], manual_labels=["Cook at home"])
    add_votes(app, room_id, [ids["place-a"]])
    set_status(app, room_id, "voting")
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert "<h2>Cook at home</h2>" in html
    assert google.calls == []


def test_overview_loads_each_google_option_once(app, client, google):
    room_id = create_room(client)
    ids = setup_options(app, room_id, ["place-a", "place-b"], manual_labels=["Cook at home"])
    add_votes(app, room_id, ids.values())
    set_status(app, room_id, "voting")
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert "You have rated all options." in html
    assert "Pizza Roma" in html
    assert "Sushi Bar" in html
    assert "Cook at home" in html
    assert html.count("Your rating: Rather yes") == 3
    assert sorted(google.detail_place_ids()) == ["place-a", "place-b"]


def test_overview_stops_after_google_timeout(app, client, google):
    room_id = create_room(client)
    ids = setup_options(app, room_id, ["place-a", "place-b", "place-c"])
    add_votes(app, room_id, ids.values())
    set_status(app, room_id, "voting")
    for place_id in NAMES:
        google.responses[DETAILS_URL + place_id] = places.requests.Timeout("timed out")
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert len(google.calls) == 1
    assert html.count(FALLBACK_NAME) == 3
    assert html.count(DETAILS_MISSING) == 3


def test_failed_details_show_fallback_with_buttons(app, client, google):
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a"])
    set_status(app, room_id, "voting")
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=500)
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert html.count(FALLBACK_NAME) == 1
    assert DETAILS_MISSING in html
    assert "Rather yes" in html


def test_rating_page_without_key_does_not_call_google(app, client, google):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a"])
    set_status(app, room_id, "voting")
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert html.count(FALLBACK_NAME) == 1
    assert google.calls == []


@pytest.mark.parametrize("status", ["collecting", "closed"])
def test_rating_page_outside_voting_does_not_call_google(app, client, google, status):
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a", "place-b"])
    set_status(app, room_id, status)
    client.get(f"/rooms/{room_id}/vote")
    assert google.calls == []


def test_rating_page_escapes_google_names(app, client, google):
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a"])
    set_status(app, room_id, "voting")
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(
        body=place_body("place-a", "<script>alert(1)</script>")
    )
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_rating_page_never_shows_the_key(app, client):
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a"])
    set_status(app, room_id, "voting")
    assert FAKE_KEY not in get_page(client, f"/rooms/{room_id}/vote")


def test_rating_a_google_option_still_works(app, client, google):
    room_id = create_room(client)
    ids = setup_options(app, room_id, ["place-a", "place-b"])
    set_status(app, room_id, "voting")
    response = client.post(
        f"/rooms/{room_id}/vote", data={"option_id": ids["place-a"], "rating": "yes"}
    )
    assert response.status_code in (302, 303)
    with app.app_context():
        saved = get_db().execute(
            "SELECT rating FROM votes WHERE option_id = ?", (ids["place-a"],)
        ).fetchall()
    assert [row["rating"] for row in saved] == ["yes"]
    google.calls.clear()
    html = get_page(client, f"/rooms/{room_id}/vote")
    assert google.detail_place_ids() == ["place-b"]
    assert "Sushi Bar" in html



def test_rejected_vote_shows_the_card_again(app, client, google):
    room_id = create_room(client)
    ids = setup_options(app, room_id, ["place-a"])
    set_status(app, room_id, "voting")
    response = client.post(
        f"/rooms/{room_id}/vote", data={"option_id": ids["place-a"], "rating": "maybe"}
    )
    html = response.data.decode()
    assert response.status_code == 400
    assert "Please choose one of the three ratings." in html
    assert "Pizza Roma" in html
    assert google.detail_place_ids() == ["place-a"]
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0


# --- Result page -----------------------------------------------------------

def closed_room(app, client, place_ids=("place-a", "place-b"), manual=("Cook at home",), winner="place-a"):
    room_id = create_room(client)
    ids = setup_options(app, room_id, list(place_ids), manual_labels=list(manual))
    add_votes(app, room_id, ids.values())
    close_with_winner(app, room_id, ids[winner])
    return room_id


def test_result_count_list_shows_names_with_one_call_per_place(app, client, google):
    room_id = closed_room(app, client)
    html = get_page(client, f"/rooms/{room_id}/result")
    assert "The group's choice: Pizza Roma" in html
    counts = count_list(html)
    assert "Pizza Roma" in counts
    assert "Sushi Bar" in counts
    assert "Cook at home" in counts
    assert FALLBACK_NAME not in counts
    assert sorted(google.detail_place_ids()) == ["place-a", "place-b"]


def test_result_failed_place_falls_back_only_there(app, client, google):
    google.responses[DETAILS_URL + "place-b"] = FakeResponse(status_code=500)
    room_id = closed_room(app, client)
    counts = count_list(get_page(client, f"/rooms/{room_id}/result"))
    assert "Pizza Roma" in counts
    assert counts.count(FALLBACK_NAME) == 1


def test_result_without_key_does_not_call_google(app, client, google):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    room_id = closed_room(app, client)
    html = get_page(client, f"/rooms/{room_id}/result")
    assert "The group's choice: Place from Google Maps" in html
    assert count_list(html).count(FALLBACK_NAME) == 2
    assert google.calls == []


def test_result_stops_after_google_timeout_and_keeps_route(app, client, google):
    for place_id in NAMES:
        google.responses[DETAILS_URL + place_id] = places.requests.Timeout("timed out")
    room_id = closed_room(app, client)
    html = get_page(client, f"/rooms/{room_id}/result")
    assert len(google.calls) == 1
    assert "Open route in Google Maps" in html


def test_result_page_before_closing_does_not_call_google(app, client, google):
    room_id = create_room(client)
    setup_options(app, room_id, ["place-a", "place-b"])
    set_status(app, room_id, "voting")
    client.get(f"/rooms/{room_id}/result")
    assert google.calls == []


def test_result_count_list_shows_only_names(app, client, google):
    room_id = closed_room(app, client)
    counts = count_list(get_page(client, f"/rooms/{room_id}/result"))
    assert "/photo/places/place-b/" not in counts
    assert "4.5 ★" not in counts


def test_result_count_list_escapes_google_names(app, client, google):
    google.responses[DETAILS_URL + "place-b"] = FakeResponse(
        body=place_body("place-b", "<b>bold</b>")
    )
    room_id = closed_room(app, client)
    counts = count_list(get_page(client, f"/rooms/{room_id}/result"))
    assert "<b>bold</b>" not in counts
    assert "&lt;b&gt;bold&lt;/b&gt;" in counts


# --- load_winner with a card ------------------------------------------------

def google_option(place_id="place-a"):
    return {"id": 1, "source": "google", "label": None, "place_id": place_id}


def test_load_winner_with_card_does_not_call_google(google):
    card = places.build_card(google_option(), None, None, None)
    card["name"] = "Given Name"
    winner = places.load_winner(FAKE_KEY, FAKE_EMBED_KEY, google_option(), card=card)
    assert google.calls == []
    assert winner["card"] is card
    assert winner["map_url"] == places.map_embed_url(FAKE_EMBED_KEY, "place-a")
    assert winner["route_url"] == places.route_url("place-a", "Given Name")


def test_load_winner_without_card_still_loads_details(google):
    winner = places.load_winner(FAKE_KEY, FAKE_EMBED_KEY, google_option())
    assert google.detail_place_ids() == ["place-a"]
    assert winner["card"]["name"] == "Pizza Roma"
