"""Tests for C3 – F9 Map and route to the winner (specs/c3-winner-map.md).

These tests never call Google: `requests.get` is replaced by a fake, and the
root conftest.py makes any other real request fail. The result page itself
comes from B3 (specs/b3-result.md); the rooms here are closed directly in the
database, so these tests only depend on B3's result page, not on its close route.
"""

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from app import create_app
from app.db import get_db
from app.services import places

FAKE_KEY = "fake-server-key-for-tests-0123456789"
FAKE_EMBED_KEY = "fake-embed-key-for-tests-9876543210"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
EMBED_PLACE_URL = "https://www.google.com/maps/embed/v1/place"
ROUTE_URL = "https://www.google.com/maps/dir/"
ROUTE_TEXT = "Open route in Google Maps"
FALLBACK_NAME = "Place from Google Maps"
DETAILS_MISSING = "Details are not available right now."
BAD_PLACE_IDS = ["../x", "a/b", "a?b", ""]


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.headers = {"Content-Type": "application/json"}
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

    def details_urls(self):
        return [call["url"] for call in self.calls if call["url"].startswith(DETAILS_URL)]


def place(place_id, name):
    """A full Place Details answer with a rating, price, location and one photo."""
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
    """Fake Google that knows two places: Pizza Roma (place-a) and Sushi Bar (place-b)."""
    fake = FakeGet()
    fake.responses[DETAILS_URL + "place-a"] = FakeResponse(body=place("place-a", "Pizza Roma"))
    fake.responses[DETAILS_URL + "place-b"] = FakeResponse(body=place("place-b", "Sushi Bar"))
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


@pytest.fixture(autouse=True)
def keys(app):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    app.config["GOOGLE_MAPS_EMBED_KEY"] = FAKE_EMBED_KEY


# --- Reading the page ------------------------------------------------------

class PageParser(HTMLParser):
    """Collects every <iframe> (its attributes) and every <a> (attributes and text)."""

    def __init__(self):
        super().__init__()
        self.iframes = []
        self.links = []
        self._open_link = None

    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            self.iframes.append(dict(attrs))
        if tag == "a":
            self._open_link = {"attrs": dict(attrs), "text": ""}

    def handle_data(self, data):
        if self._open_link is not None:
            self._open_link["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._open_link is not None:
            self._open_link["text"] = " ".join(self._open_link["text"].split())
            self.links.append(self._open_link)
            self._open_link = None


def parse(html):
    parser = PageParser()
    parser.feed(html)
    return parser


def route_links(html):
    return [link for link in parse(html).links if link["text"] == ROUTE_TEXT]


def query_of(url):
    """The query of a URL as a dict of single values, and the URL without the query."""
    parts = urlsplit(url)
    query = {name: values[0] for name, values in parse_qs(parts.query, keep_blank_values=True).items()}
    assert all(len(values) == 1 for values in parse_qs(parts.query).values())
    return f"{parts.scheme}://{parts.netloc}{parts.path}", query


def assert_embed_url(url, place_id, embed_key=FAKE_EMBED_KEY):
    base, query = query_of(url)
    assert base == EMBED_PLACE_URL
    assert query == {"key": embed_key, "q": f"place_id:{place_id}"}


def assert_route_url(url, place_id, name):
    base, query = query_of(url)
    assert base == ROUTE_URL
    assert query == {"api": "1", "destination": name, "destination_place_id": place_id}


# --- Rooms -----------------------------------------------------------------

def create_room(client, mode="nearby", title="Dinner on Friday", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_google_options(app, room_id, place_ids):
    """Store Google options directly, as C2a's search would. Returns {place_id: option id}."""
    with app.app_context():
        db = get_db()
        for place_id in place_ids:
            db.execute(
                "INSERT INTO options (room_id, source, place_id, category) VALUES (?, 'google', ?, 'restaurant')",
                (room_id, place_id),
            )
        db.commit()
        rows = db.execute("SELECT id, place_id FROM options WHERE room_id = ?", (room_id,)).fetchall()
        return {row["place_id"]: row["id"] for row in rows}


def add_manual_option(app, room_id, label):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)", (room_id, label))
        db.commit()
        return db.execute(
            "SELECT id FROM options WHERE room_id = ? AND label = ?", (room_id, label)
        ).fetchone()["id"]


def set_room(app, room_id, status, winner_option_id=None):
    """Set the status and stored winner directly, as B3's close would."""
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE rooms SET status = ?, winner_option_id = ? WHERE id = ?",
            (status, winner_option_id, room_id),
        )
        db.commit()


def result_page(client, room_id):
    response = client.get(f"/rooms/{room_id}/result")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def snapshot(app):
    with app.app_context():
        db = get_db()
        return {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
            for table in ("rooms", "participants", "options", "votes", "vetoes")
        }


