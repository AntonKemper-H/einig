"""Tests for C6 – F23 find a place by name: room page, the two routes and the
interactions with C2a, C4 and C5 (specs/c6-find-place-by-name.md).

These tests never call Google: `requests.post` (Text Search and Nearby Search) is
replaced by a fake, and the root conftest.py makes every other request fail, so the
cards fall back to "Place from Google Maps".
"""

import json

import pytest
import requests

from app import create_app
from app import db as database
from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
CENTRE = (38.737, -9.153)

NOT_JOINED_MESSAGE = "Please join the room before adding options."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
EMPTY_NAME_MESSAGE = "Please enter a name to search for."
LONG_NAME_MESSAGE = "A name can be at most 80 characters."
LIMIT_MESSAGE = "You have already searched 10 times in this room. You can still add options yourself."
UNAVAILABLE_MESSAGE = (
    "Place suggestions are not available right now. You can still add options yourself."
)
NO_MATCHES_MESSAGE = "No places found with this name. You can still add it as your own option."
EXPIRED_MESSAGE = "This search result has expired. Please search again."
ALREADY_OPTION_MESSAGE = "This place is already an option."
PICKED_PLACE_MESSAGE = "Only places from the surprise search can be replaced."
NEAR_CENTRE_TEXT ="Places near the room&#39;s search area are shown first."

# What Google finds for "Trattoria Luigi" (names without quotes, so the HTML check is simple).
MATCHES = [
    {"id": "place-luigi-1", "displayName": {"text": "Trattoria Luigi"}, "formattedAddress": "Rua Augusta 10, Lisboa"},
    {"id": "place-luigi-2", "displayName": {"text": "Luigi Gelateria"}, "formattedAddress": "Avenida da Liberdade 5, Lisboa"},
    {"id": "place-luigi-3", "displayName": {"text": "Bar Luigi"}, "formattedAddress": "Rua do Carmo 3, Porto"},
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
    """Replaces requests.post: Text Search answers with .matches, Nearby Search with .nearby_ids."""

    def __init__(self):
        self.matches = list(MATCHES)
        self.nearby_ids = ["nearby-1", "nearby-2"]
        self.problem = None
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.problem, int):
            return FakeResponse(status_code=self.problem)
        if self.problem is not None:
            raise self.problem
        if url == TEXT_SEARCH_URL:
            return FakeResponse(body={"places": self.matches} if self.matches else {})
        return FakeResponse(body={"places": [{"id": place_id} for place_id in self.nearby_ids]})

    def text_searches(self):
        return [call for call in self.calls if call["url"] == TEXT_SEARCH_URL]


@pytest.fixture(autouse=True)
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


