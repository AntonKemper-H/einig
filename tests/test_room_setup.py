"""Tests for C9 – F27 room setup: activity, kind and options per person (specs/c9-room-setup.md).

These tests never call Google: `requests.post` (Nearby Search and Text Search) is
replaced by a fake, and the root conftest.py makes every other request fail, so the
cards fall back to "Place from Google Maps".
"""

import json
import re
import sqlite3

import pytest

from app import create_app
from app import db as database
from app.db import get_db
from app.services import activities, places, surprise

FAKE_KEY = "fake-key-for-tests-0123456789"
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
LATITUDE = "38.737"
LONGITUDE = "-9.153"

ONLY_CREATOR_MESSAGE = "Only the creator can set up the room."
NOT_COLLECTING_SETUP_MESSAGE = "The setup can only be changed before voting starts."
KIND_MESSAGE = "Please choose an activity."
OPTIONS_PER_PERSON_MESSAGE = "Please choose how many options each person can add."
ALREADY_SEARCHED_TEXT = "The places were already suggested. Changing the activity does not search again."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
DUPLICATE_LABEL_MESSAGE = "This option is already in the list."
ALREADY_OPTION_MESSAGE = "This place is already an option."
CATEGORY_MESSAGE = "Please choose a category."

BRUNCH_LINE = "Activity: Food – Brunch · Up to 3 options per person"

MATCHES = [
    {"id": "place-luigi-1", "displayName": {"text": "Trattoria Luigi"}, "formattedAddress": "Rua Augusta 10"},
    {"id": "place-luigi-2", "displayName": {"text": "Luigi Gelateria"}, "formattedAddress": "Avenida 5"},
]


def limit_message(limit):
    """"You can add at most 3 options in this room." (also accepts "1 option" for a limit of 1)."""
    return f"You can add at most {limit} option"