@pytest.fixture
def google_room(app, client):
    """A closed "Places nearby" room with Pizza Roma (place-a, the winner) and Sushi Bar (place-b).

    Anna is the creator (`client`), Ben a guest.
    """
    room_id = create_room(client)
    guest = app.test_client()
    join(guest, room_id, "Ben")
    option_ids = add_google_options(app, room_id, ["place-a", "place-b"])
    set_room(app, room_id, "closed", option_ids["place-a"])
    return {"id": room_id, "guest": guest, "options": option_ids}


# --- Helpers: map_embed_url and route_url --------------------------------------

def test_map_embed_url():
    assert_embed_url(places.map_embed_url("embed-key", "place-a"), "place-a", embed_key="embed-key")


@pytest.mark.parametrize("embed_key", ["", None])
def test_map_embed_url_without_key(embed_key):
    assert places.map_embed_url(embed_key, "place-a") is None


@pytest.mark.parametrize("place_id", BAD_PLACE_IDS)
def test_map_embed_url_with_bad_place_id(place_id):
    assert places.map_embed_url("embed-key", place_id) is None


def test_route_url():
    assert_route_url(places.route_url("place-a", "Pizza Roma"), "place-a", "Pizza Roma")


def test_route_url_encodes_the_name():
    name = 'Bar & Grill "Lisboa" #1'
    url = places.route_url("place-a", name)
    assert "#" not in url and '"' not in url and " " not in url
    assert_route_url(url, "place-a", name)


@pytest.mark.parametrize("place_id", BAD_PLACE_IDS)
def test_route_url_with_bad_place_id(place_id):
    assert places.route_url(place_id, "Pizza Roma") is None


# --- Helpers: load_winner ------------------------------------------------------

def test_load_winner_manual_option(google):
    option = {"source": "manual", "label": "Movie night", "place_id": None}
    winner = places.load_winner(FAKE_KEY, FAKE_EMBED_KEY, option)
    assert winner == {"card": {"source": "manual", "label": "Movie night"}, "map_url": None, "route_url": None}
    assert google.calls == []


def test_load_winner_google_option(google):
    option = {"source": "google", "label": None, "place_id": "place-a"}
    winner = places.load_winner(FAKE_KEY, FAKE_EMBED_KEY, option)
    assert google.details_urls() == [DETAILS_URL + "place-a"]
    card = winner["card"]
    assert card["name"] == "Pizza Roma"
    assert card["photo_name"] == "places/place-a/photos/photo-ref-1"
    assert card["details_missing"] is False
    assert card["distance_text"] == ""  # the centre is deleted when the room closes
    assert_embed_url(winner["map_url"], "place-a")
    assert_route_url(winner["route_url"], "place-a", "Pizza Roma")


@pytest.mark.parametrize("failure", ["status", "timeout"])
def test_load_winner_when_google_fails(google, failure):
    if failure == "status":
        google.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=500, body={"error": {}})
    else:
        google.responses[DETAILS_URL + "place-a"] = requests.Timeout("timed out")
    option = {"source": "google", "label": None, "place_id": "place-a"}
    winner = places.load_winner(FAKE_KEY, FAKE_EMBED_KEY, option)
    assert winner["card"]["details_missing"] is True
    assert winner["card"]["name"] == FALLBACK_NAME
    assert_embed_url(winner["map_url"], "place-a")
    assert_route_url(winner["route_url"], "place-a", FALLBACK_NAME)


def test_load_winner_without_server_key(google):
    option = {"source": "google", "label": None, "place_id": "place-a"}
    winner = places.load_winner("", FAKE_EMBED_KEY, option)
    assert google.calls == []
    assert winner["card"]["details_missing"] is True
    assert_embed_url(winner["map_url"], "place-a")
    assert_route_url(winner["route_url"], "place-a", FALLBACK_NAME)


def test_load_winner_without_embed_key(google):
    option = {"source": "google", "label": None, "place_id": "place-a"}
    winner = places.load_winner(FAKE_KEY, "", option)
    assert winner["map_url"] is None
    assert_route_url(winner["route_url"], "place-a", "Pizza Roma")


# --- Config --------------------------------------------------------------------

def real_run_app(monkeypatch, embed_key):
    """Build the app like the real server does (no test config)."""
    monkeypatch.setenv("SECRET_KEY", "test-only-not-a-real-key")
    # Setting a variable (even to "") stops load_dotenv from taking a value from a local .env.
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("GOOGLE_MAPS_EMBED_KEY", embed_key)
    return create_app()


def test_real_run_reads_the_embed_key(monkeypatch):
    app = real_run_app(monkeypatch, f"  {FAKE_EMBED_KEY}\n")
    assert app.config["GOOGLE_MAPS_EMBED_KEY"] == FAKE_EMBED_KEY


