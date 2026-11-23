"""Tests for E5 – typed options come back, but only while Google Maps is unavailable
(specs/e5-typed-options-as-fallback.md, decision D23).

These tests never call Google: `requests.post` (Text Search and Nearby Search) is
replaced by a fake, as in tests/test_place_by_name_route.py. The fallback state is
moved in time by passing `now` to the functions in app/services/places.py.
"""

from datetime import timedelta

import pytest
import requests
from typed_option import add_typed_option

from app import create_app
from app.db import get_db
from app.services import places
from app.services.deadline import now_utc

FAKE_KEY = "fake-key-for-tests-0123456789"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
CENTRE = (38.737, -9.153)

FALLBACK_LINE = "Google Maps is not reachable right now – you can add your idea as text."
UNAVAILABLE_MESSAGE = "Place suggestions are not available right now."
NOT_JOINED_MESSAGE = "Please join the room before adding options."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
EMPTY_LABEL_MESSAGE = "Please enter an option."
LONG_LABEL_MESSAGE = "An option can be at most 80 characters."
DUPLICATE_MESSAGE = "This option is already in the list."
SAME_IDEA_MESSAGE = "Someone already had the same idea – it is already in the room."
LIMIT_MESSAGE = "You can add at most 1 option in this room."

MATCHES = [
    {"id": "place-luigi-1", "displayName": {"text": "Trattoria Luigi"}, "formattedAddress": "Rua Augusta 10, Lisboa"},
]


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post. With .problem set, every call raises it (Google unreachable)."""

    def __init__(self):
        self.problem = None

    def __call__(self, url, **kwargs):
        if self.problem is not None:
            raise self.problem
        if url == TEXT_SEARCH_URL:
            return FakeResponse(body={"places": MATCHES})
        return FakeResponse(body={"places": [{"id": "nearby-1"}, {"id": "nearby-2"}]})


@pytest.fixture(autouse=True)
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


@pytest.fixture(autouse=True)
def api_key(app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY


# --- Helpers ---------------------------------------------------------------

def create_room(client, mode="manual", nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner on Friday", "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(app, room_id, nickname):
    browser = app.test_client()
    response = browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)
    return browser


def page(client, room_id):
    return client.get(f"/rooms/{room_id}").get_data(as_text=True)


def find(client, room_id, name="Trattoria Luigi"):
    return client.post(f"/rooms/{room_id}/find", data={"name": name})


def search_form():
    return {
        "category": "restaurant",
        "radius_m": "1000",
        "latitude": str(CENTRE[0]),
        "longitude": str(CENTRE[1]),
        "min_rating": "",
        "max_price_level": "",
    }


def add_label(client, room_id, label):
    return client.post(f"/rooms/{room_id}/options", data={"label": label})


def break_google(google):
    google.problem = requests.Timeout("Google did not answer.")


def turn_fallback_on(client, google, room_id):
    """A failed search by name: the way the fallback is switched on in normal use."""
    break_google(google)
    assert find(client, room_id).status_code == 503
    google.problem = None


def options(app, room_id):
    with app.app_context():
        return get_db().execute(
            "SELECT id, source, label FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def author_rows(app, room_id):
    with app.app_context():
        return [
            tuple(row)
            for row in get_db().execute(
                "SELECT option_id, participant_id FROM option_authors WHERE room_id = ? ORDER BY option_id",
                (room_id,),
            )
        ]


def participant_id(app, room_id, nickname):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM participants WHERE room_id = ? AND nickname = ?", (room_id, nickname)
        ).fetchone()["id"]


def set_room_status(app, room_id, status):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def save_setup(client, room_id, options_per_person="", hide=False):
    data = {"kind": "food.restaurant", "options_per_person": options_per_person, "privacy_choices": "1"}
    if hide:
        data["hide_ideas"] = "1"
    response = client.post(f"/rooms/{room_id}/setup", data=data)
    assert response.status_code in (302, 303)


def own_idea_block(html):
    """The opening tag of the folded "Add a place by name" row and everything inside it."""
    start = html.index('<details class="own-idea"')
    return html[start:html.index("</details>", start)]


# --- Checks ----------------------------------------------------------------

def test_normal_case_has_no_typed_field_and_post_is_404(app, client):
    room_id = create_room(client)
    html = page(client, room_id)
    assert f'action="/rooms/{room_id}/options"' not in html
    assert FALLBACK_LINE not in html
    response = add_label(client, room_id, "Pizza place")
    assert response.status_code == 404
    assert options(app, room_id) == []


def test_failed_search_by_name_shows_the_typed_form(client, google):
    room_id = create_room(client)
    break_google(google)
    response = find(client, room_id)
    assert response.status_code == 503
    html = page(client, room_id)
    assert f'action="/rooms/{room_id}/options"' in html
    assert 'name="label"' in html
    assert "Add an option" in html
    assert "Add option" in html
    assert FALLBACK_LINE in html


def test_search_by_name_without_a_key_turns_the_fallback_on(app, client):
    app.config["GOOGLE_MAPS_API_KEY"] = None
    room_id = create_room(client)
    response = find(client, room_id)
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.get_data(as_text=True)
    assert FALLBACK_LINE in page(client, room_id)


@pytest.mark.parametrize("mode, route", [("nearby", "suggest"), ("surprise", "surprise")])
def test_failed_nearby_and_surprise_search_turn_it_on(client, google, mode, route):
    room_id = create_room(client, mode=mode)
    break_google(google)
    response = client.post(f"/rooms/{room_id}/{route}", data=search_form())
    assert response.status_code == 503
    html = page(client, room_id)
    assert FALLBACK_LINE in html
    assert f'action="/rooms/{room_id}/options"' in html


def test_typed_option_is_saved_with_its_author_and_redirects(app, client, google):
    room_id = create_room(client)
    turn_fallback_on(client, google, room_id)
    response = add_label(client, room_id, "Pizza place")
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")
    rows = options(app, room_id)
    assert [(row["source"], row["label"]) for row in rows] == [("manual", "Pizza place")]
    assert author_rows(app, room_id) == [(rows[0]["id"], participant_id(app, room_id, "Anna"))]
    assert "Pizza place" in page(client, room_id)


def test_rejected_typed_options_use_the_old_messages_and_save_nothing(app, client, google):
    room_id = create_room(client)
    turn_fallback_on(client, google, room_id)
    assert add_label(client, room_id, "Pizza place").status_code == 303
    before = options(app, room_id)

    for label, message in [
        ("   ", EMPTY_LABEL_MESSAGE),
        ("x" * 81, LONG_LABEL_MESSAGE),
        ("Pizza place", DUPLICATE_MESSAGE),
        ("PIZZA PLACE", DUPLICATE_MESSAGE),
    ]:
        response = add_label(client, room_id, label)
        assert response.status_code == 400, label
        assert message in response.get_data(as_text=True), label
    assert options(app, room_id) == before

    # Not joined: refused on the server.
    visitor = app.test_client()
    response = add_label(visitor, room_id, "Sushi")
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.get_data(as_text=True)
    assert options(app, room_id) == before

    # Over the room's options-per-person limit (F27): Anna already added one.
    save_setup(client, room_id, options_per_person="1")
    response = add_label(client, room_id, "Sushi")
    assert response.status_code == 400
    assert LIMIT_MESSAGE in response.get_data(as_text=True)
    assert options(app, room_id) == before

    # Room no longer collecting.
    set_room_status(app, room_id, "voting")
    response = add_label(client, room_id, "Tacos")
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.get_data(as_text=True)
    assert options(app, room_id) == before


def test_someone_elses_hidden_idea_gives_the_same_idea_message(app, client, google):
    room_id = create_room(client)
    save_setup(client, room_id, hide=True)
    ben = join(app, room_id, "Ben")
    add_typed_option(ben, room_id, "Pizza place")
    before = options(app, room_id)
    turn_fallback_on(client, google, room_id)

    response = add_label(client, room_id, "pizza place")
    assert response.status_code == 400
    assert SAME_IDEA_MESSAGE in response.get_data(as_text=True)
    assert options(app, room_id) == before


@pytest.mark.parametrize("mode", ["nearby", "surprise"])
def test_in_nearby_and_surprise_rooms_the_form_is_in_the_open_own_idea_block(client, google, mode):
    room_id = create_room(client, mode=mode)
    turn_fallback_on(client, google, room_id)
    html = page(client, room_id)
    block = own_idea_block(html)
    assert block.startswith('<details class="own-idea" open')
    assert f'action="/rooms/{room_id}/options"' in block
    assert FALLBACK_LINE in block


def test_fallback_ends_ten_minutes_after_the_last_failure(app, client, google):
    now = now_utc()
    places.note_google_unavailable(app, now)
    assert places.typed_fallback_active(app, now + timedelta(minutes=9, seconds=59))
    assert not places.typed_fallback_active(app, now + timedelta(minutes=10))

    room_id = create_room(client)
    places.note_google_unavailable(app, now_utc() - timedelta(minutes=10, seconds=1))
    html = page(client, room_id)
    assert f'action="/rooms/{room_id}/options"' not in html
    assert FALLBACK_LINE not in html
    assert add_label(client, room_id, "Pizza place").status_code == 404
    assert options(app, room_id) == []


def test_successful_search_by_name_turns_it_off_at_once(app, client, google):
    room_id = create_room(client)
    turn_fallback_on(client, google, room_id)
    assert FALLBACK_LINE in page(client, room_id)

    response = find(client, room_id)
    assert response.status_code == 200
    html = page(client, room_id)
    assert FALLBACK_LINE not in html
    assert f'action="/rooms/{room_id}/options"' not in html
    assert add_label(client, room_id, "Pizza place").status_code == 404
    assert options(app, room_id) == []


def test_state_belongs_to_the_app(app, tmp_path):
    now = now_utc()
    places.note_google_unavailable(app, now)
    assert places.typed_fallback_active(app, now)

    second = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": str(tmp_path / "second.sqlite")}
    )
    assert not places.typed_fallback_active(second, now)

    places.note_google_available(app)
    assert not places.typed_fallback_active(app, now)
