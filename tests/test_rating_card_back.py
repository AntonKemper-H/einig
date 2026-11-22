"""Tests for C10 – F30 place details, part 2: the cards, the rating page and the swipe script
(specs/c10-place-details.md).

The turning of the card runs in the browser (CSS and swipe.js) and is checked by hand on
a phone. These tests check what the server sends and what the script file contains.
Google is never called: `requests.get` is replaced by a fake.
"""

import html as html_lib
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.db import get_db
from app.services import places
from app.services.places import BACK_FIELD_MASK, CARD_FIELD_MASK

PROJECT_ROOT = Path(__file__).parent.parent
SWIPE_JS = PROJECT_ROOT / "app" / "static" / "js" / "swipe.js"
FAKE_KEY = "fake-key-for-tests-0123456789"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
MENU_TEXT = "Menu & reviews on Google Maps"
OPEN_TEXT = "More about this place"
CLOSE_TEXT = "Back to the card"
NO_DETAILS_TEXT = "Google has no more details for this place."
REVIEWS_LINE = "Reviews selected by Google"
READ_TEXT = "Read on Google Maps"
DETAILS_MISSING = "Details are not available right now."


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
    """Replaces requests.get: answers by URL, records every call with its headers."""

    def __init__(self):
        self.responses = {}
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.get(url, FakeResponse(status_code=404, body={"error": {}}))

    def detail_masks(self):
        """The field mask of every Place Details call, in order."""
        return [
            call["headers"]["X-Goog-FieldMask"]
            for call in self.calls
            if call["url"].startswith(DETAILS_URL) and not call["url"].endswith("/media")
        ]


def photo(place_id, number, author="Maria Silva"):
    return {
        "name": f"places/{place_id}/photos/ref-{number}",
        "authorAttributions": [{"displayName": author, "uri": "https://maps.google.com/maria"}],
    }


def review(number, **changes):
    body = {
        "relativePublishTimeDescription": f"{number} weeks ago",
        "rating": 4,
        "text": {"text": f"Review text {number}", "languageCode": "en"},
        "authorAttribution": {
            "displayName": f"Author {number}",
            "uri": f"https://www.google.com/maps/contrib/{number}",
            "photoUri": f"https://lh3.googleusercontent.com/a/{number}",
        },
        "googleMapsUri": f"https://www.google.com/maps/reviews/{number}",
    }
    body.update(changes)
    return body


def front_answer(place_id="place-a", name="Pizza Roma"):
    """What Google sends for CARD_FIELD_MASK."""
    return {
        "displayName": {"text": name, "languageCode": "en"},
        "rating": 4.5,
        "userRatingCount": 812,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "location": {"latitude": 38.740, "longitude": -9.153},
        "primaryTypeDisplayName": {"text": "Italian Restaurant", "languageCode": "en"},
        "photos": [photo(place_id, 1)],
    }


def back_answer(place_id="place-a"):
    """What Google sends for BACK_FIELD_MASK."""
    body = front_answer(place_id)
    body.update({
        "editorialSummary": {"text": "Wood-fired pizza near the river.", "languageCode": "en"},
        "servesDinner": True,
        "servesWine": True,
        "outdoorSeating": True,
        "reviews": [review(1), review(2), review(3), review(4)],
        "photos": [photo(place_id, number) for number in range(1, 6)],
    })
    return body


