"""Extra tests for A7 – F24 Delete an option (specs/a7-delete-option.md).

Added after the first test review: tests/test_delete_option.py was already
approved and must not be edited, so these live in a new file.
"""

import sqlite3

import pytest

from app import db as database
from app.db import get_db

NOT_ALLOWED_MESSAGE = "Only the person who added this option or the creator can delete it."


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_option(client, room_id, label):
    response = client.post(f"/rooms/{room_id}/options", data={"label": label})
    assert response.status_code in (302, 303)


def snapshot(app):
    with app.app_context():
        connection = get_db()
        options = [tuple(row) for row in connection.execute("SELECT * FROM options ORDER BY id")]
        authors = [
            tuple(row) for row in connection.execute("SELECT * FROM option_authors ORDER BY option_id")
        ]
    return options, authors


def delete(client, room_id, option_id):
    return client.post(f"/rooms/{room_id}/options/{option_id}/delete")


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


@pytest.fixture
def room_id(client):
    return create_room(client)


@pytest.fixture
def guest(app, room_id):
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


# --- Schema ----------------------------------------------------------------

def test_new_database_has_option_authors_table(app):
    with app.app_context():
        columns = [row[1] for row in get_db().execute("PRAGMA table_info(option_authors)")]
    assert columns == ["option_id", "room_id", "participant_id"]


def test_init_db_twice_keeps_options_and_authors(app, runner, guest, room_id):
    add_option(guest, room_id, "Thai Garden")
    before = snapshot(app)
    for _ in range(2):
        result = runner.invoke(args=["init-db"])
        assert result.exit_code == 0
        assert "Initialized the database" in result.output
    assert snapshot(app) == before
    assert len(before[1]) == 1


def test_author_from_another_room_is_refused(app, client, guest, room_id):
    add_option(guest, room_id, "Thai Garden")
    stranger = app.test_client()
    other_room = create_room(stranger, nickname="Zoe")
    with app.app_context():
        connection = get_db()
        option_id = connection.execute(
            "SELECT id FROM options WHERE room_id = ?", (room_id,)
        ).fetchone()["id"]
        zoe = connection.execute(
            "SELECT id FROM participants WHERE room_id = ?", (other_room,)
        ).fetchone()["id"]
        connection.execute("DELETE FROM option_authors")
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO option_authors (option_id, room_id, participant_id) VALUES (?, ?, ?)",
                (option_id, room_id, zoe),
            )
        connection.rollback()


# --- Ignored and rejected ----------------------------------------------------

def test_option_id_that_does_not_exist_is_ignored(app, client, room_id):
    add_option(client, room_id, "Thai Garden")
    before = snapshot(app)
    assert_redirects_to_room(delete(client, room_id, 999999), room_id)
    assert snapshot(app) == before


def test_been_there_replacement_only_creator_can_delete(app, client, guest, room_id):
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', 'ChIJ-old')", (room_id,)
        )
        connection.commit()
        old_id = connection.execute(
            "SELECT id FROM options WHERE place_id = 'ChIJ-old'"
        ).fetchone()["id"]
        # The same database call the "Been there" route uses (C5).
        assert database.replace_option(room_id, old_id, "ChIJ-new", "restaurant")
        new_id = connection.execute(
            "SELECT id FROM options WHERE place_id = 'ChIJ-new'"
        ).fetchone()["id"]

    before = snapshot(app)
    response = delete(guest, room_id, new_id)
    assert response.status_code == 403
    assert NOT_ALLOWED_MESSAGE in response.data.decode()
    assert snapshot(app) == before

    assert_redirects_to_room(delete(client, room_id, new_id), room_id)
    with app.app_context():
        remaining = [row["place_id"] for row in get_db().execute(
            "SELECT place_id FROM options WHERE room_id = ? AND is_replaced = 0", (room_id,)
        )]
    assert remaining == []
