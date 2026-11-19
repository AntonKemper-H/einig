"""Tests for A11 – F28 hidden collecting (specs/a11-hidden-collecting.md, D17).

While a room is collecting, a participant sees only their own ideas when the room
keeps ideas secret, and nobody sees the suggested places when the room keeps them
secret. From "voting" on, everything is shown as before.

These tests never call Google: `requests.post` (Nearby Search) and `requests.get`
(Place Details) are replaced by fakes. The fake Place Details answer names every
place "Spot <place id>", so a test can tell whether a place is on the page.

The checks look for texts, form actions and status codes, not for the page layout,
so they stay true when B6 reorders the room page.
"""

import html as html_lib
import re

import pytest

from app import create_app
from app.db import get_db
from app.services import options as option_rules
from app.services import places, surprise

FAKE_KEY = "fake-key-for-tests-0123456789"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
LATITUDE = "38.737"
LONGITUDE = "-9.153"

HIDE_IDEAS_TEXT = "Keep everyone's ideas secret until voting"
REVEAL_PLACES_TEXT = "Show suggested places to everyone before voting"
SAME_IDEA_MESSAGE = "Someone already had the same idea – it is already in the room."
SECRET_PLACES_BEEN_THERE_MESSAGE = '"Been there" is not available while the suggested places are secret.'
PLACES_WAITING_TEXT = "5 suggested places are waiting – you will see them when the voting starts."

CREATOR_IDEA = "Secret Sushi"
GUEST_IDEA = "Hidden Tacos"


def others_text(count):
    """"Others have added 1 idea." / "Others have added 2 ideas."."""
    word = "idea" if count == 1 else "ideas"
    return f"Others have added {count} {word}."


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)
        self.content = b""
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post and requests.get.

    Nearby Search answers with 15 places named after the first requested type, so
    every surprise search finds enough places. Place Details answers every place id
    with the name "Spot <place id>".
    """

    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        place_type = kwargs["json"]["includedTypes"][0]
        return FakeResponse(body={"places": [{"id": f"{place_type}-{number}"} for number in range(15)]})

    def get(self, url, **kwargs):
        self.gets.append(url)
        if url.startswith(DETAILS_URL) and not url.endswith("/media"):
            place_id = url[len(DETAILS_URL):]
            return FakeResponse(body={"displayName": {"text": f"Spot {place_id}"}})
        return FakeResponse(status_code=404, body={"error": {}})

    def details_calls(self):
        return [url for url in self.gets if url.startswith(DETAILS_URL) and not url.endswith("/media")]


@pytest.fixture(autouse=True)
def google(app, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGoogle()
    monkeypatch.setattr(places.requests, "post", fake.post)
    monkeypatch.setattr(places.requests, "get", fake.get)
    return fake


# --- Helpers ---------------------------------------------------------------

def create_room(client, mode="manual", nickname="Anna"):
    response = client.post("/rooms", data={"title": "Friday plans", "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(app, room_id, nickname="Ben"):
    browser = app.test_client()
    response = browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)
    return browser


def save_setup(client, room_id, hide=None, reveal=None, marker=True, kind="food.brunch", options_per_person=""):
    """Post the setup form. A checkbox is sent only when it is ticked (hide/reveal True)."""
    data = {"kind": kind, "options_per_person": options_per_person}
    if marker:
        data["privacy_choices"] = "1"
    if hide:
        data["hide_ideas"] = "1"
    if reveal:
        data["reveal_places"] = "1"
    return client.post(f"/rooms/{room_id}/setup", data=data)


def add_option(client, room_id, label):
    return client.post(f"/rooms/{room_id}/options", data={"label": label})


def surprise_me(client, room_id):
    form = {"radius_m": "1000", "latitude": LATITUDE, "longitude": LONGITUDE, "min_rating": "", "max_price_level": ""}
    response = client.post(f"/rooms/{room_id}/surprise", data=form)
    assert response.status_code in (302, 303)
    return response


def page(client, room_id):
    return client.get(f"/rooms/{room_id}").data.decode()


def input_tag(html, name):
    """The <input ...> tag with this name, or None."""
    match = re.search(rf'<input\b[^>]*\bname="{re.escape(name)}"[^>]*>', html)
    return None if match is None else match.group(0)


def is_checked(tag):
    return tag is not None and re.search(r"\bchecked\b", tag) is not None


def run_sql(app, sql, params=()):
    with app.app_context():
        connection = get_db()
        connection.execute(sql, params)
        connection.commit()


def query(app, sql, params=()):
    with app.app_context():
        return get_db().execute(sql, params).fetchall()


def setup_row(app, room_id):
    rows = query(app, "SELECT * FROM room_setups WHERE room_id = ?", (room_id,))
    return rows[0] if rows else None


def active_options(app, room_id):
    return query(app, "SELECT * FROM options WHERE room_id = ? AND is_replaced = 0 ORDER BY id", (room_id,))


def option_id_of(app, room_id, label):
    return query(app, "SELECT id FROM options WHERE room_id = ? AND label = ?", (room_id, label))[0]["id"]


def place_ids(app, room_id):
    return [row["place_id"] for row in active_options(app, room_id) if row["source"] == "google"]


def snapshot(app):
    """Every row that A11's routes could change, to prove nothing changed."""
    tables = {
        "rooms": "SELECT * FROM rooms ORDER BY id",
        "options": "SELECT * FROM options ORDER BY id",
        "option_authors": "SELECT * FROM option_authors ORDER BY option_id",
        "room_setups": "SELECT * FROM room_setups ORDER BY room_id",
        "votes": "SELECT * FROM votes ORDER BY id",
    }
    return {table: [tuple(row) for row in query(app, sql)] for table, sql in tables.items()}


