"""Tests for C2a – searching places for a "Places nearby" room (specs/c2-places-search.md).

These tests never call Google: `requests.post` is replaced by a fake for every test.
"""

import json

import pytest

from app import create_app
from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

NOT_JOINED_MESSAGE = "Please join the room before adding options."
NOT_CREATOR_MESSAGE = "Only the creator can search for places."
WRONG_MODE_MESSAGE = "Places can only be suggested in a &#34;Places nearby&#34; room."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
ALREADY_SUGGESTED_MESSAGE = "Places have already been suggested for this room."
UNAVAILABLE_MESSAGE = (
    "Place suggestions are not available right now. You can still add options yourself."
)
NO_RESULTS_MESSAGE = "No places found. Try a larger radius or fewer filters."
LOCATION_MESSAGE = "Please share your location so we can search nearby."
CATEGORY_MESSAGE = "Please choose a category."
GOOGLE_OPTION_TEXT = "Place from Google Maps"


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post: records every call and returns a prepared response."""

    def __init__(self, place_ids):
        self.response = FakeResponse(body={"places": [{"id": pid} for pid in place_ids]})
        self.error = None
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture(autouse=True)
def google(monkeypatch):
    """Every test gets a fake Google that finds three places. No test can reach the real API."""
    fake = FakeGoogle(["place-c", "place-a", "place-b"])
    monkeypatch.setattr(places.requests, "post", fake)
    return fake


@pytest.fixture(autouse=True)
def api_key(app):
    """Configure a fake key; tests about a missing key set it to an empty string."""
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY


# --- Helpers ---------------------------------------------------------------

def create_room(client, mode="nearby", title="Dinner on Friday", nickname="Anna"):
    """Create a room as its creator and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def search_form(**changes):
    form = {
        "category": "restaurant",
        "radius_m": "1000",
        "latitude": "38.7369876",
        "longitude": "-9.1534999",
        "min_rating": "",
        "max_price_level": "",
    }
    form.update(changes)
    return form


def suggest(client, room_id, **changes):
    return client.post(f"/rooms/{room_id}/suggest", data=search_form(**changes))


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


def options(app, room_id):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def option_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM options").fetchone()[0]


def room_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def set_room_status(app, room_id, status):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def assert_nothing_saved(app, room_id):
    assert option_count(app) == 0
    room = room_row(app, room_id)
    assert room["search_center_lat"] is None
    assert room["search_center_lng"] is None
    assert room["radius_m"] is None
    assert room["filters"] is None


def suggest_action(room_id):
    return f'action="/rooms/{room_id}/suggest"'


@pytest.fixture
def room_id(client):
    """A "Places nearby" room created by "Anna" in the creator's browser (`client`)."""
    return create_room(client)


@pytest.fixture
def guest(app, room_id):
    """A second browser that has joined the room as "Ben"."""
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


@pytest.fixture
def visitor(app):
    return app.test_client()


# --- Room page -------------------------------------------------------------

def test_creator_of_nearby_room_sees_search_form(client, room_id):
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert suggest_action(room_id) in html
    for field in ("category", "radius_m", "min_rating", "max_price_level"):
        assert f'name="{field}"' in html
    for value in ("restaurant", "bar", "cafe", "movie_theater"):
        assert f'value="{value}"' in html
    for value in ("500", "1000", "2000", "5000"):
        assert f'value="{value}"' in html
    assert 'type="hidden" name="latitude"' in html
    assert 'type="hidden" name="longitude"' in html
    assert "js/geolocation.js" in html


def test_guest_and_visitor_do_not_see_search_form(client, guest, visitor, room_id):
    assert suggest_action(room_id) not in guest.get(f"/rooms/{room_id}").data.decode()
    assert suggest_action(room_id) not in visitor.get(f"/rooms/{room_id}").data.decode()


@pytest.mark.parametrize("mode", ["manual", "surprise"])
def test_creator_of_other_modes_does_not_see_search_form(app, mode):
    browser = app.test_client()
    other_room = create_room(browser, mode=mode)
    assert suggest_action(other_room) not in browser.get(f"/rooms/{other_room}").data.decode()


# --- Accepted --------------------------------------------------------------

def test_valid_search_redirects_to_room_page(client, room_id):
    assert_redirects_to_room(suggest(client, room_id), room_id)


def test_places_are_stored_as_google_options_in_google_order(app, client, room_id):
    suggest(client, room_id, category="bar")
    stored = options(app, room_id)
    assert [row["place_id"] for row in stored] == ["place-c", "place-a", "place-b"]
    for row in stored:
        assert row["source"] == "google"
        assert row["category"] == "bar"
        assert row["label"] is None
        assert row["is_replaced"] == 0