@pytest.fixture(autouse=True)
def google(app, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGet()
    fake.responses[DETAILS_URL + "place-a"] = FakeResponse(body=back_answer())
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
        self.starts = []       # (line, column) where each found element starts
        self.open = []         # stack of [tag, attributes, parts, depth, start]
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        text = self.get_starttag_text()
        for element in self.open:
            element[2].append(text)
        if tag in self.VOID:
            return
        self.depth += 1
        if self.attribute in dict(attrs):
            self.open.append([tag, dict(attrs), [], self.depth, self.getpos()])

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for element in list(self.open):
            if element[3] == self.depth:
                self.found.append((element[1], "".join(element[2])))
                self.starts.append(element[4])
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


class TagCollector(HTMLParser):
    """Collects the attributes of every start tag with a given name (also void tags like img, input)."""

    def __init__(self, tag):
        super().__init__(convert_charrefs=False)
        self.tag = tag
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag == self.tag:
            self.found.append({name: value for name, value in attrs})


def elements_with(page_html, attribute):
    finder = ElementFinder(attribute)
    finder.feed(page_html)
    return finder.found


def tags(fragment, tag):
    collector = TagCollector(tag)
    collector.feed(fragment)
    return collector.found


def start_of(page_html, attribute, inner_text=None):
    """(line, column) of the first element with the attribute (and that inner text)."""
    finder = ElementFinder(attribute)
    finder.feed(page_html)
    for (_, inner), start in zip(finder.found, finder.starts):
        if inner_text is None or html_lib.unescape(inner).strip() == inner_text:
            return start
    return None


def links_in(fragment):
    """(href, target, rel, text) of every link in the fragment."""
    return [
        (attributes["href"], attributes.get("target"), attributes.get("rel"), html_lib.unescape(inner).strip())
        for attributes, inner in elements_with(fragment, "href")
    ]


def labels_in(page_html):
    """(for, text, attributes) of every label."""
    return [
        (attributes.get("for"), html_lib.unescape(inner).strip(), attributes)
        for attributes, inner in elements_with(page_html, "for")
    ]


def menu_links(page_html):
    return [href for href, _, _, text in links_in(page_html) if text == MENU_TEXT]


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "nearby", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


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


def rating_page(app, client, place_ids=("place-a",), labels=()):
    """(html, room id, option ids) of the rating page whose next card is the first option."""
    room_id, ids = voting_room(app, client, place_ids=place_ids, labels=labels)
    return page(client, f"/rooms/{room_id}/vote"), room_id, ids


def database_snapshot(app):
    """Every row of every table, to prove that a page view writes nothing."""
    with app.app_context():
        connection = get_db()
        names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {name: [tuple(row) for row in connection.execute(f"SELECT * FROM {name}")] for name in sorted(names)}


# --- The back of the rating card -------------------------------------------------

def test_rating_page_asks_google_once_and_with_the_back_mask(app, client, google):
    rating_page(app, client)
    assert google.detail_masks() == [BACK_FIELD_MASK]


def test_card_has_checkbox_labels_and_back(app, client):
    html, room_id, ids = rating_page(app, client)
    option_id = ids["place-a"]

    checkboxes = [item for item in tags(html, "input") if "data-flip-toggle" in item]
    assert len(checkboxes) == 1
    checkbox = checkboxes[0]
    assert checkbox["type"] == "checkbox"
    assert checkbox["id"] == f"card-side-{option_id}"
    assert "hidden" not in checkbox  # hidden by CSS only: it must stay reachable with Tab
    assert "visually-hidden" in checkbox["class"].split()

    labels = {text: (for_id, attributes) for for_id, text, attributes in labels_in(html)}
    assert set(labels) >= {OPEN_TEXT, CLOSE_TEXT}
    assert labels[OPEN_TEXT][0] == f"card-side-{option_id}"
    assert labels[CLOSE_TEXT][0] == f"card-side-{option_id}"
    assert "data-flip-open" in labels[OPEN_TEXT][1]
    assert "data-flip-close" in labels[CLOSE_TEXT][1]

    assert len(elements_with(html, "data-card-back")) == 1
    assert len(elements_with(html, "data-swipe-area")) == 1


def test_labels_sit_outside_the_swipe_area_and_the_open_label_outside_the_back(app, client):
    html, room_id, ids = rating_page(app, client)
    area_html = elements_with(html, "data-swipe-area")[0][1]
    back_html = elements_with(html, "data-card-back")[0][1]
    assert OPEN_TEXT not in area_html
    assert CLOSE_TEXT not in area_html
    assert OPEN_TEXT not in back_html
    assert CLOSE_TEXT in back_html
    # The back is not swipeable: it has no swipe area and no rating buttons inside.
    assert "data-swipe-area" not in back_html
    assert 'name="rating"' not in back_html


def test_parts_of_the_card_come_in_the_specified_order(app, client):
    html, room_id, ids = rating_page(app, client)
    card_html = elements_with(html, "data-swipe-card")[0][1]
    order = [
        card_html.index("data-flip-toggle"),
        card_html.index("data-swipe-area"),
        card_html.index("data-flip-open"),
        card_html.index("data-card-back"),
        card_html.index("Menu &amp; reviews on Google Maps"),
        card_html.index('name="rating"'),
    ]
    assert order == sorted(order)
    # The checkbox is the first element in the card, so the CSS sibling selectors reach the rest.
    assert card_html.strip().startswith("<input")


def test_back_shows_description_offers_and_the_reviews_line(app, client):
    html, room_id, ids = rating_page(app, client)
    back_html = html_lib.unescape(elements_with(html, "data-card-back")[0][1])
    assert "Wood-fired pizza near the river." in back_html
    assert "Dinner · Wine · Outdoor seating" in back_html
    assert REVIEWS_LINE in back_html
    assert back_html.index("Wood-fired") < back_html.index("Dinner · Wine") < back_html.index(REVIEWS_LINE)


def test_back_shows_three_reviews_with_every_part_unchanged(app, client):
    html, room_id, ids = rating_page(app, client)
    back_html = elements_with(html, "data-card-back")[0][1]
    text = html_lib.unescape(back_html)
    for number in (1, 2, 3):
        assert f"Review text {number}" in text
        assert f"{number} weeks ago" in text
        assert f"Author {number}" in text
    assert "Review text 4" not in text
    assert text.count("4 ★") >= 3

    links = links_in(back_html)
    for number in (1, 2, 3):
        assert (f"https://www.google.com/maps/contrib/{number}", "_blank", "noopener noreferrer", f"Author {number}") in links
        assert (f"https://www.google.com/maps/reviews/{number}", "_blank", "noopener noreferrer", READ_TEXT) in links
    assert sum(1 for link in links if link[3] == READ_TEXT) == 3

    pictures = [item for item in tags(back_html, "img") if "googleusercontent" in item.get("src", "")]
    assert [item["src"] for item in pictures] == [f"https://lh3.googleusercontent.com/a/{n}" for n in (1, 2, 3)]
    for item in pictures:
        assert item["width"] == "32" and item["height"] == "32"
        assert item["alt"] == ""
        assert item["loading"] == "lazy"
        assert item["referrerpolicy"] == "no-referrer"


def test_back_shows_the_extra_photos_through_the_proxy_with_authors(app, client):
    html, room_id, ids = rating_page(app, client)
    back_html = elements_with(html, "data-card-back")[0][1]
    sources = [item["src"] for item in tags(back_html, "img") if item.get("src", "").startswith("/photo/")]
    assert sources == [f"/photo/places/place-a/photos/ref-{number}" for number in (2, 3, 4)]
    assert all(item.get("loading") == "lazy" for item in tags(back_html, "img") if item["src"].startswith("/photo/"))
    maria = [link for link in links_in(back_html) if link[3] == "Maria Silva"]
    assert len(maria) == 3
    assert all(link[1:3] == ("_blank", "noopener noreferrer") for link in maria)
    # The front still shows the first photo, not the extra ones.
    area_html = elements_with(html, "data-swipe-area")[0][1]
    assert "/photo/places/place-a/photos/ref-1" in area_html
    assert "ref-2" not in area_html


def test_rating_buttons_stay_below_the_card_for_both_sides(app, client):
    html, room_id, ids = rating_page(app, client)
    card_html = elements_with(html, "data-swipe-card")[0][1]
    for value in ("yes", "ok", "no"):
        assert f'name="rating" value="{value}"' in card_html
    back_html = elements_with(html, "data-card-back")[0][1]
    assert 'name="rating"' not in back_html


def test_front_shows_kind_and_rating_count(app, client):
    html, room_id, ids = rating_page(app, client)
    area_html = elements_with(html, "data-swipe-area")[0][1]
    assert "Italian Restaurant" in area_html
    assert "4.5 ★ (812) · €€" in html_lib.unescape(area_html)
    assert [attributes["class"] for attributes, inner in elements_with(area_html, "class")
            if "place-kind" in attributes["class"].split()] == ["place-kind"]


# --- One menu link ---------------------------------------------------------------

def test_the_rating_page_still_has_exactly_one_menu_link_now_on_the_about_page_of_the_back(app, client):
    # C11 (D20) changed this test: the menu link moved from below the card into the back's "about" page.
    html, room_id, ids = rating_page(app, client)
    assert menu_links(html) == [places.place_page_url("place-a", "Pizza Roma")]
    back_html = elements_with(html, "data-card-back")[0][1]
    assert menu_links(back_html) == menu_links(html)


# --- Nothing more to show, nothing to turn ------------------------------------------

def test_a_place_without_back_details_says_so_on_the_back(app, client, google):
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(body=front_answer())
    html, room_id, ids = rating_page(app, client)
    back_html = elements_with(html, "data-card-back")[0][1]
    assert NO_DETAILS_TEXT in html_lib.unescape(back_html)
    assert REVIEWS_LINE not in back_html
    assert CLOSE_TEXT in html_lib.unescape(back_html)


def test_a_manual_option_has_no_checkbox_no_labels_and_no_back(app, client):
    html, room_id, ids = rating_page(app, client, place_ids=(), labels=("Burger Bar",))
    assert "Burger Bar" in html
    assert "data-flip-toggle" not in html
    assert "data-card-back" not in html
    assert OPEN_TEXT not in html and CLOSE_TEXT not in html
    assert len(elements_with(html, "data-swipe-card")) == 1


def test_a_google_option_whose_details_failed_has_no_checkbox_no_labels_and_no_back(app, client, google):
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=500, body={})
    html, room_id, ids = rating_page(app, client)
    assert DETAILS_MISSING in html
    assert "data-flip-toggle" not in html
    assert "data-card-back" not in html
    assert OPEN_TEXT not in html and CLOSE_TEXT not in html