def shows_place(html, place_id):
    return f"Spot {place_id}" in html


def without_typed_label(html, label):
    """The page without the add form's pre-filled value, so only shown options remain."""
    return html.replace(f'value="{label}"', "")


@pytest.fixture
def hidden_room(app, client):
    """A manual room with secret ideas: Anna (creator, `client`) and Ben (guest) each added one idea."""
    room_id = create_room(client)
    assert save_setup(client, room_id, hide=True).status_code in (302, 303)
    guest = join(app, room_id)
    assert add_option(client, room_id, CREATOR_IDEA).status_code in (302, 303)
    assert add_option(guest, room_id, GUEST_IDEA).status_code in (302, 303)
    return {"id": room_id, "guest": guest}


@pytest.fixture
def secret_surprise_room(app, client):
    """A surprise room with secret ideas and secret places, a limit of 1 option per person.

    Anna (creator) added an idea and ran "Surprise me" (5 places); Ben (guest) added an idea.
    """
    room_id = create_room(client, mode="surprise")
    assert save_setup(client, room_id, hide=True, reveal=False, options_per_person="1").status_code in (302, 303)
    guest = join(app, room_id)
    assert add_option(client, room_id, CREATOR_IDEA).status_code in (302, 303)
    surprise_me(client, room_id)
    assert add_option(guest, room_id, GUEST_IDEA).status_code in (302, 303)
    assert len(place_ids(app, room_id)) == surprise.SURPRISE_OPTION_COUNT
    return {"id": room_id, "guest": guest}


# --- visible_options (pure function) ------------------------------------------

OPTIONS = [
    {"id": 1, "source": "manual", "added_by": 7},     # own typed idea
    {"id": 2, "source": "manual", "added_by": 8},     # someone else's typed idea
    {"id": 3, "source": "google", "added_by": None},  # suggested place
    {"id": 4, "source": "google", "added_by": 7},     # own place found by name
    {"id": 5, "source": "google", "added_by": 8},     # someone else's place found by name
    {"id": 6, "source": "google", "added_by": None},  # suggested place
]


@pytest.mark.parametrize(
    "hide_ideas, reveal_places, shown_ids, hidden_ideas, hidden_places",
    [
        (False, True, [1, 2, 3, 4, 5, 6], 0, 0),
        (False, False, [1, 2, 4, 5], 0, 2),
        (True, True, [1, 3, 4, 6], 2, 0),
        (True, False, [1, 4], 2, 2),
    ],
)
def test_visible_options_follows_the_table(hide_ideas, reveal_places, shown_ids, hidden_ideas, hidden_places):
    shown, idea_count, place_count = option_rules.visible_options(OPTIONS, 7, hide_ideas, reveal_places)
    assert [option["id"] for option in shown] == shown_ids
    assert (idea_count, place_count) == (hidden_ideas, hidden_places)


