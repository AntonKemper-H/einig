"""Extra schema tests from mkim-nova's review of PR #5 (specs/a1-schema.md).

These live in a new file because tests/test_schema.py was already reviewed
and must not be edited.
"""

import sqlite3

import pytest

from app.db import get_db

NEW_TABLES = ["rooms", "participants", "options", "votes", "vetoes"]


def all_counts(db):
    """Return the row count of every new table, to compare before and after."""
    return {
        table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in NEW_TABLES
    }


def assert_rejected(db, sql, parameters):
    """Run a bad insert, expect the database to refuse it, and check nothing changed."""
    before = all_counts(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(sql, parameters)
    db.rollback()
    assert all_counts(db) == before


def schema_version(db):
    """Return the stored schema version."""
    return db.execute(
        "SELECT value FROM app_info WHERE key = 'schema_version'"
    ).fetchone()["value"]


@pytest.fixture
def db(app):
    """A database connection inside an app context, with one saved room."""
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO rooms (id, title, mode) VALUES ('room-a', 'Dinner', 'nearby')"
        )
        connection.commit()
        yield connection


INSERT_GOOGLE_OPTION = (
    "INSERT INTO options (room_id, source, place_id) VALUES ('room-a', 'google', ?)"
)
INSERT_ROOM_WITH_SEARCH = (
    "INSERT INTO rooms (id, title, mode, search_center_lat, search_center_lng, radius_m)"
    " VALUES ('room-x', 'Lunch', 'nearby', ?, ?, ?)"
)


# ---------- point 1: empty place_id ----------


def test_google_option_with_empty_place_id_is_rejected(db):
    assert_rejected(db, INSERT_GOOGLE_OPTION, ("",))


def test_google_option_with_space_only_place_id_is_rejected(db):
    assert_rejected(db, INSERT_GOOGLE_OPTION, ("   ",))


# ---------- point 8: ranges for search center and radius ----------


def test_room_with_zero_radius_is_rejected(db):
    assert_rejected(db, INSERT_ROOM_WITH_SEARCH, (38.7, -9.1, 0))


def test_room_with_negative_radius_is_rejected(db):
    assert_rejected(db, INSERT_ROOM_WITH_SEARCH, (38.7, -9.1, -500))


def test_room_with_latitude_out_of_range_is_rejected(db):
    assert_rejected(db, INSERT_ROOM_WITH_SEARCH, (91.0, -9.1, 1000))


def test_room_with_longitude_out_of_range_is_rejected(db):
    assert_rejected(db, INSERT_ROOM_WITH_SEARCH, (38.7, -181.0, 1000))


def test_room_with_valid_search_center_and_radius_is_accepted(db):
    db.execute(INSERT_ROOM_WITH_SEARCH, (38.737, -9.153, 1500))
    db.commit()
    room = db.execute(
        "SELECT search_center_lat, radius_m FROM rooms WHERE id = 'room-x'"
    ).fetchone()
    assert room["search_center_lat"] == 38.737
    assert room["radius_m"] == 1500


# ---------- point 4: schema version ----------


def test_schema_version_is_1_after_init_db(db):
    assert schema_version(db) == "1"


def test_init_db_updates_old_schema_version_and_keeps_rows(app, runner, db):
    """An existing database that still says '0' is updated; its rooms stay."""
    db.execute("UPDATE app_info SET value = '0' WHERE key = 'schema_version'")
    db.commit()
    result = runner.invoke(args=["init-db"])
    assert "Initialized the database" in result.output
    # A fresh app context opens a new connection, like a restart.
    with app.app_context():
        fresh = get_db()
        assert schema_version(fresh) == "1"
        assert all_counts(fresh)["rooms"] == 1
