"""Tests for C4 – F12 Surprise mode: room page and route (specs/c4-surprise-mode.md).

These tests never call Google: `requests.post` (Nearby Search) is replaced by a fake,
and the root conftest.py makes every other request fail, so the cards fall back.
"""

import json
import re

import pytest

from app import create_app
from app.db import get_db
from app.services import places
from typed_option import add_typed_option

FAKE_KEY = "fake-key-for-tests-0123456789"

NOT_JOINED_MESSAGE = "Please join the room before adding options."
NOT_CREATOR_MESSAGE = "Only the creator can search for places."
WRONG_MODE_MESSAGE = "Surprise places can only be suggested in a &#34;Surprise me&#34; room."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
ALREADY_SUGGESTED_MESSAGE = "Places have already been suggested for this room."
UNAVAILABLE_MESSAGE = (
    "Place suggestions are not available right now."
)
NO_RESULTS_MESSAGE = "No places found. Try a larger radius or fewer filters."
CATEGORY_MESSAGE = "Please choose a category."
LOCATION_MESSAGE = "Please share your location so we can search nearby."
WIDENED_TEXT = "Only a few places were found nearby, so the search area was widened to"
FALLBACK_NAME = "Place from Google Maps"

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


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post: answers each search with places named after the requested type."""

    def __init__(self):
        self.places_for = lambda place_type, radius: [
            {"id": f"{place_type}-{self.prefix}{number}"} for number in range(15)
        ]
        self.prefix = ""
        self.error = None
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        body = kwargs["json"]
        place_type = body["includedTypes"][0]
        radius = body["locationRestriction"]["circle"]["radius"]
        return FakeResponse(body={"places": self.places_for(place_type, radius)})


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


def surprise_form(**changes):
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


def search(client, room_id, **changes):
    return client.post(f"/rooms/{room_id}/surprise", data=surprise_form(**changes))


def surprise_action(room_id):
    return f'action="/rooms/{room_id}/surprise"'


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


def is_selected(html, select_name, value):
    """True if the <select name=select_name> has an <option value=value> marked as selected."""
    select = re.search(rf'<select[^>]*name="{select_name}"[^>]*>(.*?)</select>', html, re.DOTALL)
    assert select is not None, f"no <select> named {select_name}"
    for option_tag in re.findall(r"<option\b[^>]*>", select.group(1)):
        if f'value="{value}"' in option_tag and re.search(r"\bselected\b", option_tag):
            return True
    return False


def few_then_many(place_type, radius):
    """One place in total at 1000 m (too few), plenty at 1500 m."""
    if radius < 1500:
        return [{"id": "lonely-place"}]
    return [{"id": f"{place_type}-{number}"} for number in range(15)]


@pytest.fixture
def room_id(client):
    """A "Surprise me" room created by "Anna" in the creator's browser (`client`)."""
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

def test_creator_of_surprise_room_sees_surprise_form(client, room_id):
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert surprise_action(room_id) in html
    assert "Surprise us" in html
    for field in ("category", "radius_m", "min_rating", "max_price_level"):
        assert f'name="{field}"' in html
    for value in ("restaurant", "bar", "cafe"):
        assert f'value="{value}"' in html
    assert 'value="movie_theater"' not in html
    for value in ("500", "1000", "2000", "5000"):
        assert f'value="{value}"' in html
    assert 'type="hidden" name="latitude"' in html
    assert 'type="hidden" name="longitude"' in html
    assert "js/geolocation.js" in html
    assert f'action="/rooms/{room_id}/suggest"' not in html


def test_guest_and_visitor_do_not_see_surprise_form(guest, visitor, room_id):
    assert surprise_action(room_id) not in guest.get(f"/rooms/{room_id}").data.decode()
    assert surprise_action(room_id) not in visitor.get(f"/rooms/{room_id}").data.decode()


@pytest.mark.parametrize("mode", ["manual", "nearby"])
def test_creator_of_other_modes_does_not_see_surprise_form(client, mode):
    other_room = create_room(client, mode=mode)
    assert surprise_action(other_room) not in client.get(f"/rooms/{other_room}").data.decode()


# --- Accepted --------------------------------------------------------------

def test_valid_search_redirects_to_room(client, room_id):
    assert_redirects_to_room(search(client, room_id), room_id)