def at_limit_text(limit):
    """"You have added 3 of 3 options." (also accepts "1 of 1 option")."""
    return f"You have added {limit} of {limit} option"


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGoogle:
    """Replaces requests.post.

    Text Search answers with MATCHES; Nearby Search answers with 15 places named
    after the first requested type, so every search finds enough places.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if url == TEXT_SEARCH_URL:
            return FakeResponse(body={"places": MATCHES})
        place_type = kwargs["json"]["includedTypes"][0]
        return FakeResponse(body={"places": [{"id": f"{place_type}-{number}"} for number in range(15)]})

    def nearby_searches(self):
        return [call for call in self.calls if call["url"] == NEARBY_URL]

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

def create_room(client, mode="manual", title="Sunday plans", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def save_setup(client, room_id, kind="food.brunch", options_per_person="3"):
    return client.post(
        f"/rooms/{room_id}/setup", data={"kind": kind, "options_per_person": options_per_person}
    )


def add_option(client, room_id, label):
    return client.post(f"/rooms/{room_id}/options", data={"label": label})


def find(client, room_id, name="Trattoria Luigi"):
    return client.post(f"/rooms/{room_id}/find", data={"name": name})


def add_found(client, room_id, place_id="place-luigi-1"):
    return client.post(f"/rooms/{room_id}/find/add", data={"place_id": place_id})


def search_form(**changes):
    form = {
        "radius_m": "1000",
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "min_rating": "",
        "max_price_level": "",
    }
    form.update(changes)
    return form


def suggest(client, room_id, **changes):
    return client.post(f"/rooms/{room_id}/suggest", data=search_form(**changes))


def surprise_me(client, room_id, **changes):
    return client.post(f"/rooms/{room_id}/surprise", data=search_form(**changes))


def page(client, room_id):
    return client.get(f"/rooms/{room_id}").data.decode()


def setup_action(room_id):
    return f'action="/rooms/{room_id}/setup"'


def add_action(room_id):
    return f'action="/rooms/{room_id}/options"'


def find_action(room_id):
    return f'action="/rooms/{room_id}/find"'


def setup_details_tag(html, room_id):
    """The opening <details ...> tag of the section that holds the setup form."""
    form_position = html.index(setup_action(room_id))
    start = html.rindex("<details", 0, form_position)
    return html[start : html.index(">", start) + 1]


def is_selected(html, value):
    """True if an <option> with this value is marked as selected."""
    return re.search(rf'<option value="{re.escape(value)}"[^>]*\bselected\b', html) is not None


def run_sql(app, sql, params=()):
    with app.app_context():
        connection = get_db()
        connection.execute(sql, params)
        connection.commit()


def set_room_status(app, room_id, status):
    run_sql(app, "UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))


def setup_rows(app, room_id=None):
    with app.app_context():
        if room_id is None:
            return get_db().execute("SELECT * FROM room_setups ORDER BY room_id").fetchall()
        return get_db().execute("SELECT * FROM room_setups WHERE room_id = ?", (room_id,)).fetchall()


def all_options(app, room_id):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def author_count(app, room_id, participant):
    with app.app_context():
        return get_db().execute(
            "SELECT COUNT(*) AS n FROM option_authors WHERE room_id = ? AND participant_id = ?",
            (room_id, participant),
        ).fetchone()["n"]


def participant_id(app, room_id, nickname):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM participants WHERE room_id = ? AND nickname = ?", (room_id, nickname)
        ).fetchone()["id"]


def room_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def snapshot(app):
    """Every row of every table that C9 could change, to prove nothing changed."""
    with app.app_context():
        connection = get_db()
        queries = {
            "rooms": "SELECT * FROM rooms ORDER BY id",
            "options": "SELECT * FROM options ORDER BY id",
            "option_authors": "SELECT * FROM option_authors ORDER BY option_id",
            "room_setups": "SELECT * FROM room_setups ORDER BY room_id",
        }
        return {
            table: [tuple(row) for row in connection.execute(sql)] for table, sql in queries.items()
        }


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


def pretend_room_is_collecting(monkeypatch):
    """The route sees "collecting", as if the voting started right after its checks."""
    real_get_room = database.get_room
    monkeypatch.setattr(
        database, "get_room", lambda wanted: {**dict(real_get_room(wanted)), "status": "collecting"}
    )


def pretend_route_sees_below_limit(monkeypatch):
    """The route's fast check (activities.limit_reached) says "below the limit".

    Only the route uses limit_reached; the database functions count option_authors
    themselves, so their check inside the transaction still sees the real number.
    """
    monkeypatch.setattr(activities, "limit_reached", lambda *args, **kwargs: False)


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


# --- Schema ----------------------------------------------------------------

def test_new_database_has_room_setups_table(app):
    with app.app_context():
        columns = [row[1] for row in get_db().execute("PRAGMA table_info(room_setups)")]
    assert columns == [
        "room_id",
        "activity",
        "kind",
        "options_per_person",
        "hide_ideas",
        "reveal_places",
    ]


def test_init_db_adds_missing_table_and_keeps_rooms(app, runner, client, room_id):
    run_sql(app, "DROP TABLE room_setups")
    rooms_before = [tuple(room_row(app, room_id))]
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0
    assert [tuple(room_row(app, room_id))] == rooms_before
    assert setup_rows(app) == []
    assert_redirects_to_room(save_setup(client, room_id), room_id)
    assert len(setup_rows(app, room_id)) == 1


def test_deleting_a_room_deletes_its_setup(app, client, room_id):
    save_setup(client, room_id)
    run_sql(app, "DELETE FROM rooms WHERE id = ?", (room_id,))
    assert setup_rows(app) == []


def test_database_refuses_invalid_values(app, room_id):
    with app.app_context():
        connection = get_db()
        for values in [
            (room_id, "", "brunch", 3),
            (room_id, "food", "  ", 3),
            (room_id, "food", "brunch", 0),
            (room_id, "food", "brunch", 6),
        ]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO room_setups (room_id, activity, kind, options_per_person)"
                    " VALUES (?, ?, ?, ?)",
                    values,
                )
            connection.rollback()


# --- Accepted --------------------------------------------------------------

def test_creator_saves_setup_and_everyone_sees_it(app, client, guest, room_id):
    response = save_setup(client, room_id)
    assert_redirects_to_room(response, room_id)

    rows = setup_rows(app, room_id)
    assert len(rows) == 1
    row = rows[0]
    assert (row["activity"], row["kind"], row["options_per_person"]) == ("food", "brunch", 3)
    # A11 uses these two; C9 only creates them with today's behaviour.
    assert (row["hide_ideas"], row["reveal_places"]) == (0, 1)

    for browser in (client, guest):
        assert BRUNCH_LINE in page(browser, room_id)


def test_setup_without_limit_shows_only_activity(client, guest, room_id):
    save_setup(client, room_id, kind="sport.bowling", options_per_person="")
    html = page(guest, room_id)
    assert "Activity: Sport – Bowling" in html
    assert "options per person" not in html


def test_saving_again_replaces_setup(app, client, room_id):
    save_setup(client, room_id)
    # Pretend A11 changed these: saving the C9 form must leave them alone.
    run_sql(app, "UPDATE room_setups SET hide_ideas = 1, reveal_places = 0 WHERE room_id = ?", (room_id,))
    assert_redirects_to_room(save_setup(client, room_id, kind="culture.museum", options_per_person=""), room_id)

    rows = setup_rows(app, room_id)
    assert len(rows) == 1
    row = rows[0]
    assert (row["activity"], row["kind"], row["options_per_person"]) == ("culture", "museum", None)
    assert (row["hide_ideas"], row["reveal_places"]) == (1, 0)


# --- Rejected ----------------------------------------------------------------

def test_unknown_room_is_404(client):
    assert save_setup(client, "no-such-room").status_code == 404


def test_guest_visitor_and_other_room_are_rejected(app, client, guest, visitor, room_id):
    other_room = create_room(client, title="Other room")
    stranger = app.test_client()
    join(stranger, other_room, "Cleo")
    before = snapshot(app)
    for browser in (guest, visitor, stranger):
        response = save_setup(browser, room_id)
        assert response.status_code == 403
        assert ONLY_CREATOR_MESSAGE in response.data.decode()
    assert snapshot(app) == before
    assert setup_rows(app) == []


@pytest.mark.parametrize("kind", ["food.pizza", "", "nonsense"])
def test_invalid_kind_is_rejected_and_values_shown_again(app, client, room_id, kind):
    before = snapshot(app)
    response = save_setup(client, room_id, kind=kind, options_per_person="3")
    html = response.data.decode()
    assert response.status_code == 400
    assert KIND_MESSAGE in html
    assert is_selected(html, "3")
    assert snapshot(app) == before


@pytest.mark.parametrize("value", ["0", "6", "abc", "2.5"])
def test_invalid_options_per_person_is_rejected_and_values_shown_again(app, client, room_id, value):
    before = snapshot(app)
    response = save_setup(client, room_id, kind="food.brunch", options_per_person=value)
    html = response.data.decode()
    assert response.status_code == 400
    assert OPTIONS_PER_PERSON_MESSAGE in html
    assert is_selected(html, "food.brunch")
    assert snapshot(app) == before


def test_missing_fields_are_rejected(app, client, room_id):
    before = snapshot(app)
    response = client.post(f"/rooms/{room_id}/setup", data={})
    html = response.data.decode()
    assert response.status_code == 400
    assert KIND_MESSAGE in html
    assert OPTIONS_PER_PERSON_MESSAGE in html
    assert snapshot(app) == before


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_setup_rejected_when_not_collecting(app, client, room_id, status):
    save_setup(client, room_id)
    set_room_status(app, room_id, status)
    before = snapshot(app)
    response = save_setup(client, room_id, kind="sport.bowling", options_per_person="1")
    assert response.status_code == 400
    assert NOT_COLLECTING_SETUP_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_voting_starts_just_before_setup_is_saved(app, client, room_id, monkeypatch):
    set_room_status(app, room_id, "voting")
    pretend_room_is_collecting(monkeypatch)
    before = snapshot(app)
    response = save_setup(client, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_SETUP_MESSAGE in response.data.decode()
    assert snapshot(app) == before
    with app.app_context():
        assert database.save_room_setup(room_id, "food", "brunch", 3) is False
    assert setup_rows(app) == []


# --- Room page -----------------------------------------------------------------

def test_creator_form_open_before_first_save_and_prefilled_after(client, guest, room_id):
    html = page(client, room_id)
    assert setup_action(room_id) in html
    assert "Set up this room" in html
    assert "Save setup" in html
    assert "open" in setup_details_tag(html, room_id)
    # Every activity is an optgroup, every kind an option.
    assert '<optgroup label="Food">' in html
    assert 'value="food.brunch"' in html

    save_setup(client, room_id)
    html = page(client, room_id)
    assert "open" not in setup_details_tag(html, room_id)
    assert "Food – Brunch" in html
    assert is_selected(html, "food.brunch")
    assert is_selected(html, "3")

    assert setup_action(room_id) not in page(guest, room_id)


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_no_setup_form_after_collecting(app, client, room_id, status):
    set_room_status(app, room_id, status)
    assert setup_action(room_id) not in page(client, room_id)


def test_visitor_sees_no_setup(client, visitor, room_id):
    save_setup(client, room_id)
    html = page(visitor, room_id)
    assert setup_action(room_id) not in html
    assert "Activity:" not in html


@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_room_without_setup_is_unchanged(app, client, mode):
    room_id = create_room(client, mode=mode)
    guest = app.test_client()
    join(guest, room_id, "Ben")
    html = page(client, room_id)
    assert "Activity:" not in html
    assert "options added" not in html
    if mode != "manual":
        assert 'name="category"' in html
        assert "Searching for:" not in html
    for label in ["One", "Two", "Three", "Four", "Five", "Six"]:
        assert_redirects_to_room(add_option(guest, room_id, label), room_id)
    assert len(all_options(app, room_id)) == 6
    assert add_action(room_id) in page(guest, room_id)


# --- Searches in a set-up room ---------------------------------------------------

def test_nearby_search_uses_kind_types(app, client, google):
    room_id = create_room(client, mode="nearby")
    save_setup(client, room_id, kind="food.brunch", options_per_person="")
    html = page(client, room_id)
    assert f'action="/rooms/{room_id}/suggest"' in html
    assert 'name="category"' not in html
    assert "Searching for: Food – Brunch" in html
    assert 'name="radius_m"' in html

    # A posted category is ignored.
    response = suggest(client, room_id, category="bar")
    assert_redirects_to_room(response, room_id)
    searches = google.nearby_searches()
    assert len(searches) == 1
    assert sorted(searches[0]["json"]["includedTypes"]) == sorted(activities.kind_types("food", "brunch"))

    filters = json.loads(room_row(app, room_id)["filters"])
    assert filters["kind"] == "food.brunch"
    assert filters["category"] is None
    assert all_options(app, room_id)


def test_nearby_search_without_category_is_accepted(app, client, google):
    room_id = create_room(client, mode="nearby")
    save_setup(client, room_id, kind="sport.bowling", options_per_person="")
    response = suggest(client, room_id)
    assert_redirects_to_room(response, room_id)
    assert CATEGORY_MESSAGE not in response.data.decode()
    assert len(google.nearby_searches()) == 1


def test_surprise_search_uses_only_kind_types(app, client, google):
    room_id = create_room(client, mode="surprise")
    save_setup(client, room_id, kind="drinks.bar", options_per_person="")
    html = page(client, room_id)
    assert 'name="category"' not in html
    assert "Searching for: Drinks &amp; café – Bar" in html or "Searching for: Drinks & café – Bar" in html

    response = surprise_me(client, room_id, category="restaurant")
    assert_redirects_to_room(response, room_id)
    kind_types = set(activities.kind_types("drinks", "bar"))
    searches = google.nearby_searches()
    # The fake finds 15 places per type, so one round is enough.
    assert 1 <= len(searches) <= surprise.SUBCATEGORIES_PER_SEARCH
    for call in searches:
        assert len(call["json"]["includedTypes"]) == 1
        assert call["json"]["includedTypes"][0] in kind_types
    for option in all_options(app, room_id):
        assert option["category"] in kind_types

    filters = json.loads(room_row(app, room_id)["filters"])
    assert filters["kind"] == "drinks.bar"
    assert filters["category"] is None


def test_changing_setup_after_search_does_not_search_again(app, client, google):
    room_id = create_room(client, mode="nearby")
    save_setup(client, room_id, kind="food.brunch", options_per_person="")
    suggest(client, room_id)
    calls_before = len(google.calls)
    options_before = [tuple(row) for row in all_options(app, room_id)]

    assert ALREADY_SEARCHED_TEXT in page(client, room_id)
    assert_redirects_to_room(save_setup(client, room_id, kind="culture.museum", options_per_person=""), room_id)
    page(client, room_id)
    assert len(google.nearby_searches()) == 1
    assert len(google.calls) == calls_before
    assert [tuple(row) for row in all_options(app, room_id)] == options_before
    assert setup_rows(app, room_id)[0]["kind"] == "museum"


def test_been_there_in_set_up_surprise_room_searches_same_type(app, client, google):
    room_id = create_room(client, mode="surprise")
    save_setup(client, room_id, kind="sport.bowling", options_per_person="")
    surprise_me(client, room_id)
    option = all_options(app, room_id)[0]
    calls_before = len(google.nearby_searches())

    response = client.post(f"/rooms/{room_id}/options/{option['id']}/been-there")
    assert_redirects_to_room(response, room_id)
    new_searches = google.nearby_searches()[calls_before:]
    assert new_searches
    assert new_searches[0]["json"]["includedTypes"] == [option["category"]]
    rows = all_options(app, room_id)
    assert [row["is_replaced"] for row in rows if row["id"] == option["id"]] == [1]
    assert sum(1 for row in rows if not row["is_replaced"]) == surprise.SURPRISE_OPTION_COUNT


# --- Limit: typed options ----------------------------------------------------------

def test_third_option_rejected_with_limit_of_two(app, client, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="2")
    ben = app.test_client()
    join(ben, room_id, "Ben")
    cleo = app.test_client()
    join(cleo, room_id, "Cleo")

    assert_redirects_to_room(add_option(ben, room_id, "Café Central"), room_id)
    assert_redirects_to_room(add_option(ben, room_id, "Bakery Lux"), room_id)
    before = snapshot(app)
    response = add_option(ben, room_id, "Brunch Club")
    assert response.status_code == 400
    assert limit_message(2) in response.data.decode()
    assert snapshot(app) == before

    assert_redirects_to_room(add_option(cleo, room_id, "Brunch Club"), room_id)
    assert_redirects_to_room(add_option(cleo, room_id, "Pancake House"), room_id)
    assert author_count(app, room_id, participant_id(app, room_id, "Ben")) == 2
    assert author_count(app, room_id, participant_id(app, room_id, "Cleo")) == 2


def test_database_holds_limit_when_route_check_misses_it(app, client, guest, room_id, monkeypatch):
    save_setup(client, room_id, kind="food.brunch", options_per_person="2")
    add_option(guest, room_id, "One")
    add_option(guest, room_id, "Two")
    # The route's fast check sees "below the limit", as if the other add came a moment later.
    # Only the route's check is patched: the count inside the database transaction stays real.
    pretend_route_sees_below_limit(monkeypatch)
    before = snapshot(app)
    response = add_option(guest, room_id, "Three")
    assert response.status_code == 400
    assert limit_message(2) in response.data.decode()
    assert snapshot(app) == before
    assert author_count(app, room_id, participant_id(app, room_id, "Ben")) == 2


def test_add_manual_option_within_limit_results(app, client, guest, room_id):
    ben = participant_id(app, room_id, "Ben")
    with app.app_context():
        assert database.add_manual_option_within_limit(room_id, "One", ben, 2) == "added"
        assert database.add_manual_option_within_limit(room_id, "Two", ben, 2) == "added"
        assert database.count_own_options(room_id, ben) == 2

    before = snapshot(app)
    with app.app_context():
        assert database.add_manual_option_within_limit(room_id, "Three", ben, 2) == "limit"
    assert snapshot(app) == before

    with app.app_context():
        assert database.add_manual_option_within_limit(room_id, "One", ben, 5) == "duplicate"
    assert snapshot(app) == before

    set_room_status(app, room_id, "voting")
    before = snapshot(app)
    with app.app_context():
        assert database.add_manual_option_within_limit(room_id, "Four", ben, 5) == "not_collecting"
    assert snapshot(app) == before


def test_duplicate_and_not_collecting_keep_their_messages_with_limit(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="3")
    add_option(guest, room_id, "Café Central")
    before = snapshot(app)
    response = add_option(guest, room_id, "café central")
    assert response.status_code == 400
    assert DUPLICATE_LABEL_MESSAGE in response.data.decode()

    set_room_status(app, room_id, "voting")
    response = add_option(guest, room_id, "Something new")
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    run_sql(app, "UPDATE rooms SET status = 'collecting' WHERE id = ?", (room_id,))
    assert snapshot(app) == before


def test_google_results_do_not_count(app, client):
    room_id = create_room(client, mode="surprise")
    save_setup(client, room_id, kind="food.brunch", options_per_person="1")
    surprise_me(client, room_id)
    assert len(all_options(app, room_id)) == surprise.SURPRISE_OPTION_COUNT
    guest = app.test_client()
    join(guest, room_id, "Ben")
    assert_redirects_to_room(add_option(guest, room_id, "Own idea"), room_id)
    response = add_option(guest, room_id, "Second idea")
    assert response.status_code == 400
    assert limit_message(1) in response.data.decode()


def test_lowered_limit_keeps_options_but_blocks_more(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="3")
    add_option(guest, room_id, "One")
    add_option(guest, room_id, "Two")
    save_setup(client, room_id, kind="food.brunch", options_per_person="1")
    assert [row["label"] for row in all_options(app, room_id)] == ["One", "Two"]
    response = add_option(guest, room_id, "Three")
    assert response.status_code == 400
    assert limit_message(1) in response.data.decode()
    assert len(all_options(app, room_id)) == 2


def test_add_form_shows_count_and_hides_at_limit(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="3")
    add_option(guest, room_id, "One")
    html = page(guest, room_id)
    assert "1 of 3 options added" in html
    assert add_action(room_id) in html

    add_option(guest, room_id, "Two")
    add_option(guest, room_id, "Three")
    html = page(guest, room_id)
    assert at_limit_text(3) in html
    assert add_action(room_id) not in html
    assert find_action(room_id) not in html
    # The creator has added nothing yet and still sees both forms.
    html = page(client, room_id)
    assert "0 of 3 options added" in html
    assert add_action(room_id) in html


# --- Limit: places found by name (C6) -------------------------------------------------

def test_place_by_name_rejected_when_typed_option_reached_limit(app, client, guest, room_id):
    # Searching first, then typing: the pick in step 2 must be refused.
    find(guest, room_id)
    save_setup(client, room_id, kind="food.brunch", options_per_person="1")
    add_option(guest, room_id, "Own idea")
    before = snapshot(app)
    response = add_found(guest, room_id)
    assert response.status_code == 400
    assert limit_message(1) in response.data.decode()
    assert snapshot(app) == before


def test_place_by_name_counts_towards_limit(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="1")
    find(guest, room_id)
    assert_redirects_to_room(add_found(guest, room_id), room_id)
    before = snapshot(app)
    response = add_option(guest, room_id, "Own idea")
    assert response.status_code == 400
    assert limit_message(1) in response.data.decode()
    assert snapshot(app) == before


def test_name_search_at_limit_does_not_call_google(app, client, guest, room_id, google):
    save_setup(client, room_id, kind="food.brunch", options_per_person="1")
    add_option(guest, room_id, "Own idea")
    response = find(guest, room_id)
    assert response.status_code == 400
    assert limit_message(1) in response.data.decode()
    assert google.text_searches() == []
    html = page(guest, room_id)
    assert find_action(room_id) not in html
    assert at_limit_text(1) in html


def test_database_holds_limit_for_place_by_name(app, client, guest, room_id, monkeypatch):
    save_setup(client, room_id, kind="food.brunch", options_per_person="1")
    find(guest, room_id)
    add_option(guest, room_id, "Own idea")
    pretend_route_sees_below_limit(monkeypatch)
    before = snapshot(app)
    response = add_found(guest, room_id)
    assert response.status_code == 400
    assert limit_message(1) in response.data.decode()
    assert snapshot(app) == before


@pytest.mark.parametrize("starts_during_request", [False, True])
def test_place_by_name_with_limit_rejected_after_voting_starts(
    app, client, guest, room_id, monkeypatch, starts_during_request
):
    save_setup(client, room_id, kind="food.brunch", options_per_person="3")
    find(guest, room_id)
    set_room_status(app, room_id, "voting")
    if starts_during_request:
        # The route still sees "collecting"; add_place_option_within_limit must say "not_collecting".
        pretend_room_is_collecting(monkeypatch)
    before = snapshot(app)
    response = add_found(guest, room_id)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_add_place_option_within_limit_results(app, guest, room_id):
    ben = participant_id(app, room_id, "Ben")
    with app.app_context():
        assert database.add_place_option_within_limit(room_id, "place-1", ben, 2) == "added"
    option = all_options(app, room_id)[0]
    assert (option["source"], option["place_id"], option["category"]) == ("google", "place-1", None)
    assert author_count(app, room_id, ben) == 1

    before = snapshot(app)
    with app.app_context():
        assert database.add_place_option_within_limit(room_id, "place-1", ben, 5) == "duplicate"
    assert snapshot(app) == before

    with app.app_context():
        assert database.add_place_option_within_limit(room_id, "place-2", ben, 2) == "added"
    before = snapshot(app)
    with app.app_context():
        assert database.add_place_option_within_limit(room_id, "place-3", ben, 2) == "limit"
    assert snapshot(app) == before

    set_room_status(app, room_id, "voting")
    before = snapshot(app)
    with app.app_context():
        assert database.add_place_option_within_limit(room_id, "place-4", ben, 5) == "not_collecting"
    assert snapshot(app) == before


def test_place_by_name_duplicate_message_with_limit(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="3")
    run_sql(
        app,
        "INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', 'place-luigi-1')",
        (room_id,),
    )
    find(guest, room_id)
    before = snapshot(app)
    response = add_found(guest, room_id, "place-luigi-1")
    assert response.status_code == 400
    assert ALREADY_OPTION_MESSAGE in response.data.decode()
    assert snapshot(app) == before
    # The remembered matches stay: another match can still be picked.
    assert_redirects_to_room(add_found(guest, room_id, "place-luigi-2"), room_id)


def test_place_by_name_unchanged_in_set_up_room_without_limit(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="")
    for name in ["One", "Two", "Three", "Four", "Five", "Six"]:
        add_option(guest, room_id, name)
    find(guest, room_id)
    assert_redirects_to_room(add_found(guest, room_id), room_id)
    assert author_count(app, room_id, participant_id(app, room_id, "Ben")) == 7


# --- Persistence -------------------------------------------------------------------

def test_setup_and_limit_survive_restart(app, client, guest, room_id):
    save_setup(client, room_id, kind="food.brunch", options_per_person="3")
    for label in ["One", "Two", "Three"]:
        add_option(guest, room_id, label)

    restarted = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
            "GOOGLE_MAPS_API_KEY": FAKE_KEY,
        }
    )
    browser = restarted.test_client()
    browser.set_cookie("session", guest.get_cookie("session").value)
    html = page(browser, room_id)
    assert BRUNCH_LINE in html
    assert at_limit_text(3) in html
    response = add_option(browser, room_id, "Four")
    assert response.status_code == 400
    assert limit_message(3) in response.data.decode()
    assert len(all_options(restarted, room_id)) == 3
