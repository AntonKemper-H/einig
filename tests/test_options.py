"""Tests for A4 – F3 Add options manually (specs/a4-add-options.md)."""

import pytest

from app import create_app
from app.db import get_db

NOT_JOINED_MESSAGE = "Please join the room before adding options."
NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
DUPLICATE_MESSAGE = "This option is already in the list."
REFUSED_MESSAGE = "Something went wrong while adding the option. Please try again."
NO_LONGER_MESSAGE = "Options can no longer be added."


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner on Friday", nickname="Anna"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    """Join a room (A3) in this browser."""
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_option(client, room_id, label):
    """Post the add-option form. A label of None leaves the field out completely."""
    form = {} if label is None else {"label": label}
    return client.post(f"/rooms/{room_id}/options", data=form)


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


def options(app, room_id):
    """Return all saved options of a room, oldest first."""
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def labels(app, room_id):
    return [row["label"] for row in options(app, room_id)]


def option_count(app):
    """Return how many options are saved in all rooms."""
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM options").fetchone()[0]


def set_room_status(app, room_id, status):
    """Change a room's status directly in the database (start/close come in later tasks)."""
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def add_form_action(room_id):
    return f'action="/rooms/{room_id}/options"'


@pytest.fixture
def room_id(client):
    """A room created by "Anna" in the creator's browser (the `client` fixture)."""
    return create_room(client)


@pytest.fixture
def guest(app, room_id):
    """A second browser that has joined the room as "Ben"."""
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


@pytest.fixture
def visitor(app):
    """A browser that has not joined any room."""
    return app.test_client()


# --- Room page -------------------------------------------------------------

def test_participant_sees_empty_list_and_add_form(client, room_id):
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert "Options" in html
    assert "No options yet." in html
    assert add_form_action(room_id) in html
    assert 'name="label"' in html


def test_visitor_sees_no_add_form_and_no_options(client, visitor, room_id):
    add_option(client, room_id, "Pizza place")
    html = visitor.get(f"/rooms/{room_id}").data.decode()
    assert add_form_action(room_id) not in html
    assert "Pizza place" not in html


# --- Accepted --------------------------------------------------------------

def test_valid_option_redirects_to_room_page(client, room_id):
    assert_redirects_to_room(add_option(client, room_id, "Pizza place"), room_id)


def test_option_is_stored_as_manual_option(app, client, room_id):
    add_option(client, room_id, "Pizza place")
    stored = options(app, room_id)
    assert len(stored) == 1
    option = stored[0]
    assert option["source"] == "manual"
    assert option["label"] == "Pizza place"
    assert option["place_id"] is None
    assert option["category"] is None
    assert option["is_replaced"] == 0


def test_label_is_stored_stripped(app, client, room_id):
    add_option(client, room_id, " \t Pizza place \n")
    assert labels(app, room_id) == ["Pizza place"]


def test_options_appear_on_room_page_in_order_added(client, room_id):
    for label in ["Pizza place", "Cinema", "Bowling"]:
        add_option(client, room_id, label)
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert "No options yet." not in html
    positions = [html.index(label) for label in ["Pizza place", "Cinema", "Bowling"]]
    assert positions == sorted(positions)


def test_creator_and_participant_both_add_and_see_all_options(app, client, guest, room_id):
    assert_redirects_to_room(add_option(client, room_id, "Pizza place"), room_id)
    assert_redirects_to_room(add_option(guest, room_id, "Cinema"), room_id)
    assert labels(app, room_id) == ["Pizza place", "Cinema"]
    for browser in (client, guest):
        html = browser.get(f"/rooms/{room_id}").data.decode()
        assert "Pizza place" in html
        assert "Cinema" in html


def test_same_label_in_another_room_is_accepted(app, client, room_id):
    other_room_id = create_room(client, title="Saturday")
    add_option(client, room_id, "Pizza place")
    assert_redirects_to_room(add_option(client, other_room_id, "Pizza place"), other_room_id)
    assert labels(app, other_room_id) == ["Pizza place"]


def test_label_at_maximum_length_is_accepted(app, client, room_id):
    label = "o" * 80
    assert_redirects_to_room(add_option(client, room_id, f"  {label} "), room_id)
    assert labels(app, room_id) == [label]


def test_label_with_html_is_stored_as_typed_and_shown_escaped(app, client, room_id):
    label = "<script>alert(1)</script>"
    add_option(client, room_id, label)
    assert labels(app, room_id) == [label]
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- Rejected: invalid label ------------------------------------------------

