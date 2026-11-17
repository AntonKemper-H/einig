"""Tests for A10 – F4 Swipe to rate, and a menu link on the rating card (specs/a10-swipe-rating.md).

The gesture itself runs in the browser and is checked by hand on phones. These tests
check what the server sends: the markers the script needs, where the script is loaded,
that the script only presses existing buttons, and the menu link. Google is never called:
`requests.get` is replaced by a fake.
"""

import html as html_lib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode

import pytest

from app.db import get_db
from app.services import places

PROJECT_ROOT = Path(__file__).parent.parent
SWIPE_JS = PROJECT_ROOT / "app" / "static" / "js" / "swipe.js"
HINT = "Swipe right: Rather yes · up: Fine with me · left: Rather not"
MENU_TEXT = "Menu & reviews on Google Maps"
FALLBACK_NAME = "Place from Google Maps"
FAKE_KEY = "fake-key-for-tests-0123456789"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
SEARCH_URL = "https://www.google.com/maps/search/?api=1&"


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
    """Replaces requests.get: answers Place Details by URL and records every call."""

    def __init__(self):
        self.responses = {}
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.get(url, FakeResponse(status_code=404, body={"error": {}}))

    def detail_calls(self):
        return [url for url in self.calls if url.startswith(DETAILS_URL) and not url.endswith("/media")]


@pytest.fixture(autouse=True)
def google(app, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGet()
    fake.responses[DETAILS_URL + "place-a"] = FakeResponse(
        body={"displayName": {"text": "Pizza Roma"}, "rating": 4.5}
    )
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


# --- Reading the HTML --------------------------------------------------------

class ElementFinder(HTMLParser):
    """Collects the inner HTML of every element that has a given attribute."""

    VOID = {"input", "img", "br", "meta", "link", "hr", "source"}

    def __init__(self, attribute):
        super().__init__(convert_charrefs=False)
        self.attribute = attribute
        self.found = []        # list of (attributes, inner html)
        self.open = []         # stack of [tag, attributes, parts, depth]
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        text = self.get_starttag_text()
        for element in self.open:
            element[2].append(text)
        if tag in self.VOID:
            return
        self.depth += 1
        if self.attribute in dict(attrs):
            self.open.append([tag, dict(attrs), [], self.depth])

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for element in list(self.open):
            if element[3] == self.depth:
                self.found.append((element[1], "".join(element[2])))
                self.open.remove(element)
        for element in self.open:
            element[2].append(f"</{tag}>")
        self.depth -= 1

    def handle_data(self, data):
        for element in self.open:
            element[2].append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def elements_with(page_html, attribute):
    finder = ElementFinder(attribute)
    finder.feed(page_html)
    return finder.found


def menu_links(page_html):
    """(href, target, rel) of every link whose text is the menu text."""
    links = []
    for attributes, inner in elements_with(page_html, "href"):
        if html_lib.unescape(inner).strip() == MENU_TEXT:
            links.append(
                (html_lib.unescape(attributes["href"]), attributes.get("target"), attributes.get("rel"))
            )
    return links


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "nearby", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(app, room_id, nickname):
    browser = app.test_client()
    response = browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)
    return browser


def add_options(app, room_id, place_ids=(), labels=()):
    """Store options directly and return {place id or label: option id}."""
    with app.app_context():
        connection = get_db()
        for place_id in place_ids:
            connection.execute(
                "INSERT INTO options (room_id, source, place_id, category) VALUES (?, 'google', ?, 'restaurant')",
                (room_id, place_id),
            )
        for label in labels:
            connection.execute(
                "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)", (room_id, label)
            )
        connection.commit()
        rows = connection.execute("SELECT id, place_id, label FROM options WHERE room_id = ?", (room_id,))
        return {row["place_id"] or row["label"]: row["id"] for row in rows}


def set_status(app, room_id, status):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def rate(client, room_id, option_id, rating="yes"):
    return client.post(f"/rooms/{room_id}/vote", data={"option_id": str(option_id), "rating": rating})


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.data.decode()


def voting_room(app, client, place_ids=(), labels=()):
    room_id = create_room(client)
    ids = add_options(app, room_id, place_ids, labels)
    set_status(app, room_id, "voting")
    return room_id, ids


# --- The script file ---------------------------------------------------------

def test_swipe_js_is_served(client):
    response = client.get("/static/js/swipe.js")
    assert response.status_code == 200
    assert "javascript" in response.content_type


def test_swipe_js_only_presses_existing_buttons():
    source = SWIPE_JS.read_text()
    for forbidden in ("fetch(", "XMLHttpRequest", "import ", "http"):
        assert forbidden not in source


# --- The rating page ---------------------------------------------------------