def test_valid_search_saves_five_varied_google_options(app, client, room_id):
    search(client, room_id)
    saved = options(app, room_id)
    assert len(saved) == 5
    for option in saved:
        assert option["source"] == "google"
        assert option["label"] is None
        assert option["is_replaced"] == 0
        assert option["category"] in RESTAURANT_TYPES
        # The fake names each place after the type it was searched with.
        assert option["place_id"].startswith(option["category"] + "-")
    assert len({option["category"] for option in saved}) >= 4


def test_valid_search_stores_room_settings(app, client, google, room_id):
    # The places need a rating and a price level, or the filters below would drop them all.
    google.places_for = lambda place_type, radius: [
        {"id": f"{place_type}-{number}", "rating": 4.6, "priceLevel": "PRICE_LEVEL_MODERATE"}
        for number in range(15)
    ]
    search(client, room_id, radius_m="2000", min_rating="4.5", max_price_level="3")
    room = room_row(app, room_id)
    assert room["search_center_lat"] == 38.737
    assert room["search_center_lng"] == -9.153
    assert room["radius_m"] == 2000
    assert json.loads(room["filters"]) == {
        "category": "restaurant",
        "min_rating": 4.5,
        "max_price_level": 3,
        "requested_radius_m": 2000,
    }


def test_coordinates_rounded_and_key_sent(client, google, room_id):
    search(client, room_id, latitude="52.5200066", longitude="13.4049540")
    assert len(google.calls) == 4
    for call in google.calls:
        assert call["headers"]["X-Goog-Api-Key"] == FAKE_KEY
        center = call["json"]["locationRestriction"]["circle"]["center"]
        assert center == {"latitude": 52.52, "longitude": 13.405}


def test_after_search_everyone_sees_cards_and_form_is_gone(client, guest, room_id):
    search(client, room_id)
    for browser in (client, guest):
        html = browser.get(f"/rooms/{room_id}").data.decode()
        # No details can be loaded in tests (no network), so each card shows the fallback name once.
        assert html.count(FALLBACK_NAME) == 5
        assert surprise_action(room_id) not in html
        assert WIDENED_TEXT not in html


def test_widened_search_is_stored_and_shown_to_everyone(app, client, guest, google, room_id):
    google.places_for = few_then_many
    assert_redirects_to_room(search(client, room_id, radius_m="1000"), room_id)
    room = room_row(app, room_id)
    assert room["radius_m"] == 1500
    assert json.loads(room["filters"])["requested_radius_m"] == 1000
    assert len(options(app, room_id)) == 5
    for browser in (client, guest):
        html = browser.get(f"/rooms/{room_id}").data.decode()
        assert f"{WIDENED_TEXT} 1.5 km." in html


def test_widening_text_not_shown_to_visitor(client, visitor, google, room_id):
    google.places_for = few_then_many
    search(client, room_id)
    assert WIDENED_TEXT not in visitor.get(f"/rooms/{room_id}").data.decode()


def test_manual_options_still_work_after_search(app, client, room_id):
    add_typed_option(client, room_id, "Pizza at home")
    search(client, room_id)
    response = add_typed_option(client, room_id, "Picnic")
    assert response.status_code in (302, 303)
    labels = [option["label"] for option in options(app, room_id) if option["source"] == "manual"]
    assert labels == ["Pizza at home", "Picnic"]
    assert len(options(app, room_id)) == 7


def test_only_place_id_is_stored(app, client, google, room_id):
    google.places_for = lambda place_type, radius: [
        {"id": f"{place_type}-{n}", "displayName": {"text": "Secret Name"}, "rating": 4.9}
        for n in range(3)
    ]
    search(client, room_id)
    with app.app_context():
        db = get_db()
        for table in ("rooms", "options"):
            for row in db.execute(f"SELECT * FROM {table}").fetchall():
                assert "Secret Name" not in " ".join(str(value) for value in tuple(row))


# --- Rejected --------------------------------------------------------------

def test_no_places_even_after_widening(app, client, google, room_id):
    google.places_for = lambda place_type, radius: []
    response = search(client, room_id)
    assert response.status_code == 200
    html = response.data.decode()
    assert NO_RESULTS_MESSAGE in html
    assert surprise_action(room_id) in html
    assert len(google.calls) == 16
    assert_nothing_saved(app, room_id)