# --- The two choices in the setup form ------------------------------------------------

def test_setup_form_without_setup_has_both_choices_checked(client):
    room_id = create_room(client, mode="surprise")
    html = page(client, room_id)
    assert HIDE_IDEAS_TEXT in html
    assert REVEAL_PLACES_TEXT in html
    assert is_checked(input_tag(html, "hide_ideas"))
    assert is_checked(input_tag(html, "reveal_places"))
    assert input_tag(html, "privacy_choices") is not None


def test_setup_form_has_no_places_choice_in_manual_room(client):
    room_id = create_room(client, mode="manual")
    html = page(client, room_id)
    assert is_checked(input_tag(html, "hide_ideas"))
    assert REVEAL_PLACES_TEXT not in html
    assert input_tag(html, "reveal_places") is None


def test_saving_the_choices(app, client):
    room_id = create_room(client, mode="surprise")
    save_setup(client, room_id, hide=True, reveal=False)
    row = setup_row(app, room_id)
    assert (row["hide_ideas"], row["reveal_places"]) == (1, 0)
    # The form shows the saved values.
    html = page(client, room_id)
    assert is_checked(input_tag(html, "hide_ideas"))
    assert not is_checked(input_tag(html, "reveal_places"))

    # With the marker and without the fields: both unticked.
    save_setup(client, room_id, hide=False, reveal=False)
    row = setup_row(app, room_id)
    assert (row["hide_ideas"], row["reveal_places"]) == (0, 0)

    # Without the marker (like C9's tests): the stored values stay as they are.
    save_setup(client, room_id, hide=True, reveal=True, marker=False, kind="drinks.bar")
    row = setup_row(app, room_id)
    assert (row["hide_ideas"], row["reveal_places"]) == (0, 0)
    assert row["kind"] == "bar"


def test_new_setup_without_marker_keeps_the_defaults(app, client):
    room_id = create_room(client, mode="surprise")
    save_setup(client, room_id, hide=True, reveal=False, marker=False)
    row = setup_row(app, room_id)
    assert (row["hide_ideas"], row["reveal_places"]) == (0, 1)


def test_manual_room_stores_reveal_places_as_1(app, client):
    room_id = create_room(client, mode="manual")
    save_setup(client, room_id, hide=True, reveal=False)
    row = setup_row(app, room_id)
    assert (row["hide_ideas"], row["reveal_places"]) == (1, 1)


def test_choices_only_by_the_creator_and_only_while_collecting(app, client):
    room_id = create_room(client)
    guest = join(app, room_id)
    before = snapshot(app)
    assert save_setup(guest, room_id, hide=True).status_code == 403
    assert snapshot(app) == before

    run_sql(app, "UPDATE rooms SET status = 'voting' WHERE id = ?", (room_id,))
    before = snapshot(app)
    assert save_setup(client, room_id, hide=True).status_code == 400
    assert snapshot(app) == before


# --- Who sees what while collecting ---------------------------------------------------

def test_each_participant_sees_only_their_own_idea(hidden_room, client):
    creator_page = page(client, hidden_room["id"])
    assert CREATOR_IDEA in creator_page
    assert GUEST_IDEA not in creator_page
    assert others_text(1) in creator_page

    guest_page = page(hidden_room["guest"], hidden_room["id"])
    assert GUEST_IDEA in guest_page
    assert CREATOR_IDEA not in guest_page
    assert others_text(1) in guest_page


def test_count_text_uses_plural(app, hidden_room, client):
    third = join(app, hidden_room["id"], "Cara")
    add_option(third, hidden_room["id"], "Quiet Ramen")
    assert others_text(2) in page(client, hidden_room["id"])


def test_visitor_sees_no_options(app, hidden_room):
    html = page(app.test_client(), hidden_room["id"])
    assert CREATOR_IDEA not in html
    assert GUEST_IDEA not in html


