"""Tests for A7 – F24 Delete an option (specs/a7-delete-option.md)."""

import pytest

from app import create_app
from app.db import get_db, init_db

NOT_JOINED_MESSAGE = "Please join the room before deleting options."
NOT_COLLECTING_MESSAGE = "Options can only be deleted before voting starts."
NOT_ALLOWED_MESSAGE = "Only the person who added this option or the creator can delete it."
TOO_FEW_OPTIONS_MESSAGE = "Add at least 2 options before starting the voting."


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_option(client, room_id, label):
    """Add a manual option through the app (A4) and return its id."""
    response = client.post(f"/rooms/{room_id}/options", data={"label": label})
    assert response.status_code in (302, 303)
    return option_id_by_label(client.application, room_id, label)


def option_id_by_label(app, room_id, label):
    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM options WHERE room_id = ? AND label = ?", (room_id, label)
        ).fetchone()
    return row["id"]


def add_google_option(app, room_id, place_id="ChIJ-fake-place"):
    """Save a Google option the way the nearby search does: no author."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', ?)",
            (room_id, place_id),
        )
        db.commit()
        row = db.execute(
            "SELECT id FROM options WHERE room_id = ? AND place_id = ?", (room_id, place_id)
        ).fetchone()
    return row["id"]


def add_option_without_author(app, room_id, label):
    """A manual option saved before A7, so it has no row in option_authors."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)", (room_id, label)
        )
        db.commit()
    return option_id_by_label(app, room_id, label)


def delete(client, room_id, option_id):
    return client.post(f"/rooms/{room_id}/options/{option_id}/delete")


def delete_action(room_id, option_id):
    return f'action="/rooms/{room_id}/options/{option_id}/delete"'


def option_ids(app, room_id):
    """Ids of every option row of the room (active and replaced), oldest first."""
    with app.app_context():
        rows = get_db().execute(
            "SELECT id FROM options WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()
    return [row["id"] for row in rows]


def snapshot(app):
    """Every option and author row in the database, to compare before and after."""
    with app.app_context():
        db = get_db()
        options = [tuple(row) for row in db.execute("SELECT * FROM options ORDER BY id")]
        authors = [tuple(row) for row in db.execute("SELECT * FROM option_authors ORDER BY option_id")]
    return options, authors


def author_rows(app):
    with app.app_context():
        rows = get_db().execute(
            "SELECT option_id, room_id, participant_id FROM option_authors ORDER BY option_id"
        ).fetchall()
    return [dict(row) for row in rows]


def participant_id(app, room_id, nickname):
    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM participants WHERE room_id = ? AND nickname = ?", (room_id, nickname)
        ).fetchone()
    return row["id"]


def set_room_status(app, room_id, status):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def mark_replaced(app, option_id):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE options SET is_replaced = 1 WHERE id = ?", (option_id,))
        db.commit()


def page(client, room_id):
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    return response.data.decode()


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


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
def other_guest(app, room_id):
    """A third browser that has joined the room as "Cara"."""
    browser = app.test_client()
    join(browser, room_id, "Cara")
    return browser


# --- Accepted --------------------------------------------------------------