def test_google_error_shows_friendly_message(app, client, google, room_id):
    google.error = places.requests.Timeout("too slow")
    response = search(client, room_id)
    assert response.status_code == 503
    html = response.data.decode()
    assert UNAVAILABLE_MESSAGE in html
    assert f'action="/rooms/{room_id}/options"' not in html  # E1: no typed options any more
    assert len(google.calls) == 1
    assert_nothing_saved(app, room_id)


def test_no_api_key(app, client, google, room_id):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    response = search(client, room_id)
    assert response.status_code == 503
    assert UNAVAILABLE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_invalid_form(app, client, google, room_id):
    response = search(client, room_id, category="movie_theater", latitude="", radius_m="2000")
    assert response.status_code == 400
    html = response.data.decode()
    assert CATEGORY_MESSAGE in html
    assert LOCATION_MESSAGE in html
    assert surprise_action(room_id) in html
    assert is_selected(html, "radius_m", "2000")
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_second_search_rejected(app, client, google, room_id):
    search(client, room_id)
    before = [tuple(row) for row in options(app, room_id)]
    room_before = tuple(room_row(app, room_id))
    google.calls.clear()
    response = search(client, room_id, radius_m="5000")
    assert response.status_code == 400
    assert ALREADY_SUGGESTED_MESSAGE in response.data.decode()
    assert google.calls == []
    assert [tuple(row) for row in options(app, room_id)] == before
    assert tuple(room_row(app, room_id)) == room_before


def test_guest_cannot_search(app, guest, google, room_id):
    response = search(guest, room_id)
    assert response.status_code == 403
    assert NOT_CREATOR_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_visitor_and_other_room_participant_cannot_search(app, client, visitor, google, room_id):
    response = search(visitor, room_id)
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.data.decode()

    other_browser = app.test_client()
    create_room(other_browser, title="Other room", nickname="Carla")
    response = search(other_browser, room_id)
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.data.decode()

    assert google.calls == []
    assert_nothing_saved(app, room_id)


@pytest.mark.parametrize("mode", ["manual", "nearby"])
def test_other_modes_rejected(app, client, google, mode):
    other_room = create_room(client, mode=mode)
    response = search(client, other_room)
    assert response.status_code == 400
    assert WRONG_MODE_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, other_room)


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_room_not_collecting_rejected(app, client, google, room_id, status):
    set_room_status(app, room_id, status)
    response = search(client, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert google.calls == []
    assert_nothing_saved(app, room_id)


def test_unknown_room(client, google):
    response = search(client, "no-such-room")
    assert response.status_code == 404
    assert google.calls == []


# --- Edge cases ------------------------------------------------------------

def test_second_search_passing_check_is_stopped_by_claim(app, client, google, room_id, monkeypatch):
    from app import db

    search(client, room_id)
    before = [tuple(row) for row in options(app, room_id)]
    room_before = tuple(room_row(app, room_id))

    monkeypatch.setattr(db, "has_google_options", lambda room_id: False)
    google.prefix = "second-"
    response = search(client, room_id, radius_m="5000")
    assert response.status_code == 400
    assert ALREADY_SUGGESTED_MESSAGE in response.data.decode()
    assert [tuple(row) for row in options(app, room_id)] == before
    assert tuple(room_row(app, room_id)) == room_before


# --- Security --------------------------------------------------------------

def test_api_key_never_in_page(app, client, google, room_id):
    pages = [client.get(f"/rooms/{room_id}").data.decode()]
    pages.append(search(client, room_id, latitude="").data.decode())
    google.error = places.requests.ConnectionError("down")
    pages.append(search(client, room_id).data.decode())
    google.error = None
    search(client, room_id)
    pages.append(client.get(f"/rooms/{room_id}").data.decode())
    for html in pages:
        assert FAKE_KEY not in html


# --- Persistence -----------------------------------------------------------

def test_search_survives_restart(app, client, google, room_id):
    google.places_for = few_then_many
    search(client, room_id)
    saved_before = [tuple(row) for row in options(app, room_id)]
    room_before = tuple(room_row(app, room_id))

    restarted = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
            "GOOGLE_MAPS_API_KEY": FAKE_KEY,
        }
    )
    assert [tuple(row) for row in options(restarted, room_id)] == saved_before
    assert tuple(room_row(restarted, room_id)) == room_before

    browser = restarted.test_client()
    browser.set_cookie("session", client.get_cookie("session").value)
    html = browser.get(f"/rooms/{room_id}").data.decode()
    assert html.count(FALLBACK_NAME) == 5
    assert f"{WIDENED_TEXT} 1.5 km." in html