def test_only_the_next_card_gets_a_back(app, client, google):
    google.responses[DETAILS_URL + "place-b"] = FakeResponse(body=back_answer("place-b"))
    html, room_id, ids = rating_page(app, client, place_ids=("place-a", "place-b"))
    assert len(elements_with(html, "data-card-back")) == 1
    assert google.detail_masks() == [BACK_FIELD_MASK]  # one call for the one card shown


# --- The other pages show the front only -------------------------------------------------

def assert_front_only(html):
    assert "Italian Restaurant" in html
    assert "4.5 ★ (812)" in html_lib.unescape(html)
    assert "data-card-back" not in html
    assert "data-flip-toggle" not in html
    assert OPEN_TEXT not in html


def test_the_overview_has_no_back_and_asks_for_the_card_mask_only(app, client, google):
    room_id, ids = voting_room(app, client, place_ids=["place-a"], labels=["Burger Bar"])
    # A participant who never rates, so the room is not "everyone done" (B5) and stays open.
    app.test_client().post(f"/rooms/{room_id}/join", data={"nickname": "Idle"})
    for option_id in ids.values():
        rate(client, room_id, option_id)
    google.calls.clear()
    html = page(client, f"/rooms/{room_id}/vote")
    assert "You have rated all options." in html
    assert_front_only(html)
    assert google.detail_masks() == [CARD_FIELD_MASK]


