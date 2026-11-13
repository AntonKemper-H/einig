"""Tests for the database schema (specs/a1-schema.md).

Each rejected row must raise sqlite3.IntegrityError and leave the saved data
unchanged. The database itself enforces the rules for simultaneous actions
from AGENTS.md (one vote per participant and option, one veto per participant
and room, unique nickname per room).
"""

import sqlite3

import pytest

from app.db import get_db

NEW_TABLES = ["rooms", "participants", "options", "votes", "vetoes"]


# ---------- helpers ----------


def add_room(db, room_id="room-a", title="Dinner", mode="manual"):
    """Store a room and return its id."""
    db.execute(
        "INSERT INTO rooms (id, title, mode) VALUES (?, ?, ?)",
        (room_id, title, mode),
    )
    return room_id


def add_participant(db, room_id, nickname, session_token, is_creator=0):
    """Store a participant and return its id."""
    cursor = db.execute(
        "INSERT INTO participants (room_id, nickname, session_token, is_creator)"
        " VALUES (?, ?, ?, ?)",
        (room_id, nickname, session_token, is_creator),
    )
    return cursor.lastrowid


def add_manual_option(db, room_id, label):
    """Store a manual option and return its id."""
    cursor = db.execute(
        "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)",
        (room_id, label),
    )
    return cursor.lastrowid


def add_google_option(db, room_id, place_id):
    """Store a Google option (only the place_id) and return its id."""
    cursor = db.execute(
        "INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', ?)",
        (room_id, place_id),
    )
    return cursor.lastrowid


def count_rows(db, table):
    """Return how many rows a table has. Table names come from this file only."""
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def all_counts(db):
    """Return the row count of every new table, to compare before and after."""
    return {table: count_rows(db, table) for table in NEW_TABLES}


def assert_rejected(db, sql, parameters):
    """Run a bad insert, expect the database to refuse it, and check nothing changed."""
    before = all_counts(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, parameters)
    db.rollback()
    assert all_counts(db) == before


@pytest.fixture
def db(app):
    """A database connection inside an app context."""
    with app.app_context():
        yield get_db()


@pytest.fixture
def two_rooms(db):
    """Two rooms, each with one participant and one option. Saved before each test."""
    add_room(db, "room-a", "Dinner")
    add_room(db, "room-b", "Cinema")
    ids = {
        "anna": add_participant(db, "room-a", "Anna", "token-anna", is_creator=1),
        "ben": add_participant(db, "room-b", "Ben", "token-ben", is_creator=1),
        "pizza": add_manual_option(db, "room-a", "Pizza"),
        "movie": add_manual_option(db, "room-b", "Dune"),
    }
    db.commit()
    return ids


# ---------- tables exist / accepted rows ----------


def test_all_tables_exist_after_init_db(db):
    names = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for table in NEW_TABLES:
        assert table in names


def test_complete_valid_room_can_be_stored(db):
    add_room(db, "room-a", "Dinner", mode="nearby")
    anna = add_participant(db, "room-a", "Anna", "token-anna", is_creator=1)
    pizza = add_manual_option(db, "room-a", "Pizza")
    google = add_google_option(db, "room-a", "ChIJ-fake-place-id")
    db.execute(
        "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, 'yes')",
        ("room-a", anna, pizza),
    )
    db.execute(
        "INSERT INTO vetoes (room_id, participant_id, option_id) VALUES (?, ?, ?)",
        ("room-a", anna, google),
    )
    db.commit()
    assert all_counts(db) == {
        "rooms": 1, "participants": 1, "options": 2, "votes": 1, "vetoes": 1
    }
    google_row = db.execute("SELECT * FROM options WHERE id = ?", (google,)).fetchone()
    assert google_row["place_id"] == "ChIJ-fake-place-id"
    assert google_row["label"] is None


def test_new_room_gets_default_status_and_created_at(db):
    add_room(db)
    db.commit()
    room = db.execute("SELECT status, created_at FROM rooms WHERE id = 'room-a'").fetchone()
    assert room["status"] == "collecting"
    assert room["created_at"] is not None


# ---------- rooms ----------


def test_room_with_unknown_mode_is_rejected(db, two_rooms):
    assert_rejected(
        db, "INSERT INTO rooms (id, title, mode) VALUES ('room-x', 'Lunch', 'fate')", ()
    )


def test_room_with_unknown_status_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO rooms (id, title, mode, status) VALUES ('room-x', 'Lunch', 'manual', 'open')",
        (),
    )


def test_room_with_empty_title_is_rejected(db, two_rooms):
    assert_rejected(
        db, "INSERT INTO rooms (id, title, mode) VALUES ('room-x', '  ', 'manual')", ()
    )


# ---------- participants ----------


def test_duplicate_nickname_in_same_room_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO participants (room_id, nickname, session_token) VALUES (?, ?, ?)",
        ("room-a", "Anna", "token-other"),
    )


def test_same_nickname_in_other_room_is_accepted(db, two_rooms):
    add_participant(db, "room-b", "Anna", "token-anna-2")
    db.commit()
    assert count_rows(db, "participants") == 3


def test_duplicate_session_token_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO participants (room_id, nickname, session_token) VALUES (?, ?, ?)",
        ("room-a", "Clara", "token-anna"),
    )


def test_empty_nickname_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO participants (room_id, nickname, session_token) VALUES (?, ?, ?)",
        ("room-a", "", "token-clara"),
    )