def test_room_stores_rounded_centre_radius_and_filters(app, client, room_id):
    suggest(client, room_id, radius_m="2000", min_rating="4.5", max_price_level="3")
    room = room_row(app, room_id)
    assert room["search_center_lat"] == 38.737
    assert room["search_center_lng"] == -9.153
    assert room["radius_m"] == 2000
    assert json.loads(room["filters"]) == {
        "category": "restaurant",
        "min_rating": 4.5,
        "max_price_level": 3,
    }


def test_empty_filters_are_stored_as_null(app, client, room_id):
    suggest(client, room_id)
    assert json.loads(room_row(app, room_id)["filters"]) == {
        "category": "restaurant",
        "min_rating": None,
        "max_price_level": None,
    }


def test_google_is_called_with_key_and_cleaned_values(client, room_id, google):
    suggest(client, room_id, category="cafe", radius_m="500")
    assert len(google.calls) == 1
    call = google.calls[0]
    assert call["url"] == NEARBY_URL
    assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
    assert call["timeout"] == 5
    body = call["json"]
    assert body["includedTypes"] == ["cafe"]
    circle = body["locationRestriction"]["circle"]
    assert circle["center"] == {"latitude": 38.737, "longitude": -9.153}
    assert circle["radius"] == 500


def test_filters_are_applied_to_results(app, client, room_id, google):
    google.response = FakeResponse(
        body={
            "places": [
                {"id": "good", "rating": 4.6, "priceLevel": "PRICE_LEVEL_MODERATE"},
                {"id": "too-expensive", "rating": 4.8, "priceLevel": "PRICE_LEVEL_EXPENSIVE"},
                {"id": "too-low", "rating": 3.0, "priceLevel": "PRICE_LEVEL_INEXPENSIVE"},
            ]
        }
    )
    suggest(client, room_id, min_rating="4.0", max_price_level="2")
    assert [row["place_id"] for row in options(app, room_id)] == ["good"]


def test_after_search_everyone_sees_places_and_form_is_gone(client, guest, room_id):
    suggest(client, room_id)
    creator_html = client.get(f"/rooms/{room_id}").data.decode()
    guest_html = guest.get(f"/rooms/{room_id}").data.decode()
    assert creator_html.count(GOOGLE_OPTION_TEXT) == 3
    assert guest_html.count(GOOGLE_OPTION_TEXT) == 3
    assert suggest_action(room_id) not in creator_html


def test_manual_options_work_before_and_after_search(app, client, room_id):
    client.post(f"/rooms/{room_id}/options", data={"label": "Pizza place"})
    suggest(client, room_id)
    response = client.post(f"/rooms/{room_id}/options", data={"label": "Cinema"})
    assert_redirects_to_room(response, room_id)
    stored = options(app, room_id)
    assert [row["label"] for row in stored if row["source"] == "manual"] == ["Pizza place", "Cinema"]
    assert len([row for row in stored if row["source"] == "google"]) == 3
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert "Pizza place" in html
    assert "Cinema" in html


def test_only_place_id_is_stored_from_google(app, client, room_id, google):
    google.response = FakeResponse(
        body={
            "places": [
                {
                    "id": "place-x",
                    "rating": 4.4,
                    "priceLevel": "PRICE_LEVEL_MODERATE",
                    "displayName": {"text": "Secret Name Bistro"},
                }
            ]
        }
    )
    suggest(client, room_id)
    with app.app_context():
        db = get_db()
        for table in ("rooms", "options"):
            for row in db.execute(f"SELECT * FROM {table}").fetchall():
                values = " ".join(str(value) for value in tuple(row))
                assert "Secret Name Bistro" not in values
                assert "PRICE_LEVEL" not in values


# --- Rejected --------------------------------------------------------------

def test_no_places_found_shows_message_and_form(app, client, room_id, google):
    google.response = FakeResponse(body={})
    response = suggest(client, room_id)
    html = response.data.decode()
    assert response.status_code == 200
    assert NO_RESULTS_MESSAGE in html
    assert suggest_action(room_id) in html
    assert_nothing_saved(app, room_id)


def test_no_places_left_after_filters_shows_message(app, client, room_id, google):
    google.response = FakeResponse(body={"places": [{"id": "low", "rating": 2.0}]})
    response = suggest(client, room_id, min_rating="4.5")
    assert NO_RESULTS_MESSAGE in response.data.decode()
    assert_nothing_saved(app, room_id)