def test_the_room_page_has_no_back_and_asks_for_the_card_mask_only(app, client, google):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    set_status(app, room_id, "collecting")
    google.calls.clear()
    html = page(client, f"/rooms/{room_id}")
    assert_front_only(html)
    assert BACK_FIELD_MASK not in google.detail_masks()
    assert set(google.detail_masks()) == {CARD_FIELD_MASK}


def test_the_result_page_has_no_back_and_asks_for_the_card_mask_only(app, client, google):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    rate(client, room_id, ids["place-a"], "yes")
    assert client.post(f"/rooms/{room_id}/close").status_code in (302, 303)
    google.calls.clear()
    html = page(client, f"/rooms/{room_id}/result")
    assert_front_only(html)
    assert BACK_FIELD_MASK not in google.detail_masks()
    assert set(google.detail_masks()) == {CARD_FIELD_MASK}


# --- Safety --------------------------------------------------------------------------------

def test_review_text_names_and_description_are_escaped(app, client, google):
    body = back_answer()
    body["editorialSummary"] = {"text": "<script>alert(1)</script>"}
    body["reviews"] = [
        review(1, text={"text": "<b>Great</b> & cheap"},
               authorAttribution={"displayName": "<i>Eve</i>", "uri": "https://www.google.com/maps/contrib/1"}),
    ]
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(body=body)
    html, room_id, ids = rating_page(app, client)
    for raw in ("<script>alert(1)</script>", "<b>Great</b>", "<i>Eve</i>"):
        assert raw not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;Great&lt;/b&gt; &amp; cheap" in html
    assert "&lt;i&gt;Eve&lt;/i&gt;" in html


def test_the_api_key_never_appears_in_the_page(app, client):
    html, room_id, ids = rating_page(app, client)
    assert FAKE_KEY not in html
    assert "key=" not in html


def test_viewing_the_rating_page_writes_nothing(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    before = database_snapshot(app)
    page(client, f"/rooms/{room_id}/vote")
    assert database_snapshot(app) == before


def test_rating_from_the_one_card_view_still_works(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a", "place-b"])
    first = [option for option in (ids["place-a"], ids["place-b"])]
    html = page(client, f"/rooms/{room_id}/vote")
    shown = [value for value in first if f'name="option_id" value="{value}"' in html]
    assert len(shown) == 1
    response = rate(client, room_id, shown[0], "ok")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}/vote")
    with app.app_context():
        saved = [tuple(row) for row in get_db().execute("SELECT option_id, rating FROM votes")]
    assert saved == [(shown[0], "ok")]


# --- swipe.js -----------------------------------------------------------------------------------

def test_swipe_js_turns_the_card_on_a_short_tap_and_leaves_links_alone():
    source = SWIPE_JS.read_text()
    assert "TAP_DISTANCE" in source
    assert "= 10" in source.split("TAP_DISTANCE", 1)[1].split("\n", 1)[0]
    assert "[data-flip-toggle]" in source
    assert ".click()" in source
    assert 'closest("a")' in source


def test_swipe_js_still_passes_the_a10_static_check():
    source = SWIPE_JS.read_text()
    for forbidden in ("fetch(", "XMLHttpRequest", "import ", "http"):
        assert forbidden not in source
