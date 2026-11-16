"""Tests for C5 – F13 "Been there": room page, route and lobby (specs/c5-been-there.md).

These tests never call Google: `requests.post` (Nearby Search) is replaced by a fake,
and the root conftest.py makes every other request fail, so the cards fall back.
The data C4's surprise search would save is written directly into the database,
so these tests do not depend on how C4 searches.
"""

import json

import pytest

from app import create_app
from app import db as database
from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
CENTRE = (38.737, -9.153)
FILTERS = {"category": "restaurant", "min_rating": None, "max_price_level": None, "requested_radius_m": 1000}
# What C4 would have saved: five places from five different sub-categories.
SURPRISE_PLACES = [
    ("thai_restaurant-0", "thai_restaurant"),
    ("greek_restaurant-0", "greek_restaurant"),
    ("italian_restaurant-0", "italian_restaurant"),
    ("korean_restaurant-0", "korean_restaurant"),
    ("vegan_restaurant-0", "vegan_restaurant"),
]
USED_TYPES = {category for _, category in SURPRISE_PLACES}
RESTAURANT_TYPES = {
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
}

NOT_JOINED_MESSAGE = "Please join the room before adding options."
UNKNOWN_OPTION_MESSAGE = "This option does not exist in this room."
WRONG_MODE_MESSAGE = "&#34;Been there&#34; is only available in a &#34;Surprise me&#34; room."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
MANUAL_OPTION_MESSAGE = "Only places from Google Maps can be replaced."
LIMIT_MESSAGE = "This room has already replaced 5 places. You can still add options yourself."
UNAVAILABLE_MESSAGE = (
    "Place suggestions are not available right now. You can still add options yourself."
)
NOTHING_NEW_MESSAGE = (
    "No other place was found nearby, so this place stays. You can still add options yourself."
)
REFUSED_MESSAGE = "Something went wrong while adding the option. Please try again."


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post: answers each search with 15 places named after the requested type."""

    def __init__(self):
        self.places_for = lambda place_type: [
            {"id": f"{place_type}-{number}"} for number in range(15)
        ]
        self.problem = None
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.problem, int):
            return FakeResponse(status_code=self.problem)
        if self.problem is not None:
            raise self.problem
        place_type = kwargs["json"]["includedTypes"][0]
        return FakeResponse(body={"places": self.places_for(place_type)})


@pytest.fixture(autouse=True)
def google(monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


@pytest.fixture(autouse=True)
def api_key(app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY


# --- Helpers ---------------------------------------------------------------

def create_room(client, mode="surprise", title="Friday surprise", nickname="Anna"):
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


def save_search(app, room_id, place_list=SURPRISE_PLACES, radius_m=1500, filters=None):
    """Store what a C4 search saves: the room's settings and one Google option per place."""
    run_sql(
        app,
        "UPDATE rooms SET search_center_lat = ?, search_center_lng = ?, radius_m = ?, filters = ?"
        " WHERE id = ?",
        (CENTRE[0], CENTRE[1], radius_m, json.dumps(filters or FILTERS), room_id),
    )
    return {
        place_id: add_google_option(app, room_id, place_id, category)
        for place_id, category in place_list
    }


def add_google_option(app, room_id, place_id, category, is_replaced=0):
    return run_sql(
        app,
        "INSERT INTO options (room_id, source, place_id, category, is_replaced)"
        " VALUES (?, 'google', ?, ?, ?)",
        (room_id, place_id, category, is_replaced),
    )


def add_manual_option(app, room_id, label):
    return run_sql(
        app, "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)", (room_id, label)
    )


