"""Tests for C11 – F4/F30 full-screen rating card (specs/c11-fullscreen-card.md).

Swiping, scroll snapping and the full-screen layout run in the browser and are checked by hand
on a phone. These tests check what the server sends and what the CSS and script files contain.
Google is never called: `requests.get` is replaced by a fake.
"""

import html as html_lib
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app.db import get_db
from app.services import places
from app.services.places import BACK_FIELD_MASK

PROJECT_ROOT = Path(__file__).parent.parent
SWIPE_JS = PROJECT_ROOT / "app" / "static" / "js" / "swipe.js"
APP_CSS = PROJECT_ROOT / "app" / "static" / "css" / "app.css"
FAKE_KEY = "fake-key-for-tests-0123456789"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
MENU_TEXT = "Menu & reviews on Google Maps"
OPEN_TEXT = "More about this place"
CLOSE_TEXT = "Back to the card"
NO_DETAILS_TEXT = "Google has no more details for this place."
REVIEWS_LINE = "Reviews selected by Google"
READ_TEXT = "Read on Google Maps"
DETAILS_MISSING = "Details are not available right now."
JOKER_BUTTON_TEXT = "Use my joker on this option (cannot be undone)"
PAGE_NAMES = ["about", "photos", "reviews"]
PAGE_TITLES = {"about": "About", "photos": "Photos", "reviews": "Reviews"}


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


# --- More helpers for this task ------------------------------------------------------

def joker_cannot_be_undone(place_name):
    return f"Use my joker on {place_name}? This cannot be undone."


def back_html_of(html):
    return elements_with(html, "data-card-back")[0][1]


def pages_of(html):
    """{page name: inner html} of the three pages on the back."""
    return {attributes["data-card-page"]: inner for attributes, inner in elements_with(back_html_of(html), "data-card-page")}


def page_ids_of(html):
    return [attributes.get("id") for attributes, _ in elements_with(back_html_of(html), "data-card-page")]


def join_as_guest(app, room_id, nickname="Ben"):
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": nickname}).status_code in (302, 303)
    return guest


def use_joker(client, room_id, option_id):
    return client.post(f"/rooms/{room_id}/veto", data={"option_id": str(option_id)})


def css_rules():
    """[(selector, body)] of the CSS file, comments removed. Simple enough for our flat stylesheet."""
    import re
    text = re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.S)
    return [(selector.strip(), rule.strip()) for selector, rule in re.findall(r"([^{}]+)\{([^{}]*)\}", text)]


# --- The three pages on the back -------------------------------------------------------

def test_the_back_has_three_pages_in_the_order_about_photos_reviews(app, client):
    html, room_id, ids = rating_page(app, client)
    names = [attributes["data-card-page"] for attributes, _ in elements_with(back_html_of(html), "data-card-page")]
    assert names == PAGE_NAMES


def test_about_page_has_description_offers_and_the_one_menu_link(app, client):
    html, room_id, ids = rating_page(app, client)
    about = pages_of(html)["about"]
    text = html_lib.unescape(about)
    assert "Wood-fired pizza near the river." in text
    assert "Dinner · Wine · Outdoor seating" in text
    assert menu_links(about) == [places.place_page_url("place-a", "Pizza Roma")]
    assert REVIEWS_LINE not in text and "Review text" not in text
    assert "/photo/" not in about


def test_photos_page_has_the_extra_photos_with_their_authors(app, client):
    html, room_id, ids = rating_page(app, client)
    photos = pages_of(html)["photos"]
    sources = [item["src"] for item in tags(photos, "img")]
    assert sources == [f"/photo/places/place-a/photos/ref-{number}" for number in (2, 3, 4)]
    assert all(item.get("loading") == "lazy" for item in tags(photos, "img"))
    maria = [link for link in links_in(photos) if link[3] == "Maria Silva"]
    assert len(maria) == 3
    assert all(link[1:3] == ("_blank", "noopener noreferrer") for link in maria)
    assert "Review text" not in html_lib.unescape(photos)