def test_author_deletes_own_option(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    response = delete(guest, room_id, pizza)
    assert_redirects_to_room(response, room_id)
    assert pizza not in option_ids(app, room_id)
    assert "Thai Garden" not in page(guest, room_id)


def test_creator_deletes_option_of_another_participant(app, client, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    assert_redirects_to_room(delete(client, room_id, pizza), room_id)
    assert pizza not in option_ids(app, room_id)


def test_creator_deletes_google_option(app, client, room_id):
    place = add_google_option(app, room_id)
    assert_redirects_to_room(delete(client, room_id, place), room_id)
    assert option_ids(app, room_id) == []


def test_creator_deletes_own_option(app, client, room_id):
    pizza = add_option(client, room_id, "Thai Garden")
    assert_redirects_to_room(delete(client, room_id, pizza), room_id)
    assert option_ids(app, room_id) == []


def test_same_label_can_be_added_again_after_deleting(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    delete(guest, room_id, pizza)
    new_pizza = add_option(guest, room_id, "Thai Garden")
    assert option_ids(app, room_id) == [new_pizza]


def test_delete_leaves_no_author_row_and_other_options_unchanged(app, client, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    cinema = add_option(guest, room_id, "Cinema")
    place = add_google_option(app, room_id)
    delete(guest, room_id, pizza)
    assert option_ids(app, room_id) == [cinema, place]
    assert [row["option_id"] for row in author_rows(app)] == [cinema]


def test_lobby_counts_one_less_and_start_needs_two_again(app, client, guest, room_id):
    add_option(guest, room_id, "Thai Garden")
    cinema = add_option(guest, room_id, "Cinema")
    delete(guest, room_id, cinema)
    lobby = client.get(f"/rooms/{room_id}/lobby").data.decode()
    assert "1 options" in lobby
    response = client.post(f"/rooms/{room_id}/start")
    assert response.status_code == 400
    assert TOO_FEW_OPTIONS_MESSAGE in response.data.decode()


def test_adding_an_option_stores_its_author(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    assert author_rows(app) == [
        {"option_id": pizza, "room_id": room_id, "participant_id": participant_id(app, room_id, "Ben")}
    ]


# --- Room page -------------------------------------------------------------

def test_participant_sees_delete_only_for_own_options(app, client, guest, room_id):
    own = add_option(guest, room_id, "Thai Garden")
    creators = add_option(client, room_id, "Cinema")
    place = add_google_option(app, room_id)
    html = page(guest, room_id)
    assert delete_action(room_id, own) in html
    assert delete_action(room_id, creators) not in html
    assert delete_action(room_id, place) not in html


def test_creator_sees_delete_for_every_option(app, client, guest, room_id):
    ids = [add_option(guest, room_id, "Thai Garden"), add_option(client, room_id, "Cinema")]
    ids.append(add_google_option(app, room_id))
    html = page(client, room_id)
    for option_id in ids:
        assert delete_action(room_id, option_id) in html


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_no_delete_form_after_collecting(app, client, guest, room_id, status):
    pizza = add_option(guest, room_id, "Thai Garden")
    set_room_status(app, room_id, status)
    assert delete_action(room_id, pizza) not in page(client, room_id)
    assert delete_action(room_id, pizza) not in page(guest, room_id)


def test_author_is_not_shown_to_others(app, other_guest, room_id):
    author = app.test_client()
    join(author, room_id, "Bartholomew")
    add_option(author, room_id, "Thai Garden")
    html = page(other_guest, room_id)
    assert "Thai Garden" in html
    assert "Bartholomew" not in html


# --- Rejected --------------------------------------------------------------

def test_other_participant_cannot_delete(app, guest, other_guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    before = snapshot(app)
    response = delete(other_guest, room_id, pizza)
    assert response.status_code == 403
    assert NOT_ALLOWED_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_non_creator_cannot_delete_google_option(app, guest, room_id):
    place = add_google_option(app, room_id)
    before = snapshot(app)
    response = delete(guest, room_id, place)
    assert response.status_code == 403
    assert NOT_ALLOWED_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_option_without_author_only_creator_can_delete(app, client, guest, room_id):
    old = add_option_without_author(app, room_id, "Thai Garden")
    before = snapshot(app)
    assert delete(guest, room_id, old).status_code == 403
    assert snapshot(app) == before
    assert_redirects_to_room(delete(client, room_id, old), room_id)
    assert option_ids(app, room_id) == []


@pytest.mark.parametrize("status", ["voting", "closed"])
def test_cannot_delete_after_collecting(app, client, guest, room_id, status):
    pizza = add_option(guest, room_id, "Thai Garden")
    set_room_status(app, room_id, status)
    before = snapshot(app)
    for browser in (guest, client):
        response = delete(browser, room_id, pizza)
        assert response.status_code == 400
        assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_visitor_cannot_delete(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    before = snapshot(app)
    response = delete(app.test_client(), room_id, pizza)
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_participant_of_another_room_cannot_delete(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    stranger = app.test_client()
    create_room(stranger, nickname="Zoe")  # creator of a different room
    before = snapshot(app)
    response = delete(stranger, room_id, pizza)
    assert response.status_code == 403
    assert NOT_JOINED_MESSAGE in response.data.decode()
    assert snapshot(app) == before


def test_unknown_room_is_404(client):
    assert delete(client, "no-such-room", 1).status_code == 404


def test_option_of_another_room_is_unchanged(app, client, room_id):
    other_browser = app.test_client()
    other_room = create_room(other_browser, nickname="Zoe")
    foreign = add_option(other_browser, other_room, "Sushi")
    before = snapshot(app)
    response = delete(client, room_id, foreign)  # Anna is the creator of room_id, not of other_room
    assert_redirects_to_room(response, room_id)
    assert snapshot(app) == before


def test_bad_option_id_and_get_are_refused(app, client, room_id):
    pizza = add_option(client, room_id, "Thai Garden")
    assert client.post(f"/rooms/{room_id}/options/abc/delete").status_code == 404
    assert client.get(f"/rooms/{room_id}/options/{pizza}/delete").status_code == 405
    assert option_ids(app, room_id) == [pizza]


# --- Ignored ---------------------------------------------------------------

def test_deleting_twice_changes_nothing_the_second_time(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    cinema = add_option(guest, room_id, "Cinema")
    delete(guest, room_id, pizza)
    before = snapshot(app)
    assert_redirects_to_room(delete(guest, room_id, pizza), room_id)
    assert snapshot(app) == before
    assert option_ids(app, room_id) == [cinema]


def test_replaced_option_is_ignored(app, client, room_id):
    place = add_google_option(app, room_id)
    mark_replaced(app, place)
    before = snapshot(app)
    assert_redirects_to_room(delete(client, room_id, place), room_id)
    assert snapshot(app) == before


# --- Edge case: voting starts at the same moment -----------------------------

def test_race_with_start_voting_keeps_the_option(app, guest, room_id, monkeypatch):
    pizza = add_option(guest, room_id, "Thai Garden")
    set_room_status(app, room_id, "voting")
    before = snapshot(app)
    # The route's own status check still sees "collecting", as if the creator
    # started the voting right after this request read the room.
    monkeypatch.setattr(
        "app.db.get_room",
        lambda wanted: {
            "id": wanted, "title": "Dinner", "mode": "manual", "status": "collecting",
            "search_center_lat": None, "search_center_lng": None, "radius_m": None,
            "filters": None, "deadline": None, "winner_option_id": None,
        },
    )
    response = delete(guest, room_id, pizza)
    assert response.status_code == 400
    assert NOT_COLLECTING_MESSAGE in response.data.decode()
    assert snapshot(app) == before


# --- Migration and persistence ----------------------------------------------

def test_init_db_adds_the_table_and_keeps_data(app, client, room_id):
    add_option(client, room_id, "Thai Garden")
    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE option_authors")  # a database from before A7
        db.commit()
        init_db()
        tables = [row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        labels = [row["label"] for row in db.execute("SELECT label FROM options")]
    assert "option_authors" in tables
    assert labels == ["Thai Garden"]
    assert "Thai Garden" in page(client, room_id)


def test_deletion_and_authorship_survive_restart(app, guest, room_id):
    pizza = add_option(guest, room_id, "Thai Garden")
    cinema = add_option(guest, room_id, "Cinema")
    delete(guest, room_id, pizza)
    session_cookie = guest.get_cookie("session")

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

    assert option_ids(restarted_app, room_id) == [cinema]
    assert delete_action(room_id, cinema) in page(restarted_browser, room_id)
    assert_redirects_to_room(delete(restarted_browser, room_id, cinema), room_id)
    assert option_ids(restarted_app, room_id) == []