def test_participant_in_unknown_room_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO participants (room_id, nickname, session_token) VALUES (?, ?, ?)",
        ("no-such-room", "Clara", "token-clara"),
    )


# ---------- options ----------


def test_option_with_unknown_source_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO options (room_id, source, label) VALUES ('room-a', 'osm', 'Sushi')",
        (),
    )


def test_manual_option_without_label_is_rejected(db, two_rooms):
    assert_rejected(
        db, "INSERT INTO options (room_id, source) VALUES ('room-a', 'manual')", ()
    )


def test_google_option_without_place_id_is_rejected(db, two_rooms):
    assert_rejected(
        db, "INSERT INTO options (room_id, source) VALUES ('room-a', 'google')", ()
    )


def test_google_option_with_stored_name_is_rejected(db, two_rooms):
    """Google terms: only the place_id may be stored, not the name."""
    assert_rejected(
        db,
        "INSERT INTO options (room_id, source, place_id, label)"
        " VALUES ('room-a', 'google', 'ChIJ-x', 'Some Restaurant')",
        (),
    )


def test_duplicate_manual_label_in_same_room_is_rejected(db, two_rooms):
    assert_rejected(
        db,
        "INSERT INTO options (room_id, source, label) VALUES ('room-a', 'manual', 'Pizza')",
        (),
    )


def test_duplicate_place_id_in_same_room_is_rejected(db, two_rooms):
    add_google_option(db, "room-a", "ChIJ-same")
    db.commit()
    assert_rejected(
        db,
        "INSERT INTO options (room_id, source, place_id) VALUES ('room-a', 'google', 'ChIJ-same')",
        (),
    )


# ---------- votes ----------

INSERT_VOTE = (
    "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, ?)"
)


def test_vote_with_unknown_rating_is_rejected(db, two_rooms):
    assert_rejected(db, INSERT_VOTE, ("room-a", two_rooms["anna"], two_rooms["pizza"], "maybe"))


def test_second_vote_for_same_option_is_rejected(db, two_rooms):
    db.execute(INSERT_VOTE, ("room-a", two_rooms["anna"], two_rooms["pizza"], "yes"))
    db.commit()
    assert_rejected(db, INSERT_VOTE, ("room-a", two_rooms["anna"], two_rooms["pizza"], "no"))


def test_voting_again_with_upsert_replaces_the_vote(db, two_rooms):
    upsert = (
        INSERT_VOTE
        + " ON CONFLICT (participant_id, option_id) DO UPDATE SET rating = excluded.rating"
    )
    db.execute(upsert, ("room-a", two_rooms["anna"], two_rooms["pizza"], "yes"))
    db.execute(upsert, ("room-a", two_rooms["anna"], two_rooms["pizza"], "no"))
    db.commit()
    rows = db.execute("SELECT rating FROM votes").fetchall()
    assert [row["rating"] for row in rows] == ["no"]


def test_vote_for_option_from_other_room_is_rejected(db, two_rooms):
    assert_rejected(db, INSERT_VOTE, ("room-a", two_rooms["anna"], two_rooms["movie"], "yes"))


def test_vote_by_participant_from_other_room_is_rejected(db, two_rooms):
    assert_rejected(db, INSERT_VOTE, ("room-a", two_rooms["ben"], two_rooms["pizza"], "yes"))


# ---------- vetoes ----------

INSERT_VETO = "INSERT INTO vetoes (room_id, participant_id, option_id) VALUES (?, ?, ?)"


def test_second_veto_in_same_room_is_rejected(db, two_rooms):
    sushi = add_manual_option(db, "room-a", "Sushi")
    db.execute(INSERT_VETO, ("room-a", two_rooms["anna"], two_rooms["pizza"]))
    db.commit()
    assert_rejected(db, INSERT_VETO, ("room-a", two_rooms["anna"], sushi))


def test_veto_on_option_from_other_room_is_rejected(db, two_rooms):
    assert_rejected(db, INSERT_VETO, ("room-a", two_rooms["anna"], two_rooms["movie"]))


# ---------- deleting, persistence, reset ----------


def test_deleting_a_room_deletes_everything_in_it(db, two_rooms):
    db.execute(INSERT_VOTE, ("room-a", two_rooms["anna"], two_rooms["pizza"], "ok"))
    db.execute(INSERT_VETO, ("room-a", two_rooms["anna"], two_rooms["pizza"]))
    db.commit()
    db.execute("DELETE FROM rooms WHERE id = 'room-a'")
    db.commit()
    # Only room-b with Ben and "Dune" is left.
    assert all_counts(db) == {
        "rooms": 1, "participants": 1, "options": 1, "votes": 0, "vetoes": 0
    }


def test_init_db_keeps_rows_in_new_tables(app, runner, db, two_rooms):
    db.execute(INSERT_VOTE, ("room-a", two_rooms["anna"], two_rooms["pizza"], "yes"))
    db.commit()
    before = all_counts(db)
    result = runner.invoke(args=["init-db"])
    assert "Initialized the database" in result.output
    # A fresh app context opens a new connection, like a restart.
    with app.app_context():
        assert all_counts(get_db()) == before


def test_reset_db_empties_new_tables(app, runner, db, two_rooms):
    result = runner.invoke(args=["reset-db"], input="y\n")
    assert "Database reset" in result.output
    with app.app_context():
        assert all_counts(get_db()) == {table: 0 for table in NEW_TABLES}