@pytest.mark.parametrize("with_setup", [True, False])
def test_without_hidden_ideas_everyone_sees_everything(app, client, with_setup):
    room_id = create_room(client)
    if with_setup:
        save_setup(client, room_id, hide=False)
    guest = join(app, room_id)
    add_option(client, room_id, CREATOR_IDEA)
    add_option(guest, room_id, GUEST_IDEA)
    for browser in (client, guest):
        html = page(browser, room_id)
        assert CREATOR_IDEA in html
        assert GUEST_IDEA in html
        assert "Others have added" not in html


def test_secret_places_are_hidden_from_everyone(app, client, google, secret_surprise_room):
    room_id = secret_surprise_room["id"]
    for browser in (client, secret_surprise_room["guest"]):
        calls_before = len(google.details_calls())
        html = page(browser, room_id)
        assert PLACES_WAITING_TEXT in html
        assert not any(shows_place(html, place_id) for place_id in place_ids(app, room_id))
        assert "Been there" not in html
        # Hidden places cost nothing: no Place Details call on the room page.
        assert len(google.details_calls()) == calls_before


def test_revealed_places_are_shown_with_been_there(app, client):
    room_id = create_room(client, mode="surprise")
    save_setup(client, room_id, hide=True, reveal=True)
    guest = join(app, room_id)
    surprise_me(client, room_id)
    for browser in (client, guest):
        html = page(browser, room_id)
        for row in active_options(app, room_id):
            assert shows_place(html, row["place_id"])
            assert f'action="/rooms/{room_id}/options/{row["id"]}/been-there"' in html
        assert "suggested places are waiting" not in html


# --- Rejected and ignored actions -------------------------------------------------------

def test_been_there_on_a_secret_place_is_rejected(app, google, secret_surprise_room):
    room_id = secret_surprise_room["id"]
    option = active_options(app, room_id)[1]
    assert option["source"] == "google"
    before = snapshot(app)
    posts_before = len(google.posts)

    response = secret_surprise_room["guest"].post(f"/rooms/{room_id}/options/{option['id']}/been-there")
    assert response.status_code == 400
    # Jinja escapes the quotes (&#34;), so compare the unescaped text.
    assert SECRET_PLACES_BEEN_THERE_MESSAGE in html_lib.unescape(response.data.decode())
    assert snapshot(app) == before
    assert len(google.posts) == posts_before


def test_same_label_as_a_hidden_idea_is_rejected(app, hidden_room):
    room_id = hidden_room["id"]
    before = snapshot(app)
    response = add_option(hidden_room["guest"], room_id, CREATOR_IDEA)
    html = response.data.decode()
    assert response.status_code == 400
    assert SAME_IDEA_MESSAGE in html
    assert CREATOR_IDEA not in without_typed_label(html, CREATOR_IDEA)
    assert snapshot(app) == before
    assert CREATOR_IDEA not in page(hidden_room["guest"], room_id)


def test_same_label_as_own_idea_keeps_the_normal_message(app, hidden_room):
    before = snapshot(app)
    response = add_option(hidden_room["guest"], hidden_room["id"], GUEST_IDEA)
    html = response.data.decode()
    assert response.status_code == 400
    assert option_rules.DUPLICATE_MESSAGE in html
    assert SAME_IDEA_MESSAGE not in html
    assert snapshot(app) == before


def test_deleting_a_hidden_option_is_ignored_like_an_unknown_one(app, client, secret_surprise_room):
    room_id = secret_surprise_room["id"]
    guest_idea = option_id_of(app, room_id, GUEST_IDEA)
    secret_place = next(row["id"] for row in active_options(app, room_id) if row["source"] == "google")
    unknown = client.post(f"/rooms/{room_id}/options/999999/delete")
    before = snapshot(app)

    for option_id in (guest_idea, secret_place):
        response = client.post(f"/rooms/{room_id}/options/{option_id}/delete")
        assert response.status_code == unknown.status_code == 303
        assert response.headers["Location"] == unknown.headers["Location"]
        assert response.data == unknown.data
    assert snapshot(app) == before


def test_deleting_own_idea_in_a_hidden_room_works(app, hidden_room):
    room_id = hidden_room["id"]
    option_id = option_id_of(app, room_id, GUEST_IDEA)
    response = hidden_room["guest"].post(f"/rooms/{room_id}/options/{option_id}/delete")
    assert response.status_code == 303
    assert [row["label"] for row in active_options(app, room_id)] == [CREATOR_IDEA]