def test_google_error_shows_friendly_message(app, client, room_id, google):
    google.response = FakeResponse(status_code=500, body={"error": {}})
    response = suggest(client, room_id)
    html = response.data.decode()
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in html
    assert 'action="/rooms/' + room_id + '/options"' in html  # manual adding still possible
    assert_nothing_saved(app, room_id)


def test_google_timeout_shows_friendly_message(app, client, room_id, google):
    google.error = places.requests.Timeout("timed out")
    response = suggest(client, room_id)
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.data.decode()
    assert_nothing_saved(app, room_id)


def test_missing_api_key_does_not_call_google(app, client, room_id, google):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    response = suggest(client, room_id)
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_invalid_form_shows_messages_and_values(app, client, room_id, google):
    response = suggest(client, room_id, category="museum", latitude="", longitude="", radius_m="2000")
    html = response.data.decode()
    assert response.status_code == 400
    assert CATEGORY_MESSAGE in html
    assert LOCATION_MESSAGE in html
    assert suggest_action(room_id) in html
    # The entered radius is selected again.
    assert 'value="2000" selected' in html
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_second_search_is_rejected(app, client, room_id, google):
    suggest(client, room_id)
    before = [tuple(row) for row in options(app, room_id)]
    response = suggest(client, room_id, category="bar")
    assert response.status_code == 400
    assert ALREADY_SUGGESTED_MESSAGE in response.data.decode()
    assert len(google.calls) == 1
    assert [tuple(row) for row in options(app, room_id)] == before


def test_guest_cannot_search(app, guest, room_id, google):
    response = suggest(guest, room_id)
    assert response.status_code == 403
    assert NOT_CREATOR_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_visitor_cannot_search(app, visitor, room_id, google):
    response = suggest(visitor, room_id)
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_creator_of_another_room_cannot_search(app, room_id, google):
    other_browser = app.test_client()
    create_room(other_browser, title="Other room", nickname="Zoe")
    response = suggest(other_browser, room_id)
    assert response.status_code == 403
    assert google.calls == []
    assert_nothing_saved(app, room_id)


@pytest.mark.parametrize("mode", ["manual", "surprise"])
def test_other_modes_are_rejected(app, mode, google):
    browser = app.test_client()
    other_room = create_room(browser, mode=mode)
    response = suggest(browser, other_room)
    assert response.status_code == 400
    assert WRONG_MODE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, other_room)


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_rooms_not_collecting_are_rejected(app, client, room_id, google, status):
    set_room_status(app, room_id, status)
    response = suggest(client, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_unknown_room_is_404(client, google):
    response = client.post("/rooms/does-not-exist/suggest", data=search_form())
    assert response.status_code == 404
    assert google.calls == []


def test_database_refusal_shows_message_and_changes_nothing(app, client, room_id, monkeypatch):
    suggest(client, room_id)
    before_options = [tuple(row) for row in options(app, room_id)]
    before_room = tuple(room_row(app, room_id))

    # Simulate a race: the "already suggested" check passes although options exist,
    # so the insert breaks the UNIQUE (room_id, place_id) rule.
    from app import db

    monkeypatch.setattr(db, "has_google_options", lambda room_id: False)
    response = suggest(client, room_id, radius_m="5000")
    assert response.status_code == 400
    assert ALREADY_SUGGESTED_MESSAGE in response.data.decode()
    assert [tuple(row) for row in options(app, room_id)] == before_options
    assert tuple(room_row(app, room_id)) == before_room


# --- Security --------------------------------------------------------------

def test_api_key_never_appears_in_pages(app, client, room_id, google):
    pages = [client.get(f"/rooms/{room_id}").data.decode()]
    pages.append(suggest(client, room_id, category="museum").data.decode())
    google.response = FakeResponse(status_code=403, body={"error": {"message": FAKE_KEY}})
    pages.append(suggest(client, room_id).data.decode())
    google.response = FakeResponse(body={"places": [{"id": "p1"}]})
    pages.append(client.get(suggest(client, room_id).headers["Location"]).data.decode())
    for html in pages:
        assert FAKE_KEY not in html


# --- Persistence -----------------------------------------------------------

def test_places_and_search_settings_survive_restart(app, client, room_id):
    suggest(client, room_id, radius_m="2000")
    session_cookie = client.get_cookie("session")
    assert session_cookie is not None

    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
        }
    )
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)

    assert [row["place_id"] for row in options(restarted_app, room_id)] == [
        "place-c",
        "place-a",
        "place-b",
    ]
    assert room_row(restarted_app, room_id)["radius_m"] == 2000
    html = restarted_browser.get(f"/rooms/{room_id}").data.decode()
    assert html.count(GOOGLE_OPTION_TEXT) == 3