def set_room_status(app, room_id, status):
    run_sql(app, "UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))


def all_options(app, room_id):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def active_options(app, room_id):
    return [row for row in all_options(app, room_id) if row["is_replaced"] == 0]


def option_row(app, option_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM options WHERE id = ?", (option_id,)).fetchone()


def snapshot(app):
    """Every row of every table that C5 could change, to prove nothing changed."""
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


def press(client, room_id, option_id):
    return client.post(f"/rooms/{room_id}/options/{option_id}/been-there")


def form_action(room_id, option_id):
    return f'action="/rooms/{room_id}/options/{option_id}/been-there"'


def page(client, room_id):
    return client.get(f"/rooms/{room_id}").data.decode()


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


@pytest.fixture
def room_id(client):
    """A "Surprise me" room created by "Anna" in the creator's browser (`client`)."""
    return create_room(client)


@pytest.fixture
def option_ids(app, room_id):
    """The five surprise places of the room, as {place id: option id}."""
    return save_search(app, room_id)


@pytest.fixture
def guest(app, room_id):
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


@pytest.fixture
def visitor(app):
    return app.test_client()


# --- Room page -------------------------------------------------------------

def test_participants_see_one_button_per_google_option(app, client, guest, room_id, option_ids):
    manual_id = add_manual_option(app, room_id, "Pizza at Luigi's")
    for browser in (client, guest):
        html = page(browser, room_id)
        for option_id in option_ids.values():
            assert html.count(form_action(room_id, option_id)) == 1
        assert form_action(room_id, manual_id) not in html
        assert html.count("/been-there") == 5
        assert "Been there" in html


def test_no_button_in_nearby_or_manual_rooms(app, client):
    for mode in ("nearby", "manual"):
        other_room = create_room(client, mode=mode)
        save_search(app, other_room)
        assert "/been-there" not in page(client, other_room)


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_no_button_once_the_room_is_not_collecting(app, client, room_id, option_ids, status):
    set_room_status(app, room_id, status)
    assert "/been-there" not in page(client, room_id)


def test_visitor_sees_no_button(visitor, room_id, option_ids):
    assert "/been-there" not in page(visitor, room_id)


def test_button_is_shown_even_if_filters_cannot_be_read(app, client, room_id, option_ids):
    run_sql(app, "UPDATE rooms SET filters = ? WHERE id = ?", ("not json {", room_id))
    assert page(client, room_id).count("/been-there") == 5


# --- Accepted --------------------------------------------------------------

def test_guest_replaces_a_place(app, guest, room_id, option_ids):
    old_id = option_ids["thai_restaurant-0"]
    response = press(guest, room_id, old_id)
    assert_redirects_to_room(response, room_id)

    assert option_row(app, old_id)["is_replaced"] == 1
    rows = all_options(app, room_id)
    assert len(rows) == 6
    new = rows[-1]
    assert new["id"] > old_id
    assert new["source"] == "google"
    assert new["label"] is None
    assert new["is_replaced"] == 0
    assert new["category"] == "thai_restaurant"
    assert new["place_id"].startswith("thai_restaurant-")
    assert new["place_id"] != "thai_restaurant-0"
    assert len(active_options(app, room_id)) == 5


def test_google_is_called_with_the_stored_search(app, guest, google, room_id):
    filters = {"category": "restaurant", "min_rating": 4.5, "max_price_level": 2, "requested_radius_m": 1000}
    ids = save_search(app, room_id, radius_m=2250, filters=filters)
    google.places_for = lambda place_type: [
        {"id": f"{place_type}-pricey", "rating": 4.9, "priceLevel": "PRICE_LEVEL_EXPENSIVE"},
        {"id": f"{place_type}-poor", "rating": 3.1, "priceLevel": "PRICE_LEVEL_MODERATE"},
        {"id": f"{place_type}-good", "rating": 4.6, "priceLevel": "PRICE_LEVEL_MODERATE"},
    ]
    assert_redirects_to_room(press(guest, room_id, ids["greek_restaurant-0"]), room_id)

    assert len(google.calls) == 1
    call = google.calls[0]
    assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert call["json"]["includedTypes"] == ["greek_restaurant"]
    circle = call["json"]["locationRestriction"]["circle"]
    assert circle["center"] == {"latitude": CENTRE[0], "longitude": CENTRE[1]}
    assert circle["radius"] == 2250
    assert all_options(app, room_id)[-1]["place_id"] == "greek_restaurant-good"


def test_every_participant_sees_the_new_place_instead(app, client, guest, room_id, option_ids):
    old_id = option_ids["korean_restaurant-0"]
    before = page(client, room_id).count("<article")
    press(guest, room_id, old_id)
    new_id = all_options(app, room_id)[-1]["id"]
    for browser in (client, guest):
        html = page(browser, room_id)
        assert html.count("<article") == before == 5
        assert form_action(room_id, old_id) not in html
        assert form_action(room_id, new_id) in html


def test_replaced_and_other_places_of_the_room_are_never_chosen(app, guest, google, room_id, option_ids):
    # Google lists the replaced place and another option of the room first.
    google.places_for = lambda place_type: [
        {"id": "thai_restaurant-0"},
        {"id": "greek_restaurant-0"},
        {"id": "thai_restaurant-new"},
    ]
    press(guest, room_id, option_ids["thai_restaurant-0"])
    assert all_options(app, room_id)[-1]["place_id"] == "thai_restaurant-new"


def test_other_kind_is_tried_when_the_same_kind_has_nothing_new(app, guest, google, room_id, option_ids):
    google.places_for = lambda place_type: (
        [{"id": "thai_restaurant-0"}]
        if place_type == "thai_restaurant"
        else [{"id": f"{place_type}-{number}"} for number in range(15)]
    )
    assert_redirects_to_room(press(guest, room_id, option_ids["thai_restaurant-0"]), room_id)

    assert len(google.calls) == 2
    new = all_options(app, room_id)[-1]
    assert new["category"] in RESTAURANT_TYPES - USED_TYPES
    assert new["place_id"].startswith(new["category"] + "-")
    assert google.calls[1]["json"]["includedTypes"] == [new["category"]]


def test_lobby_and_voting_count_only_active_options(app, client, guest, room_id, option_ids):
    old_id = option_ids["vegan_restaurant-0"]
    press(guest, room_id, old_id)

    assert "5 options" in client.get(f"/rooms/{room_id}/lobby").data.decode()
    start = client.post(f"/rooms/{room_id}/start")
    assert start.status_code in (302, 303)

    vote = guest.post(f"/rooms/{room_id}/vote", data={"option_id": str(old_id), "rating": "yes"})
    assert vote.status_code == 400
    assert UNKNOWN_OPTION_MESSAGE in vote.data.decode()


def test_only_the_place_id_is_stored(app, guest, room_id, option_ids, monkeypatch):
    # Even if Google's details could be loaded, no name is ever written to the database.
    def details(url, **kwargs):
        return FakeResponse(body={"displayName": {"text": "Secret Thai Kitchen"}})

    monkeypatch.setattr(places.requests, "get", details)
    press(guest, room_id, option_ids["thai_restaurant-0"])
    page(guest, room_id)

    stored = json.dumps(snapshot(app), default=str)
    assert "Secret Thai Kitchen" not in stored
    with app.app_context():
        option_columns = [row[1] for row in get_db().execute("PRAGMA table_info(options)")]
    assert option_columns == ["id", "room_id", "source", "label", "place_id", "category", "is_replaced"]


# --- Ignored ---------------------------------------------------------------

def test_pressing_again_for_a_replaced_option_is_ignored(app, client, guest, google, room_id, option_ids):
    old_id = option_ids["thai_restaurant-0"]
    press(guest, room_id, old_id)
    after_first = snapshot(app)
    calls_after_first = len(google.calls)

    response = press(client, room_id, old_id)
    assert_redirects_to_room(response, room_id)
    assert len(google.calls) == calls_after_first
    assert snapshot(app) == after_first


def test_losing_the_claim_is_ignored(app, guest, room_id, option_ids, monkeypatch):
    old_id = option_ids["thai_restaurant-0"]
    # Another request replaced it a moment ago, but this request read it before that.
    run_sql(app, "UPDATE options SET is_replaced = 1 WHERE id = ?", (old_id,))
    original_get_option = database.get_option

    def stale_get_option(*args, **kwargs):
        row = original_get_option(*args, **kwargs)
        return None if row is None else {**dict(row), "is_replaced": 0}

    monkeypatch.setattr(database, "get_option", stale_get_option)
    before = snapshot(app)

    response = press(guest, room_id, old_id)
    assert_redirects_to_room(response, room_id)
    assert snapshot(app) == before


# --- Rejected --------------------------------------------------------------

def test_nothing_new_found_keeps_the_place(app, guest, google, room_id, option_ids):
    google.places_for = lambda place_type: [{"id": place_id} for place_id in option_ids]
    before = snapshot(app)
    response = press(guest, room_id, option_ids["thai_restaurant-0"])
    assert response.status_code == 200
    assert NOTHING_NEW_MESSAGE in response.data.decode()
    assert snapshot(app) == before
    assert option_row(app, option_ids["thai_restaurant-0"])["is_replaced"] == 0


def test_google_error_changes_nothing(app, guest, google, room_id, option_ids):
    google.problem = 500
    before = snapshot(app)
    response = press(guest, room_id, option_ids["thai_restaurant-0"])
    html = response.data.decode()
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in html
    assert snapshot(app) == before
    assert html.count("<article") == 5
    assert f'action="/rooms/{room_id}/options"' in html


def test_without_key_google_is_not_called(app, guest, google, room_id, option_ids):
    app.config["GOOGLE_MAPS_API_KEY"] = None
    before = snapshot(app)
    response = press(guest, room_id, option_ids["thai_restaurant-0"])
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_room_without_stored_search_is_unavailable(app, guest, google, room_id):
    option_id = add_google_option(app, room_id, "thai_restaurant-0", "thai_restaurant")
    before = snapshot(app)
    response = press(guest, room_id, option_id)
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_limit_of_five_replacements(app, guest, google, room_id, option_ids):
    for number in range(5):
        add_google_option(app, room_id, f"old-{number}", "thai_restaurant", is_replaced=1)
    before = snapshot(app)
    response = press(guest, room_id, option_ids["thai_restaurant-0"])
    assert response.status_code == 400
    assert LIMIT_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_manual_option_cannot_be_replaced(app, guest, google, room_id, option_ids):
    manual_id = add_manual_option(app, room_id, "Pizza at Luigi's")
    before = snapshot(app)
    response = press(guest, room_id, manual_id)
    assert response.status_code == 400
    assert MANUAL_OPTION_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_option_of_another_room_or_unknown_id(app, client, guest, google, room_id, option_ids):
    other_room = create_room(app.test_client(), title="Other room", nickname="Cleo")
    other_ids = save_search(app, other_room, place_list=[("thai_restaurant-9", "thai_restaurant")])
    before = snapshot(app)
    for option_id in (other_ids["thai_restaurant-9"], 99999):
        response = press(guest, room_id, option_id)
        assert response.status_code == 400
        assert UNKNOWN_OPTION_MESSAGE in response.data.decode()
    assert press(guest, room_id, "abc").status_code == 404
    assert google.calls == []
    assert snapshot(app) == before


def test_nearby_room_is_rejected(app, client, google):
    nearby_room = create_room(client, mode="nearby")
    ids = save_search(app, nearby_room)
    before = snapshot(app)
    response = press(client, nearby_room, ids["thai_restaurant-0"])
    assert response.status_code == 400
    assert WRONG_MODE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_room_not_collecting_is_rejected(app, guest, google, room_id, option_ids, status):
    set_room_status(app, room_id, status)
    before = snapshot(app)
    response = press(guest, room_id, option_ids["thai_restaurant-0"])
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_visitor_and_participant_of_another_room_are_rejected(app, visitor, google, room_id, option_ids):
    stranger = app.test_client()
    create_room(stranger, title="Stranger's room", nickname="Dora")
    before = snapshot(app)
    for browser in (visitor, stranger):
        response = press(browser, room_id, option_ids["thai_restaurant-0"])
        assert response.status_code == 403
        assert NOT_JOINED_MESSAGE in response.data.decode()
    assert google.calls == []
    assert snapshot(app) == before


def test_unknown_room(guest, google, option_ids):
    assert press(guest, "no-such-room", option_ids["thai_restaurant-0"]).status_code == 404
    assert google.calls == []


def test_database_refusal_rolls_everything_back(app, guest, google, room_id, option_ids, monkeypatch):
    # Simulates another option of this room being replaced by the same new place a moment
    # earlier: the route does not know greek_restaurant-0 yet, Google offers only that one.
    original = database.get_room_place_ids

    def place_ids_without_greek(*args, **kwargs):
        return [place_id for place_id in original(*args, **kwargs) if place_id != "greek_restaurant-0"]

    monkeypatch.setattr(database, "get_room_place_ids", place_ids_without_greek)
    google.places_for = lambda place_type: [{"id": "thai_restaurant-0"}, {"id": "greek_restaurant-0"}]
    before = snapshot(app)

    response = press(guest, room_id, option_ids["thai_restaurant-0"])
    assert response.status_code == 400
    assert REFUSED_MESSAGE in response.data.decode()
    assert snapshot(app) == before
    assert option_row(app, option_ids["thai_restaurant-0"])["is_replaced"] == 0


# --- Security and persistence ---------------------------------------------

def test_api_key_never_appears_in_pages(app, guest, google, room_id, option_ids):
    responses = [press(guest, room_id, option_ids["thai_restaurant-0"])]
    responses.append(guest.get(f"/rooms/{room_id}"))
    google.problem = 500
    responses.append(press(guest, room_id, option_ids["greek_restaurant-0"]))
    for response in responses:
        assert FAKE_KEY not in response.data.decode()


def test_replacement_survives_restart(app, client, guest, room_id, option_ids):
    old_id = option_ids["italian_restaurant-0"]
    press(guest, room_id, old_id)
    saved_before = [tuple(row) for row in all_options(app, room_id)]
    new_id = saved_before[-1][0]

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
    assert html.count("<article") == 5
    assert form_action(room_id, old_id) not in html
    assert form_action(room_id, new_id) in html
