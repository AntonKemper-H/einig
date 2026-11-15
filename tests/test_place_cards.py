"""Tests for C2b – place cards on the room page and the photo proxy (specs/c2b-place-cards.md).

These tests never call Google: `requests.get` is replaced by a fake, and the
root conftest.py makes any other real request fail.
"""

import pytest

from app import create_app
from app.db import get_db
from app.services import places

FAKE_KEY = "fake-key-for-tests-0123456789"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
FALLBACK_NAME = "Place from Google Maps"
DETAILS_MISSING = "Details are not available right now."
PHOTO_UNAVAILABLE = "Photo not available."
CENTRE = (38.737, -9.153)


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None, content=b"", content_type="application/json"):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGet:
    """Replaces requests.get: answers by URL, records every call."""

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

    def urls(self):
        return [call["url"] for call in self.calls]


def place(place_id, name, rating=4.5, price="PRICE_LEVEL_MODERATE", location=(38.740, -9.153),
          author_uri="https://maps.google.com/maria", with_photo=True):
    """A Place Details answer. Pass None to leave a field out."""
    body = {"displayName": {"text": name}}
    if rating is not None:
        body["rating"] = rating
    if price is not None:
        body["priceLevel"] = price
    if location is not None:
        body["location"] = {"latitude": location[0], "longitude": location[1]}
    if with_photo:
        body["photos"] = [
            {
                "name": f"places/{place_id}/photos/photo-ref-1",
                "authorAttributions": [{"displayName": "Maria Silva", "uri": author_uri}],
            }
        ]
    return body


@pytest.fixture(autouse=True)
def google(monkeypatch):
    """Fake Google that knows two places: Pizza Roma (place-a) and Sushi Bar (place-b)."""
    fake = FakeGet()
    fake.responses[DETAILS_URL + "place-a"] = FakeResponse(body=place("place-a", "Pizza Roma"))
    fake.responses[DETAILS_URL + "place-b"] = FakeResponse(body=place("place-b", "Sushi Bar"))
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