def test_rejected_actions_do_not_leak_hidden_options(app, secret_surprise_room):
    room_id = secret_surprise_room["id"]
    guest = secret_surprise_room["guest"]
    secret_place = next(row["id"] for row in active_options(app, room_id) if row["source"] == "google")
    responses = [
        add_option(guest, room_id, "One more idea"),  # over the limit of 1
        add_option(guest, room_id, ""),  # empty label
        guest.post(f"/rooms/{room_id}/options/{secret_place}/been-there"),
        guest.post(f"/rooms/{room_id}/find", data={"name": ""}),
    ]
    for response in responses:
        html = response.data.decode()
        assert response.status_code == 400
        assert CREATOR_IDEA not in html
        assert not any(shows_place(html, place_id) for place_id in place_ids(app, room_id))
        assert others_text(1) in html
        assert PLACES_WAITING_TEXT in html


# --- After the voting starts ------------------------------------------------------------

def rate_everything(browser, room_id):
    """Rate every card on the one-card rating page.

    Returns the option ids in the order they were shown, and the page after the last
    rating (the overview, which may again contain rating forms for options already rated).
    """
    shown = []
    for _ in range(50):
        html = browser.get(f"/rooms/{room_id}/vote").data.decode()
        match = re.search(r'name="option_id" value="(\d+)"', html)
        if match is None or int(match.group(1)) in shown:
            return shown, html
        option_id = int(match.group(1))
        shown.append(option_id)
        response = browser.post(f"/rooms/{room_id}/vote", data={"option_id": option_id, "rating": "yes"})
        assert response.status_code in (302, 303)
    raise AssertionError("the rating page never ended")


def test_after_start_everyone_rates_every_option(app, client, secret_surprise_room):
    room_id = secret_surprise_room["id"]
    assert client.post(f"/rooms/{room_id}/start").status_code in (302, 303)
    all_ids = {row["id"] for row in active_options(app, room_id)}
    assert len(all_ids) == 2 + surprise.SURPRISE_OPTION_COUNT

    shown, overview = rate_everything(secret_surprise_room["guest"], room_id)
    assert set(shown) == all_ids
    # The overview shows every option, also the creator's idea and the places.
    assert CREATOR_IDEA in overview
    assert all(shows_place(overview, place_id) for place_id in place_ids(app, room_id))


def test_overview_and_result_never_show_who_added_an_option(app, client, hidden_room):
    room_id = hidden_room["id"]
    guest = hidden_room["guest"]
    client.post(f"/rooms/{room_id}/start")
    _, overview = rate_everything(guest, room_id)
    assert "Anna" not in overview
    rate_everything(client, room_id)  # the last rating closes the room (B5)
    for browser, other in ((client, "Ben"), (guest, "Anna")):
        result = browser.get(f"/rooms/{room_id}/result").data.decode()
        assert CREATOR_IDEA in result and GUEST_IDEA in result
        assert other not in result


def test_lobby_shows_the_full_number_of_options(hidden_room):
    html = hidden_room["guest"].get(f"/rooms/{hidden_room['id']}/lobby").data.decode()
    assert "2 options" in html


# --- Changing the choice, persistence ----------------------------------------------------

def test_turning_hidden_ideas_off_shows_everything(app, client, hidden_room):
    room_id = hidden_room["id"]
    assert CREATOR_IDEA not in page(hidden_room["guest"], room_id)
    assert save_setup(client, room_id, hide=False).status_code in (302, 303)
    html = page(hidden_room["guest"], room_id)
    assert CREATOR_IDEA in html and GUEST_IDEA in html
    assert len(active_options(app, room_id)) == 2


def test_choices_survive_a_restart(app, hidden_room):
    restarted = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
            "GOOGLE_MAPS_API_KEY": FAKE_KEY,
        }
    )
    browser = restarted.test_client()
    browser.set_cookie("session", hidden_room["guest"].get_cookie("session").value)
    html = page(browser, hidden_room["id"])
    assert GUEST_IDEA in html
    assert CREATOR_IDEA not in html
    assert others_text(1) in html