def test_real_run_without_embed_key(monkeypatch):
    app = real_run_app(monkeypatch, "")
    assert app.config["GOOGLE_MAPS_EMBED_KEY"] == ""


# --- Result page -----------------------------------------------------------------

@pytest.mark.parametrize("who", ["creator", "guest"])
def test_result_page_shows_map_and_route(client, google_room, who):
    browser = client if who == "creator" else google_room["guest"]
    html = result_page(browser, google_room["id"])
    assert "The group's choice: Pizza Roma" in html
    assert "/photo/places/place-a/photos/photo-ref-1" in html
    assert "4.5 ★" in html

    iframes = parse(html).iframes
    assert len(iframes) == 1
    assert_embed_url(iframes[0]["src"], "place-a")
    assert iframes[0]["title"] == "Map of Pizza Roma"

    links = route_links(html)
    assert len(links) == 1
    assert_route_url(links[0]["attrs"]["href"], "place-a", "Pizza Roma")
    assert links[0]["attrs"]["target"] == "_blank"
    assert links[0]["attrs"]["rel"] == "noopener noreferrer"


def test_only_the_winner_is_loaded_from_google(client, google_room, google):
    result_page(client, google_room["id"])
    assert google.details_urls() == [DETAILS_URL + "place-a"]


def test_server_key_never_in_page_and_embed_key_only_in_iframe(client, google_room):
    html = result_page(client, google_room["id"])
    assert FAKE_KEY not in html
    assert html.count(FAKE_EMBED_KEY) == 1
    assert FAKE_EMBED_KEY in parse(html).iframes[0]["src"]


def test_without_embed_key_no_map_but_route(app, client, google_room):
    app.config["GOOGLE_MAPS_EMBED_KEY"] = ""
    html = result_page(client, google_room["id"])
    assert "<iframe" not in html
    assert len(route_links(html)) == 1
    assert "The group's choice: Pizza Roma" in html


@pytest.mark.parametrize("failure", ["status", "timeout"])
def test_google_fails_for_the_winner(client, google_room, google, failure):
    if failure == "status":
        google.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=500, body={"error": {}})
    else:
        google.responses[DETAILS_URL + "place-a"] = requests.Timeout("timed out")
    html = result_page(client, google_room["id"])
    assert f"The group's choice: {FALLBACK_NAME}" in html
    assert DETAILS_MISSING in html
    assert_embed_url(parse(html).iframes[0]["src"], "place-a")
    assert_route_url(route_links(html)[0]["attrs"]["href"], "place-a", FALLBACK_NAME)


def test_manual_winner_has_no_map_and_no_route(app, client, google):
    room_id = create_room(client, mode="manual")
    pizza = add_manual_option(app, room_id, "Pizza")
    add_manual_option(app, room_id, "Sushi")
    set_room(app, room_id, "closed", pizza)
    html = result_page(client, room_id)
    assert "The group's choice: Pizza" in html
    assert "<iframe" not in html
    assert route_links(html) == []
    assert google.calls == []


@pytest.mark.parametrize("status", ["closed", "voting"])
def test_no_map_without_a_winner(app, client, google, status):
    room_id = create_room(client)
    add_google_options(app, room_id, ["place-a", "place-b"])
    set_room(app, room_id, status, None)
    html = result_page(client, room_id)
    assert "<iframe" not in html
    assert route_links(html) == []
    assert google.calls == []


def test_name_with_html_and_quotes_is_safe(client, google_room, google):
    name = '<script>"x"</script>'
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(body=place("place-a", name))
    html = result_page(client, google_room["id"])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    parsed = parse(html)
    assert parsed.iframes[0]["title"] == f"Map of {name}"  # escaped in the HTML, read back unchanged
    assert_route_url(route_links(html)[0]["attrs"]["href"], "place-a", name)


def test_viewing_the_result_writes_nothing(app, client, google_room):
    before = snapshot(app)
    result_page(client, google_room["id"])
    result_page(google_room["guest"], google_room["id"])
    assert snapshot(app) == before


def test_map_and_route_after_restart(app, client, google_room):
    session_cookie = client.get_cookie("session")
    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
            "GOOGLE_MAPS_API_KEY": FAKE_KEY,
            "GOOGLE_MAPS_EMBED_KEY": FAKE_EMBED_KEY,
        }
    )
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)
    html = result_page(restarted_browser, google_room["id"])
    assert "The group's choice: Pizza Roma" in html
    assert_embed_url(parse(html).iframes[0]["src"], "place-a")
    assert_route_url(route_links(html)[0]["attrs"]["href"], "place-a", "Pizza Roma")