def test_reviews_page_has_the_reviews_line_and_three_reviews_unchanged(app, client):
    html, room_id, ids = rating_page(app, client)
    reviews = pages_of(html)["reviews"]
    text = html_lib.unescape(reviews)
    assert REVIEWS_LINE in text
    for number in (1, 2, 3):
        assert f"Review text {number}" in text
        assert f"{number} weeks ago" in text
        assert f"Author {number}" in text
    assert "Review text 4" not in text
    links = links_in(reviews)
    for number in (1, 2, 3):
        assert (f"https://www.google.com/maps/contrib/{number}", "_blank", "noopener noreferrer", f"Author {number}") in links
        assert (f"https://www.google.com/maps/reviews/{number}", "_blank", "noopener noreferrer", READ_TEXT) in links
    pictures = [item for item in tags(reviews, "img") if "googleusercontent" in item.get("src", "")]
    assert [item["src"] for item in pictures] == [f"https://lh3.googleusercontent.com/a/{n}" for n in (1, 2, 3)]
    assert "Wood-fired" not in text and "/photo/" not in reviews


def test_the_back_stays_a_single_back_with_the_close_label(app, client):
    html, room_id, ids = rating_page(app, client)
    assert len(elements_with(html, "data-card-back")) == 1
    assert CLOSE_TEXT in html_lib.unescape(back_html_of(html))
    assert OPEN_TEXT not in html_lib.unescape(back_html_of(html))


def test_a_page_without_content_says_so_and_the_back_keeps_three_pages_and_dots(app, client, google):
    body = back_answer()
    del body["reviews"]
    body["photos"] = [photo("place-a", 1)]  # only the front photo: no extra photos
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(body=body)
    html, room_id, ids = rating_page(app, client)
    pages = pages_of(html)
    assert list(pages) == PAGE_NAMES
    assert NO_DETAILS_TEXT in html_lib.unescape(pages["photos"])
    assert NO_DETAILS_TEXT in html_lib.unescape(pages["reviews"])
    assert NO_DETAILS_TEXT not in html_lib.unescape(pages["about"])
    assert len(elements_with(back_html_of(html), "data-card-dot")) == 3


def test_when_google_sends_no_back_details_the_empty_pages_say_so(app, client, google):
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(body=front_answer())
    html, room_id, ids = rating_page(app, client)
    pages = pages_of(html)
    assert list(pages) == PAGE_NAMES
    assert NO_DETAILS_TEXT in html_lib.unescape(pages["photos"])
    assert NO_DETAILS_TEXT in html_lib.unescape(pages["reviews"])
    assert len(elements_with(back_html_of(html), "data-card-dot")) == 3


# --- The three dots ------------------------------------------------------------------------

def test_three_dots_link_to_the_three_pages_and_the_first_is_current(app, client):
    html, room_id, ids = rating_page(app, client)
    option_id = ids["place-a"]
    back_html = back_html_of(html)
    dots = elements_with(back_html, "data-card-dot")
    assert len(dots) == 3
    page_ids = page_ids_of(html)
    assert page_ids == [f"card-page-{option_id}-{name}" for name in PAGE_NAMES]
    for (attributes, _), page_id, number, name in zip(dots, page_ids, (1, 2, 3), PAGE_NAMES):
        assert attributes["href"] == f"#{page_id}"
        assert attributes["aria-label"] == f"Page {number} of 3: {PAGE_TITLES[name]}"
    assert dots[0][0].get("aria-current") == "true"
    assert all("aria-current" not in attributes for attributes, _ in dots[1:])


def test_the_dots_come_after_the_pages_inside_the_back(app, client):
    html, room_id, ids = rating_page(app, client)
    back_html = back_html_of(html)
    assert back_html.index("data-card-dot") > back_html.rindex("data-card-page")
    # Dots are only on the back, never on the front.
    assert "data-card-dot" not in elements_with(html, "data-swipe-area")[0][1]


# --- One menu link, on the about page ----------------------------------------------------------