REJECTED_LABELS = [
    pytest.param(None, [], "Please enter an option.", id="missing"),
    pytest.param("", [], "Please enter an option.", id="empty"),
    pytest.param(" \t\r\n ", [], "Please enter an option.", id="whitespace"),
    pytest.param("o" * 81, [], "An option can be at most 80 characters.", id="too-long"),
    pytest.param("Pizza place", ["Pizza place"], DUPLICATE_MESSAGE, id="duplicate-exact"),
    pytest.param("pizza PLACE", ["Pizza place"], DUPLICATE_MESSAGE, id="duplicate-case"),
    pytest.param("  Pizza place\t", ["Pizza place"], DUPLICATE_MESSAGE, id="duplicate-whitespace"),
    pytest.param("café ö", ["Café Ö"], DUPLICATE_MESSAGE, id="duplicate-non-ascii"),
]


@pytest.mark.parametrize("label, existing, message", REJECTED_LABELS)
def test_rejected_label_shows_message_and_saves_nothing(app, client, room_id, label, existing, message):
    for existing_label in existing:
        assert_redirects_to_room(add_option(client, room_id, existing_label), room_id)
    before = option_count(app)

    response = add_option(client, room_id, label)

    assert response.status_code == 400
    assert message in response.data.decode()
    assert option_count(app) == before


def test_rejected_form_keeps_entered_label(client, room_id):
    response = add_option(client, room_id, "o" * 81)
    html = response.data.decode()
    assert response.status_code == 400
    assert add_form_action(room_id) in html
    assert "o" * 81 in html


# --- Rejected: wrong phase or no permission ---------------------------------

@pytest.mark.parametrize("status", ["voting", "closed"])
def test_adding_after_collecting_is_rejected(app, client, room_id, status):
    add_option(client, room_id, "Pizza place")
    set_room_status(app, room_id, status)
    before = option_count(app)

    response = add_option(client, room_id, "Cinema")

    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert option_count(app) == before
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert NO_LONGER_MESSAGE in html
    assert add_form_action(room_id) not in html
    assert "Pizza place" in html


def test_visitor_without_token_cannot_add(app, visitor, room_id):
    response = add_option(visitor, room_id, "Pizza place")
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.data.decode()
    assert option_count(app) == 0


def test_visitor_with_unknown_token_cannot_add(app, visitor, room_id):
    with visitor.session_transaction() as session:
        session["participant_tokens"] = {room_id: "token-that-is-not-in-the-database"}
    response = add_option(visitor, room_id, "Pizza place")
    assert response.status_code == 403
    assert option_count(app) == 0


def test_participant_of_another_room_cannot_add(app, client, room_id):
    other_browser = app.test_client()
    other_room_id = create_room(other_browser, title="Saturday", nickname="Carla")
    # Carla's token for her own room, presented for Anna's room.
    with other_browser.session_transaction() as session:
        carla_token = session["participant_tokens"][other_room_id]
        session["participant_tokens"] = {room_id: carla_token}

    response = add_option(other_browser, room_id, "Pizza place")

    assert response.status_code == 403
    assert option_count(app) == 0


def test_adding_to_unknown_room_shows_404(app, client, room_id):
    response = add_option(client, "does-not-exist", "Pizza place")
    assert response.status_code == 404
    assert option_count(app) == 0


def test_refused_insert_shows_message_and_does_not_crash(app, client, room_id, monkeypatch):
    add_option(client, room_id, "Pizza place")
    # Simulate a race: the duplicate check sees no labels, so only the
    # database's UNIQUE (room_id, label) rule stops the second insert.
    monkeypatch.setattr("app.db.get_option_labels", lambda room_id: [])
    before = option_count(app)

    response = add_option(client, room_id, "Pizza place")

    assert REFUSED_MESSAGE in response.data.decode()
    assert option_count(app) == before


# --- Persistence -----------------------------------------------------------

def test_options_survive_restart(app, client, room_id):
    add_option(client, room_id, "Pizza place")
    add_option(client, room_id, "Cinema")
    session_cookie = client.get_cookie("session")
    assert session_cookie is not None

    # A restart: a brand-new app object on the same database file and secret key.
    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
        }
    )
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)

    assert labels(restarted_app, room_id) == ["Pizza place", "Cinema"]
    html = restarted_browser.get(f"/rooms/{room_id}").data.decode()
    assert "Pizza place" in html
    assert "Cinema" in html