@pytest.fixture(autouse=True)
def api_key(app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY


# --- Helpers ---------------------------------------------------------------

def create_room(client, mode="manual", title="Dinner on Friday", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def run_sql(app, sql, params=()):
    with app.app_context():
        connection = get_db()
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor.lastrowid


def set_centre(app, room_id, radius_m=1000):
    """Store what a C2a/C4 search stores on the room (without options)."""
    run_sql(
        app,
        "UPDATE rooms SET search_center_lat = ?, search_center_lng = ?, radius_m = ?, filters = ?"
        " WHERE id = ?",
        (CENTRE[0], CENTRE[1], radius_m, json.dumps({"category": "restaurant"}), room_id),
    )


def add_google_option(app, room_id, place_id, category=None, is_replaced=0):
    return run_sql(
        app,
        "INSERT INTO options (room_id, source, place_id, category, is_replaced)"
        " VALUES (?, 'google', ?, ?, ?)",
        (room_id, place_id, category, is_replaced),
    )


def set_room_status(app, room_id, status):
    run_sql(app, "UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))


def all_options(app, room_id):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def author_rows(app, room_id):
    """The rows of A7's table option_authors for this room (PR #38)."""
    with app.app_context():
        return [
            tuple(row)
            for row in get_db().execute(
                "SELECT option_id, room_id, participant_id FROM option_authors"
                " WHERE room_id = ? ORDER BY option_id",
                (room_id,),
            )
        ]


def participant_id(app, room_id, nickname):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM participants WHERE room_id = ? AND nickname = ?", (room_id, nickname)
        ).fetchone()["id"]


def room_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def snapshot(app):
    """Every row of every table that C6 could change, to prove nothing changed."""
    with app.app_context():
        connection = get_db()
        queries = {
            "rooms": "SELECT * FROM rooms ORDER BY id",
            "options": "SELECT * FROM options ORDER BY id",
            "participants": "SELECT * FROM participants ORDER BY id",
            "votes": "SELECT * FROM votes ORDER BY id",
        }
        return {
            table: [tuple(row) for row in connection.execute(sql)] for table, sql in queries.items()
        }


def find(client, room_id, name="Trattoria Luigi", **location):
    return client.post(f"/rooms/{room_id}/find", data={"name": name, **location})


def add(client, room_id, place_id="place-luigi-1"):
    return client.post(f"/rooms/{room_id}/find/add", data={"place_id": place_id})


def page(client, room_id):
    return client.get(f"/rooms/{room_id}").data.decode()


def find_form(room_id):
    return f'action="/rooms/{room_id}/find"'


def add_form(room_id):
    return f'action="/rooms/{room_id}/find/add"'


def session_data(app, client):
    """The decoded signed session cookie of this browser."""
    cookie = client.get_cookie("session")
    if cookie is None:
        return {}
    return app.session_interface.get_signing_serializer(app).loads(cookie.value)


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


@pytest.fixture
def room_id(client):
    """A "manual" room created by "Anna" in the creator's browser (`client`)."""
    return create_room(client)


@pytest.fixture
def guest(app, room_id):
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


@pytest.fixture
def visitor(app):
    return app.test_client()


# --- Room page -------------------------------------------------------------

@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_creator_and_guest_see_find_form_in_every_mode(app, client, mode):
    room_id = create_room(client, mode=mode)
    guest = app.test_client()
    join(guest, room_id, "Ben")
    for browser in (client, guest):
        html = page(browser, room_id)
        assert find_form(room_id) in html
        assert 'name="name"' in html
        assert "Find on Google Maps" in html


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_no_find_form_for_visitors_or_after_collecting(app, client, visitor, room_id, status):
    assert find_form(room_id) not in page(visitor, room_id)
    assert find_form(room_id) in page(client, room_id)
    set_room_status(app, room_id, status)
    assert find_form(room_id) not in page(client, room_id)


def test_use_my_location_only_without_centre_and_without_other_search_form(app, client, guest, room_id):
    # Manual room without a centre: the find form offers the location.
    html = page(guest, room_id)
    assert 'id="use-location"' in html
    assert "js/geolocation.js" in html

    # A room with a centre: the centre is used, no location button.
    set_centre(app, room_id)
    html = page(guest, room_id)
    assert 'id="use-location"' not in html
    assert "js/geolocation.js" not in html
    assert NEAR_CENTRE_TEXT in html

    # Creator of a nearby room before the search: the ids must not appear twice.
    nearby_room = create_room(client, mode="nearby")
    html = page(client, nearby_room)
    assert find_form(nearby_room) in html
    assert html.count('id="use-location"') == 1
    assert html.count('id="latitude"') == 1


# --- Step 1: search --------------------------------------------------------

def test_step_one_shows_matches_without_saving(app, guest, room_id, google):
    before = snapshot(app)
    response = find(guest, room_id)
    html = response.data.decode()
    assert response.status_code == 200
    for result in MATCHES:
        assert result["displayName"]["text"] in html
        assert result["formattedAddress"] in html
        assert f'value="{result["id"]}"' in html
    assert html.count(add_form(room_id)) == len(MATCHES)
    assert html.count("Add this place") == len(MATCHES)
    # The manual add form is pre-filled with the typed name.
    assert 'value="Trattoria Luigi"' in html
    assert snapshot(app) == before


def test_step_one_calls_google_with_key_and_cleaned_name(guest, room_id, google):
    find(guest, room_id, name="  Trattoria Luigi  ")
    calls = google.text_searches()
    assert len(calls) == 1
    assert calls[0]["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert calls[0]["json"]["textQuery"] == "Trattoria Luigi"


def test_step_one_uses_room_centre_as_bias(app, guest, room_id, google):
    set_centre(app, room_id)
    find(guest, room_id, latitude="52.52", longitude="13.405")
    circle = google.text_searches()[0]["json"]["locationBias"]["circle"]
    assert circle["center"] == {"latitude": CENTRE[0], "longitude": CENTRE[1]}
    assert circle["radius"] == 5000


def test_step_one_uses_rounded_browser_location_without_storing_it(app, guest, room_id, google):
    before = room_row(app, room_id)
    find(guest, room_id, latitude="52.520071", longitude="13.404954")
    circle = google.text_searches()[0]["json"]["locationBias"]["circle"]
    assert circle["center"] == {"latitude": 52.52, "longitude": 13.405}
    after = room_row(app, room_id)
    assert tuple(after) == tuple(before)
    assert after["search_center_lat"] is None
    assert after["radius_m"] is None


@pytest.mark.parametrize(
    "location",
    [{}, {"latitude": "", "longitude": ""}, {"latitude": "abc", "longitude": "13.4"}, {"latitude": "52.5"}],
)
def test_step_one_without_valid_location_searches_without_bias(guest, room_id, google, location):
    response = find(guest, room_id, **location)
    assert response.status_code == 200
    assert "locationBias" not in google.text_searches()[0]["json"]


def test_session_holds_only_ids_of_shown_matches(app, guest, room_id):
    find(guest, room_id)
    data = session_data(app, guest)
    assert data["name_searches"][room_id]["place_ids"] == [result["id"] for result in MATCHES]
    as_text = json.dumps(data)
    for result in MATCHES:
        assert result["displayName"]["text"] not in as_text
        assert result["formattedAddress"] not in as_text


# --- Step 2: save ----------------------------------------------------------

def test_step_two_saves_google_option_and_forgets_matches(app, guest, room_id, google):
    find(guest, room_id)
    calls_before = len(google.calls)
    response = add(guest, room_id, "place-luigi-2")
    assert_redirects_to_room(response, room_id)
    assert len(google.calls) == calls_before  # step 2 never calls Google

    rows = all_options(app, room_id)
    assert len(rows) == 1
    option = rows[0]
    assert option["source"] == "google"
    assert option["place_id"] == "place-luigi-2"
    assert option["label"] is None
    assert option["category"] is None
    assert option["is_replaced"] == 0
    assert not session_data(app, guest)["name_searches"][room_id]["place_ids"]


def test_picked_place_is_shown_to_everyone_and_counted_in_lobby(app, client, guest, room_id):
    client.post(f"/rooms/{room_id}/options", data={"label": "Sushi bar"})
    find(guest, room_id)
    add(guest, room_id)
    for browser in (client, guest):
        html = page(browser, room_id)
        assert "Sushi bar" in html
        assert "Place from Google Maps" in html
        assert html.count("<article") == 1
    assert "2 options" in client.get(f"/rooms/{room_id}/lobby").data.decode()


def test_picker_is_stored_as_author_and_not_shown(app, client, guest, room_id):
    find(guest, room_id)
    add(guest, room_id)
    option_id = all_options(app, room_id)[0]["id"]
    assert author_rows(app, room_id) == [(option_id, room_id, participant_id(app, room_id, "Ben"))]
    # Who added an option is never shown to others.
    assert "Ben" not in page(client, room_id)


def test_picker_can_delete_the_place_and_other_guests_cannot(app, guest, room_id):
    find(guest, room_id)
    add(guest, room_id)
    option_id = all_options(app, room_id)[0]["id"]

    other_guest = app.test_client()
    join(other_guest, room_id, "Cleo")
    refused = other_guest.post(f"/rooms/{room_id}/options/{option_id}/delete")
    assert refused.status_code == 403
    assert len(all_options(app, room_id)) == 1

    deleted = guest.post(f"/rooms/{room_id}/options/{option_id}/delete")
    assert_redirects_to_room(deleted, room_id)
    assert all_options(app, room_id) == []
    assert author_rows(app, room_id) == []


def test_nothing_but_place_id_is_stored(app, guest, room_id):
    find(guest, room_id)
    add(guest, room_id)
    stored = json.dumps(snapshot(app), default=str)
    assert "place-luigi-1" in stored
    for result in MATCHES:
        assert result["displayName"]["text"] not in stored
        assert result["formattedAddress"] not in stored


@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_creator_and_guest_can_pick_in_every_mode(app, client, mode):
    room_id = create_room(client, mode=mode)
    guest = app.test_client()
    join(guest, room_id, "Ben")
    find(client, room_id)
    assert_redirects_to_room(add(client, room_id, "place-luigi-1"), room_id)
    find(guest, room_id)
    assert_redirects_to_room(add(guest, room_id, "place-luigi-2"), room_id)
    assert [row["place_id"] for row in all_options(app, room_id)] == ["place-luigi-1", "place-luigi-2"]


# --- Rejected: step 1 ------------------------------------------------------

def test_no_matches_shows_message_and_prefilled_manual_form(app, guest, room_id, google):
    google.matches = []
    before = snapshot(app)
    response = find(guest, room_id)
    html = response.data.decode()
    assert response.status_code == 200
    assert NO_MATCHES_MESSAGE in html
    assert 'value="Trattoria Luigi"' in html
    assert add_form(room_id) not in html
    assert snapshot(app) == before


@pytest.mark.parametrize("problem", [500, requests.ConnectionError("down")])
def test_google_error_is_friendly_and_saves_nothing(app, guest, room_id, google, problem):
    google.problem = problem
    before = snapshot(app)
    response = find(guest, room_id)
    html = response.data.decode()
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in html
    assert 'value="Trattoria Luigi"' in html
    assert snapshot(app) == before


def test_no_key_is_friendly_and_does_not_call_google(app, guest, room_id, google):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    response = find(guest, room_id)
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.data.decode()
    assert google.calls == []


@pytest.mark.parametrize("name, message", [("   ", EMPTY_NAME_MESSAGE), ("x" * 81, LONG_NAME_MESSAGE)])
def test_invalid_name_is_rejected_without_google(app, guest, room_id, google, name, message):
    before = snapshot(app)
    response = find(guest, room_id, name=name)
    assert response.status_code == 400
    assert message in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_eleventh_search_is_rejected_but_others_can_still_search(app, client, guest, room_id, google):
    for _ in range(10):
        assert find(guest, room_id).status_code == 200
    response = find(guest, room_id)
    assert response.status_code == 400
    assert LIMIT_MESSAGE in response.data.decode()
    assert len(google.text_searches()) == 10

    assert find(client, room_id).status_code == 200
    assert len(google.text_searches()) == 11


def test_step_one_rejects_visitor_and_other_room(app, client, visitor, room_id, google):
    other_room = create_room(client, title="Other room")
    stranger = app.test_client()
    join(stranger, other_room, "Cleo")
    for browser in (visitor, stranger):
        response = find(browser, room_id)
        assert response.status_code == 403
        assert NOT_JOINED_MESSAGE in response.data.decode()
    assert google.calls == []


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_step_one_rejects_room_that_is_not_collecting(app, guest, room_id, google, status):
    set_room_status(app, room_id, status)
    response = find(guest, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert google.calls == []


def test_step_one_unknown_room_is_404(client, google):
    assert find(client, "no-such-room").status_code == 404
    assert google.calls == []


# --- Rejected: step 2 ------------------------------------------------------

def assert_expired(app, response, room_id, expected_option_count=0):
    assert response.status_code == 400
    assert EXPIRED_MESSAGE in response.data.decode()
    assert len(all_options(app, room_id)) == expected_option_count


def test_step_two_without_search_is_expired(app, guest, room_id):
    assert_expired(app, add(guest, room_id), room_id)


def test_step_two_with_id_not_shown_is_expired(app, guest, room_id):
    find(guest, room_id)
    assert_expired(app, add(guest, room_id, "place-somewhere-else"), room_id)


def test_step_two_with_id_from_older_search_is_expired(app, guest, room_id, google):
    find(guest, room_id)
    google.matches = [{"id": "place-new", "displayName": {"text": "New"}, "formattedAddress": "Street"}]
    find(guest, room_id, name="Something else")
    assert_expired(app, add(guest, room_id, "place-luigi-1"), room_id)


def test_pressing_add_again_after_save_is_expired(app, guest, room_id):
    find(guest, room_id)
    add(guest, room_id, "place-luigi-1")
    assert_expired(app, add(guest, room_id, "place-luigi-2"), room_id, expected_option_count=1)


def test_matches_of_another_room_are_not_accepted(app, client, guest, room_id):
    other_room = create_room(client, title="Other room")
    find(client, other_room)
    assert_expired(app, add(client, room_id, "place-luigi-1"), room_id)


def test_garbage_in_session_is_expired(app, guest, room_id):
    with guest.session_transaction() as session:
        session["name_searches"] = {room_id: {"place_ids": "place-luigi-1", "count": "many"}}
    assert_expired(app, add(guest, room_id, "place-luigi-1"), room_id)


def test_place_that_is_already_active_option_is_rejected(app, guest, room_id):
    add_google_option(app, room_id, "place-luigi-1", category="restaurant")
    find(guest, room_id)
    before = snapshot(app)
    response = add(guest, room_id, "place-luigi-1")
    assert response.status_code == 400
    assert ALREADY_OPTION_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_place_that_was_replaced_is_rejected(app, client, guest):
    room_id = create_room(client, mode="surprise")
    join(guest, room_id, "Ben")
    add_google_option(app, room_id, "place-luigi-1", category="italian_restaurant", is_replaced=1)
    find(guest, room_id)
    before = snapshot(app)
    response = add(guest, room_id, "place-luigi-1")
    assert response.status_code == 400
    assert ALREADY_OPTION_MESSAGE in response.data.decode()
    assert snapshot(app) == before


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_step_two_rejects_room_that_is_not_collecting(app, guest, room_id, status):
    find(guest, room_id)
    set_room_status(app, room_id, status)
    before = snapshot(app)
    response = add(guest, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_step_two_rejects_visitor_and_other_room(app, client, visitor, room_id):
    other_room = create_room(client, title="Other room")
    stranger = app.test_client()
    join(stranger, other_room, "Cleo")
    find(stranger, other_room)
    for browser in (visitor, stranger):
        response = add(browser, room_id)
        assert response.status_code == 403
        assert NOT_JOINED_MESSAGE in response.data.decode()
    assert all_options(app, room_id) == []


def test_step_two_unknown_room_is_404(client):
    assert add(client, "no-such-room").status_code == 404


# --- Edge cases ------------------------------------------------------------

def test_room_starts_voting_just_before_insert(app, guest, room_id, monkeypatch):
    find(guest, room_id)
    set_room_status(app, room_id, "voting")
    real_get_room = database.get_room
    # The route still sees "collecting", as if voting started after its checks.
    monkeypatch.setattr(
        database, "get_room", lambda wanted: {**dict(real_get_room(wanted)), "status": "collecting"}
    )
    before = snapshot(app)
    response = add(guest, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_database_refuses_duplicate_insert(app, guest, room_id, monkeypatch):
    add_google_option(app, room_id, "place-luigi-1")
    find(guest, room_id)
    # The duplicate check misses it, as if another request added it a moment earlier.
    monkeypatch.setattr(database, "get_room_place_ids", lambda wanted: [])
    response = add(guest, room_id, "place-luigi-1")
    assert response.status_code == 400
    assert ALREADY_OPTION_MESSAGE in response.data.decode()
    assert len(all_options(app, room_id)) == 1
    assert author_rows(app, room_id) == []


def test_rejected_step_two_writes_no_author_row(app, guest, room_id, monkeypatch):
    add(guest, room_id)  # no search before: expired
    find(guest, room_id)
    add(guest, room_id, "place-somewhere-else")  # not among the matches
    add_google_option(app, room_id, "place-luigi-2", category="restaurant")
    add(guest, room_id, "place-luigi-2")  # already an option
    set_room_status(app, room_id, "voting")
    real_get_room = database.get_room
    monkeypatch.setattr(
        database, "get_room", lambda wanted: {**dict(real_get_room(wanted)), "status": "collecting"}
    )
    response = add(guest, room_id, "place-luigi-1")  # room started voting just before the insert
    assert response.status_code == 400
    assert [row["place_id"] for row in all_options(app, room_id)] == ["place-luigi-2"]
    assert author_rows(app, room_id) == []


# --- Interactions with C2a, C4, C5 -----------------------------------------

def test_nearby_search_still_works_after_a_pick(app, client, google):
    room_id = create_room(client, mode="nearby")
    guest = app.test_client()
    join(guest, room_id, "Ben")
    find(guest, room_id)
    add(guest, room_id, "place-luigi-1")

    assert 'action="/rooms/{}/suggest"'.format(room_id) in page(client, room_id)
    google.nearby_ids = ["nearby-1", "place-luigi-1", "nearby-2"]
    response = client.post(
        f"/rooms/{room_id}/suggest",
        data={
            "category": "restaurant",
            "radius_m": "1000",
            "latitude": str(CENTRE[0]),
            "longitude": str(CENTRE[1]),
            "min_rating": "",
            "max_price_level": "",
        },
    )
    assert_redirects_to_room(response, room_id)
    rows = all_options(app, room_id)
    assert [(row["place_id"], row["category"]) for row in rows] == [
        ("place-luigi-1", None),
        ("nearby-1", "restaurant"),
        ("nearby-2", "restaurant"),
    ]
    assert room_row(app, room_id)["radius_m"] == 1000


def test_picked_place_in_surprise_room_has_no_been_there_form(app, client, guest):
    room_id = create_room(client, mode="surprise")
    join(guest, room_id, "Ben")
    set_centre(app, room_id)
    surprise_id = add_google_option(app, room_id, "thai-1", category="thai_restaurant")
    find(guest, room_id)
    add(guest, room_id, "place-luigi-1")
    picked_id = all_options(app, room_id)[-1]["id"]

    html = page(guest, room_id)
    assert f'action="/rooms/{room_id}/options/{surprise_id}/been-there"' in html
    assert f'action="/rooms/{room_id}/options/{picked_id}/been-there"' not in html


def test_been_there_route_rejects_picked_place(app, client, guest, google):
    room_id = create_room(client, mode="surprise")
    join(guest, room_id, "Ben")
    set_centre(app, room_id)
    surprise_id = add_google_option(app, room_id, "thai-1", category="thai_restaurant")
    # Stored directly as C6 stores a picked place (no category), so this test checks only the C5 route.
    picked_id = add_google_option(app, room_id, "place-luigi-1")

    calls_before = len(google.calls)
    before = snapshot(app)
    response = guest.post(f"/rooms/{room_id}/options/{picked_id}/been-there")
    assert response.status_code == 400
    assert PICKED_PLACE_MESSAGE in response.data.decode()
    assert len(google.calls) == calls_before
    assert snapshot(app) == before

    # The surprise place of the same room can still be replaced.
    response = guest.post(f"/rooms/{room_id}/options/{surprise_id}/been-there")
    assert_redirects_to_room(response, room_id)
    replaced = [row["place_id"] for row in all_options(app, room_id) if row["is_replaced"]]
    assert replaced == ["thai-1"]


# --- Security and persistence ----------------------------------------------

def test_api_key_never_appears_in_any_page(app, guest, room_id, google):
    form_page = page(guest, room_id)
    matches = find(guest, room_id)
    google.problem = 500
    error = find(guest, room_id)
    assert find_form(room_id) in form_page
    assert matches.status_code == 200
    assert error.status_code == 503
    for html in (form_page, matches.data.decode(), error.data.decode()):
        assert FAKE_KEY not in html


def test_picked_option_survives_restart(app, client, guest, room_id):
    find(guest, room_id)
    add(guest, room_id)
    saved_before = [tuple(row) for row in all_options(app, room_id)]

    restarted = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
            "GOOGLE_MAPS_API_KEY": FAKE_KEY,
        }
    )
    assert [tuple(row) for row in all_options(restarted, room_id)] == saved_before
    browser = restarted.test_client()
    browser.set_cookie("session", client.get_cookie("session").value)
    html = page(browser, room_id)
    assert html.count("<article") == 1
    assert "Place from Google Maps" in html