def test_exactly_one_menu_link_on_the_rating_page_and_it_is_on_the_about_page(app, client):
    html, room_id, ids = rating_page(app, client)
    expected = places.place_page_url("place-a", "Pizza Roma")
    assert menu_links(html) == [expected]
    assert menu_links(pages_of(html)["about"]) == [expected]


# --- Front: the only swipe area ---------------------------------------------------------------------

def test_the_front_is_the_only_swipe_area_and_the_back_has_no_rating_buttons(app, client):
    html, room_id, ids = rating_page(app, client)
    assert len(elements_with(html, "data-swipe-area")) == 1
    back_html = back_html_of(html)
    assert "data-swipe-area" not in back_html
    assert 'name="rating"' not in back_html
    assert "<form" not in back_html
    area_html = elements_with(html, "data-swipe-area")[0][1]
    assert "Pizza Roma" in area_html and "/photo/places/place-a/photos/ref-1" in area_html
    assert "data-card-page" not in area_html


# --- The buttons stay, out of sight ----------------------------------------------------------------------

def test_rating_and_joker_buttons_are_still_buttons_and_not_hidden_by_attribute(app, client):
    html, room_id, ids = rating_page(app, client)
    card_html = elements_with(html, "data-swipe-card")[0][1]
    ratings = [item for item in tags(card_html, "button") if item.get("name") == "rating"]
    assert [item["value"] for item in ratings] == ["yes", "ok", "no"]
    joker_form = [form for form in card_html.split("<form") if f'/rooms/{room_id}/veto"' in form][0].split("</form>")[0]
    joker = tags(joker_form, "button")
    assert len(joker) == 1  # the existing joker button of B4, in its own form
    assert JOKER_BUTTON_TEXT in html_lib.unescape(card_html)
    for item in ratings + joker:
        assert "hidden" not in item
        assert item.get("type") == "submit"
        assert "style" not in item or "display" not in item["style"]


def test_the_css_hides_the_buttons_visually_and_shows_them_on_focus_within():
    # U4 (D27, changed with the team's OK): the buttons are visible as the icon row; they are
    # never removed with display: none (as before) and never clipped out of sight any more.
    rules = css_rules()
    for selector, rule in rules:
        if "rating-buttons" in selector or 'name="rating"' in selector or "joker-form" in selector:
            assert "display: none" not in rule and "display:none" not in rule
        if "rating-buttons" in selector or "veto" in selector:
            assert "clip:" not in rule


def test_the_buttons_are_hidden_only_once_swipe_js_has_started():
    # U4 (D27, changed with the team's OK): not hidden at all now, also not under .swipe-ready.
    hiding = [selector for selector, rule in css_rules() if "clip:" in rule and ("veto" in selector or "rating-buttons" in selector)]
    assert hiding == []
    assert 'classList.add("swipe-ready")' in SWIPE_JS.read_text()


def test_the_form_routes_and_fields_are_unchanged(app, client):
    html, room_id, ids = rating_page(app, client)
    card_html = elements_with(html, "data-swipe-card")[0][1]
    assert f'action="/rooms/{room_id}/vote"' in card_html
    assert f'action="/rooms/{room_id}/veto"' in card_html
    assert f'name="option_id" value="{ids["place-a"]}"' in card_html


# --- The joker question ----------------------------------------------------------------------------------

def test_the_joker_question_is_hidden_and_has_the_name_and_both_buttons(app, client):
    html, room_id, ids = rating_page(app, client)
    questions = elements_with(html, "data-joker-question")
    assert len(questions) == 1
    attributes, inner = questions[0]
    assert "hidden" in attributes
    text = html_lib.unescape(inner)
    assert joker_cannot_be_undone("Pizza Roma") in " ".join(text.split())
    buttons = {html_lib.unescape(text_).strip(): item for item, text_ in elements_with(inner, "type")}
    assert set(buttons) == {"Use joker", "Cancel"}
    assert all(item["type"] == "button" for item in buttons.values())  # nothing is sent by these buttons
    assert 'name="rating"' not in inner and "<form" not in inner