@pytest.fixture(autouse=True)
def api_key(app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY


# --- Helpers ---------------------------------------------------------------

def create_room(client, mode="nearby", title="Dinner on Friday", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_places(app, room_id, place_ids, centre=CENTRE):
    """Store Google options and the search centre directly, as C2a's search would."""
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE rooms SET search_center_lat = ?, search_center_lng = ?, radius_m = 1000"
            " WHERE id = ?",
            (centre[0], centre[1], room_id),
        )
        for place_id in place_ids:
            db.execute(
                "INSERT INTO options (room_id, source, place_id, category)"
                " VALUES (?, 'google', ?, 'restaurant')",
                (room_id, place_id),
            )
        db.commit()


def add_manual(client, room_id, label):
    response = client.post(f"/rooms/{room_id}/options", data={"label": label})
    assert response.status_code in (302, 303)


def page(client, room_id):
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    return response.data.decode()


def snapshot(app):
    with app.app_context():
        db = get_db()
        return {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
            for table in ("rooms", "participants", "options", "votes", "vetoes")
        }


@pytest.fixture
def room_id(app, client):
    """A "Places nearby" room by Anna (`client`) with Pizza Roma and Sushi Bar."""
    room = create_room(client)
    add_places(app, room, ["place-a", "place-b"])
    return room


@pytest.fixture
def guest(app, room_id):
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


# --- Room page -------------------------------------------------------------

def test_creator_and_guest_see_full_cards(client, guest, room_id):
    for browser in (client, guest):
        html = page(browser, room_id)
        assert "Pizza Roma" in html
        assert "Sushi Bar" in html
        assert '<img src="/photo/places/place-a/photos/photo-ref-1"' in html
        assert 'alt="Photo of Pizza Roma"' in html
        assert "Photo:" in html
        assert '<a href="https://maps.google.com/maria"' in html
        assert "Maria Silva" in html
        assert "4.5 ★ · €€ · 330 m" in html
        assert "Google Maps" in html
        assert FALLBACK_NAME not in html


def test_manual_options_keep_label_and_cause_no_calls(client, room_id, google):
    add_manual(client, room_id, "Cinema")
    google.calls.clear()
    html = page(client, room_id)
    assert "Cinema" in html
    assert sorted(google.urls()) == [DETAILS_URL + "place-a", DETAILS_URL + "place-b"]


def test_place_without_photo_rating_price_or_location(client, room_id, google):
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(
        body=place("place-a", "Plain Place", rating=None, price=None, location=None, with_photo=False)
    )
    html = page(client, room_id)
    assert "Plain Place" in html
    assert "/photo/places/place-a/" not in html
    assert "Photo of Plain Place" not in html
    assert " ·  · " not in html
    assert "· ·" not in html


def test_google_error_for_one_place_falls_back_only_there(client, room_id, google):
    google.responses[DETAILS_URL + "place-b"] = FakeResponse(status_code=500, body={})
    html = page(client, room_id)
    assert "Pizza Roma" in html
    assert html.count(FALLBACK_NAME) == 1
    assert DETAILS_MISSING in html


def test_without_key_every_place_falls_back_and_google_is_not_called(app, client, room_id, google):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    html = page(client, room_id)
    assert html.count(FALLBACK_NAME) == 2  # exactly once per Google option
    assert html.count(DETAILS_MISSING) == 2
    assert google.calls == []


def test_google_timeout_on_first_place_stops_further_calls(client, room_id, google):
    google.responses[DETAILS_URL + "place-a"] = places.requests.Timeout("timed out")
    html = page(client, room_id)  # status 200 is checked in page()
    assert len(google.calls) == 1
    assert html.count(FALLBACK_NAME) == 2
    assert html.count(DETAILS_MISSING) == 2
    assert "Pizza Roma" not in html
    assert "Sushi Bar" not in html


def test_visitor_page_does_not_call_google(app, room_id, google):
    visitor = app.test_client()
    html = page(visitor, room_id)
    assert "Pizza Roma" not in html
    assert google.calls == []


def test_google_content_is_shown_safely(client, room_id, google):
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(
        body=place("place-a", "<script>alert(1)</script>", author_uri="javascript:alert(1)")
    )
    html = page(client, room_id)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "javascript:" not in html


def test_viewing_the_page_writes_nothing(app, client, room_id):
    before = snapshot(app)
    page(client, room_id)
    assert snapshot(app) == before


def test_api_key_never_appears_in_room_page(client, room_id):
    assert FAKE_KEY not in page(client, room_id)


# --- Photo proxy -----------------------------------------------------------

PHOTO_PATH = "/photo/places/place-a/photos/photo-ref-1"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/places/place-a/photos/photo-ref-1/media"


def test_photo_proxy_returns_image_for_participant(client, room_id, google):
    google.responses[PHOTO_MEDIA_URL] = FakeResponse(content=b"\xff\xd8jpeg-bytes", content_type="image/jpeg")
    response = client.get(PHOTO_PATH)
    assert response.status_code == 200
    assert response.data == b"\xff\xd8jpeg-bytes"
    assert response.headers["Content-Type"] == "image/jpeg"
    assert response.headers["Cache-Control"] == "private, max-age=600"
    assert FAKE_KEY.encode() not in response.data
    assert all(FAKE_KEY not in value for value in response.headers.values())
    assert google.urls() == [PHOTO_MEDIA_URL]
    assert google.calls[0]["params"] == {"maxWidthPx": 400}


@pytest.mark.parametrize(
    "path",
    [
        "/photo/places/place-a/photos/../../secret",
        "/photo/places/place-a/other/photo-ref-1",
        "/photo/places/place-a",
        "/photo/https://evil.example/x.jpg",
    ],
)
def test_photo_proxy_rejects_malformed_names(client, room_id, google, path):
    assert client.get(path).status_code == 404
    assert google.calls == []


def test_photo_proxy_rejects_visitor(app, room_id, google):
    visitor = app.test_client()
    assert visitor.get(PHOTO_PATH).status_code == 404
    assert google.calls == []


def test_photo_proxy_rejects_participant_of_another_room(app, room_id, google):
    other = app.test_client()
    create_room(other, title="Other room", nickname="Zoe")
    assert other.get(PHOTO_PATH).status_code == 404
    assert google.calls == []


def test_photo_proxy_rejects_place_not_in_joined_room(client, room_id, google):
    response = client.get("/photo/places/place-z/photos/photo-ref-1")
    assert response.status_code == 404
    assert google.calls == []


def test_photo_proxy_without_key(app, client, room_id, google):
    app.config["GOOGLE_MAPS_API_KEY"] = ""
    response = client.get(PHOTO_PATH)
    assert response.status_code == 503
    assert response.data.decode() == PHOTO_UNAVAILABLE
    assert google.calls == []


@pytest.mark.parametrize(
    "google_answer",
    [
        FakeResponse(status_code=403, body={"error": {}}),
        FakeResponse(content=b"<html>", content_type="text/html"),
    ],
    ids=["error-status", "not-an-image"],
)
def test_photo_proxy_google_error(client, room_id, google, google_answer):
    google.responses[PHOTO_MEDIA_URL] = google_answer
    response = client.get(PHOTO_PATH)
    assert response.status_code == 503
    assert response.data.decode() == PHOTO_UNAVAILABLE


# --- Persistence -----------------------------------------------------------

def test_cards_after_restart(app, client, room_id, google):
    session_cookie = client.get_cookie("session")
    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
            "GOOGLE_MAPS_API_KEY": FAKE_KEY,
        }
    )
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)
    html = page(restarted_browser, room_id)
    assert "Pizza Roma" in html
    assert "Sushi Bar" in html