def test_next_card_has_the_swipe_markers(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    html = page(client, f"/rooms/{room_id}/vote")
    scripts = [attributes for attributes, _ in elements_with(html, "src")
               if attributes["src"].startswith("/static/js/swipe.js")]
    assert len(scripts) == 1
    assert "defer" in scripts[0]

    cards = elements_with(html, "data-swipe-card")
    assert len(cards) == 1
    areas = elements_with(html, "data-swipe-area")
    assert len(areas) == 1
    area_html = areas[0][1]
    assert "Pizza Roma" in area_html
    assert 'name="rating"' not in area_html
    assert "<form" not in area_html
    assert "data-swipe-area" in cards[0][1]

    hints = [attributes for attributes, inner in elements_with(html, "hidden")
             if html_lib.unescape(inner).strip() == HINT]
    assert len(hints) == 1
    # The hint sits above the card, not inside it.
    assert HINT not in html_lib.unescape(cards[0][1])
    assert html.index(HINT) < html.index("data-swipe-card")


def test_buttons_and_option_id_stay_inside_the_swipe_card(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    card_html = elements_with(page(client, f"/rooms/{room_id}/vote"), "data-swipe-card")[0][1]
    for value in ("yes", "ok", "no"):
        assert f'name="rating" value="{value}"' in card_html
    assert f'name="option_id" value="{ids["place-a"]}"' in card_html


def test_overview_has_no_swipe(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"], labels=["Burger Bar"])
    for option_id in ids.values():
        rate(client, room_id, option_id)
    html = page(client, f"/rooms/{room_id}/vote")
    assert "You have rated all options." in html
    assert "data-swipe-card" not in html
    assert "data-swipe-area" not in html
    assert HINT not in html
    assert "swipe.js" not in html


def test_other_pages_do_not_load_swipe_js(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"], labels=["Burger Bar"])
    set_status(app, room_id, "collecting")
    assert "swipe.js" not in page(client, f"/rooms/{room_id}")
    assert "swipe.js" not in page(client, f"/rooms/{room_id}/lobby")
    set_status(app, room_id, "voting")
    rate(client, room_id, ids["Burger Bar"])
    assert client.post(f"/rooms/{room_id}/close").status_code in (302, 303)
    assert "swipe.js" not in page(client, f"/rooms/{room_id}/result")


def test_rating_the_way_the_script_does_is_saved(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"], labels=["Burger Bar"])
    response = rate(client, room_id, ids["place-a"], "ok")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}/vote")
    with app.app_context():
        saved = [tuple(row) for row in get_db().execute("SELECT option_id, rating FROM votes")]
    assert saved == [(ids["place-a"], "ok")]


def test_manual_option_has_no_menu_link_but_swipes(app, client):
    room_id, ids = voting_room(app, client, labels=["Burger Bar"])
    html = page(client, f"/rooms/{room_id}/vote")
    assert MENU_TEXT not in html
    cards = elements_with(html, "data-swipe-card")
    assert len(cards) == 1
    assert "Burger Bar" in elements_with(html, "data-swipe-area")[0][1]


def test_rating_page_shows_no_ratings_of_others(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"], labels=["Burger Bar", "Taco Truck"])
    ben = join(app, room_id, "Bernadette")
    for option_id in ids.values():
        rate(ben, room_id, option_id, "no")
    # Anna rates one option, so a next card is still left for her.
    rate(client, room_id, ids["Burger Bar"], "yes")
    html = page(client, f"/rooms/{room_id}/vote")
    assert elements_with(html, "data-swipe-card")
    assert "Bernadette" not in html
    assert "Your rating" not in html


# --- The menu link -----------------------------------------------------------

def test_place_page_url():
    expected = SEARCH_URL + urlencode({"query": "Café Lisboa & Co", "query_place_id": "ChIJ-abc_123"})
    assert places.place_page_url("ChIJ-abc_123", "Café Lisboa & Co") == expected
    for bad in ("", "abc/def", "abc?x=1", "../places", "a b"):
        assert places.place_page_url(bad, "Pizza Roma") is None


def test_google_card_shows_the_menu_link(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    links = menu_links(page(client, f"/rooms/{room_id}/vote"))
    assert links == [(places.place_page_url("place-a", "Pizza Roma"), "_blank", "noopener noreferrer")]


def test_menu_link_uses_the_fallback_name_when_details_failed(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-gone"])
    html = page(client, f"/rooms/{room_id}/vote")
    assert "Details are not available right now." in html
    assert menu_links(html) == [
        (places.place_page_url("place-gone", FALLBACK_NAME), "_blank", "noopener noreferrer")
    ]


def test_menu_link_makes_no_extra_google_call(app, client, google):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    page(client, f"/rooms/{room_id}/vote")
    assert google.detail_calls() == [DETAILS_URL + "place-a"]


def test_room_page_cards_have_no_menu_link(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    set_status(app, room_id, "collecting")
    html = page(client, f"/rooms/{room_id}")
    assert "Pizza Roma" in html
    assert MENU_TEXT not in html
    assert "data-swipe" not in html