def test_the_joker_question_is_inside_the_card_but_not_in_the_swipe_area_or_the_back(app, client):
    html, room_id, ids = rating_page(app, client)
    card_html = elements_with(html, "data-swipe-card")[0][1]
    assert "data-joker-question" in card_html
    assert "data-joker-question" not in elements_with(html, "data-swipe-area")[0][1]
    assert "data-joker-question" not in back_html_of(html)


def test_a_manual_option_gets_the_joker_question_with_its_label(app, client):
    html, room_id, ids = rating_page(app, client, place_ids=(), labels=("Burger Bar",))
    inner = elements_with(html, "data-joker-question")[0][1]
    assert joker_cannot_be_undone("Burger Bar") in " ".join(html_lib.unescape(inner).split())


def test_no_joker_question_after_the_joker_was_used(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a", "place-b"])
    shown = [value for value in ids.values() if f'name="option_id" value="{value}"' in page(client, f"/rooms/{room_id}/vote")][0]
    assert use_joker(client, room_id, shown).status_code in (302, 303)
    html = page(client, f"/rooms/{room_id}/vote")
    assert "data-joker-question" not in html
    assert "You used your joker on:" in html


def test_viewing_the_page_saves_no_vote_and_no_joker(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    before = database_snapshot(app)
    page(client, f"/rooms/{room_id}/vote")
    assert database_snapshot(app) == before
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM vetoes").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM votes").fetchone()[0] == 0


# --- Manual options and failed details: front only --------------------------------------------------------------

def test_a_manual_option_has_no_back_and_no_dots_but_is_swiped_like_any_card(app, client):
    html, room_id, ids = rating_page(app, client, place_ids=(), labels=("Burger Bar",))
    assert "data-card-back" not in html and "data-card-dot" not in html and "data-card-page" not in html
    assert len(elements_with(html, "data-swipe-area")) == 1
    assert 'name="rating" value="yes"' in html


def test_a_google_option_whose_details_failed_has_no_back_and_no_dots(app, client, google):
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(status_code=500, body={})
    html, room_id, ids = rating_page(app, client)
    assert "data-card-back" not in html and "data-card-dot" not in html and "data-card-page" not in html
    assert len(elements_with(html, "data-swipe-area")) == 1


# --- The page does not scroll: on the rating page only -----------------------------------------------------------

def class_tokens(html):
    return {token for attributes, _ in elements_with(html, "class") for token in attributes["class"].split()}


def test_the_rating_page_has_the_no_scroll_class_and_the_css_uses_it():
    rules = [(selector, rule) for selector, rule in css_rules() if "rating-screen" in selector]
    assert rules, "app.css needs a rule for .rating-screen"
    joined = " ".join(rule for _, rule in rules)
    assert "overflow: hidden" in joined
    assert "100dvh" in joined


def test_the_one_card_rating_page_has_the_class(app, client):
    html, room_id, ids = rating_page(app, client)
    assert "rating-screen" in class_tokens(html)


def test_other_pages_do_not_have_the_class(app, client, google):
    room_id, ids = voting_room(app, client, place_ids=["place-a"], labels=["Burger Bar"])
    app.test_client().post(f"/rooms/{room_id}/join", data={"nickname": "Idle"})  # keeps the room open (B5)
    assert "rating-screen" not in class_tokens(page(client, f"/rooms/{room_id}/lobby"))
    for option_id in ids.values():
        rate(client, room_id, option_id)
    assert "You have rated all options." in page(client, f"/rooms/{room_id}/vote")
    assert "rating-screen" not in class_tokens(page(client, f"/rooms/{room_id}/vote"))  # the overview
    assert "rating-screen" not in class_tokens(page(client, f"/rooms/{room_id}"))
    client.post(f"/rooms/{room_id}/close")
    assert "rating-screen" not in class_tokens(page(client, f"/rooms/{room_id}/result"))


def test_the_room_page_before_voting_does_not_have_the_class(app, client):
    room_id = create_room(client)
    add_options(app, room_id, place_ids=["place-a"])
    assert "rating-screen" not in class_tokens(page(client, f"/rooms/{room_id}"))


# --- Slim line, close button and lobby link ------------------------------------------------------------------------

def test_the_slim_line_still_says_option_n_of_m(app, client):
    html, room_id, ids = rating_page(app, client, place_ids=("place-a", "place-b"))
    assert "Option 1 of 2" in html_lib.unescape(html)


def test_the_creator_can_reach_the_close_button_and_everyone_the_lobby_link(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    creator_html = page(client, f"/rooms/{room_id}/vote")
    assert f'action="/rooms/{room_id}/close"' in creator_html
    assert f'href="/rooms/{room_id}/lobby"' in creator_html
    guest = join_as_guest(app, room_id)
    guest_html = page(guest, f"/rooms/{room_id}/vote")
    assert f'href="/rooms/{room_id}/lobby"' in guest_html
    assert f'action="/rooms/{room_id}/close"' not in guest_html


def test_a_guest_cannot_close_the_room_by_post(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    guest = join_as_guest(app, room_id)
    guest.post(f"/rooms/{room_id}/close")
    with app.app_context():
        assert get_db().execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()["status"] == "voting"


# --- Rating and joker by the forms still work ----------------------------------------------------------------------------

def test_rating_by_the_form_still_works(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a"])
    join_as_guest(app, room_id, "Idle")  # keeps the room open when the only option is rated (B5)
    response = rate(client, room_id, ids["place-a"], "ok")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}/vote")
    with app.app_context():
        assert [tuple(row) for row in get_db().execute("SELECT option_id, rating FROM votes")] == [(ids["place-a"], "ok")]


def test_the_joker_form_still_works_once_per_participant_and_room(app, client):
    room_id, ids = voting_room(app, client, place_ids=["place-a", "place-b"])
    assert use_joker(client, room_id, ids["place-a"]).status_code in (302, 303)
    use_joker(client, room_id, ids["place-b"])  # second attempt: rejected with a message
    with app.app_context():
        assert [row["option_id"] for row in get_db().execute("SELECT option_id FROM vetoes")] == [ids["place-a"]]


# --- Google calls, key, escaping -------------------------------------------------------------------------------------------

def test_one_details_call_with_the_back_mask_per_rating_step(app, client, google):
    google.responses[DETAILS_URL + "place-b"] = FakeResponse(body=back_answer("place-b"))
    rating_page(app, client, place_ids=("place-a", "place-b"))
    assert google.detail_masks() == [BACK_FIELD_MASK]


def test_the_api_key_never_appears_in_the_page(app, client):
    html, room_id, ids = rating_page(app, client)
    assert FAKE_KEY not in html and "key=" not in html


def test_text_from_google_is_escaped_on_every_page_of_the_back(app, client, google):
    body = back_answer()
    body["editorialSummary"] = {"text": "<script>alert(1)</script>"}
    body["reviews"] = [review(1, text={"text": "<b>Great</b> & cheap"})]
    google.responses[DETAILS_URL + "place-a"] = FakeResponse(body=body)
    html, room_id, ids = rating_page(app, client)
    assert "<script>alert(1)</script>" not in html and "<b>Great</b>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in pages_of(html)["about"]
    assert "&lt;b&gt;Great&lt;/b&gt; &amp; cheap" in pages_of(html)["reviews"]


# --- CSS and swipe.js ----------------------------------------------------------------------------------------------------------

def test_the_css_makes_the_back_a_horizontal_scroll_snap_container():
    text = APP_CSS.read_text()
    assert "scroll-snap-type: x mandatory" in text
    assert "overflow-y: auto" in text  # long content scrolls inside a page


def test_swipe_js_handles_the_joker_question_the_dots_and_the_tap_on_the_back():
    source = SWIPE_JS.read_text()
    assert "[data-joker-question]" in source
    assert "[data-card-dot]" in source and "aria-current" in source
    assert "[data-card-back]" in source
    assert "[data-flip-toggle]" in source and ".click()" in source
    assert 'closest("a")' in source


def test_swipe_js_still_passes_the_a10_static_check():
    source = SWIPE_JS.read_text()
    for forbidden in ("fetch(", "XMLHttpRequest", "import ", "http"):
        assert forbidden not in source
