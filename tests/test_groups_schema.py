"""Schema tests for A9 – F16 Fixed groups (specs/a9-groups.md)."""

import sqlite3
from pathlib import Path

import pytest

from app.db import get_db, init_db
from typed_option import add_typed_option

GROUP_TABLES = {
    "groups": ["id", "name", "created_at", "last_activity_at"],
    "group_members": ["id", "group_id", "nickname", "member_token", "is_creator", "joined_at"],
    "group_rooms": ["room_id", "group_id"],
    "group_participants": ["participant_id", "group_member_id"],
}
ROOM_COLUMNS = [
    "id", "title", "mode", "status", "deadline", "search_center_lat", "search_center_lng",
    "radius_m", "filters", "winner_option_id", "created_at",
]
PROJECT_ROOT = Path(__file__).parent.parent
PARTICIPANT_COLUMNS = ["id", "room_id", "nickname", "session_token", "is_creator", "has_finished"]


# --- Helpers ---------------------------------------------------------------

def columns(connection, table):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]


def table_names(connection):
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def create_room(client, title="Dinner", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def everything(connection):
    """All rows of the tables that existed before A9."""
    return {
        table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
        for table in ("rooms", "participants", "options", "votes", "option_authors")
    }


def insert_group(connection, group_id="g1", name="Friends"):
    connection.execute("INSERT INTO groups (id, name) VALUES (?, ?)", (group_id, name))


def insert_member(connection, group_id, nickname, token):
    return connection.execute(
        "INSERT INTO group_members (group_id, nickname, member_token) VALUES (?, ?, ?) RETURNING id",
        (group_id, nickname, token),
    ).fetchone()[0]


def participant_id(connection, room_id, nickname):
    return connection.execute(
        "SELECT id FROM participants WHERE room_id = ? AND nickname = ?", (room_id, nickname)
    ).fetchone()[0]


# --- Tests -------------------------------------------------------------------

def test_fresh_database_has_the_four_tables_and_unchanged_room_tables(app):
    with app.app_context():
        connection = get_db()
        for table, expected in GROUP_TABLES.items():
            assert columns(connection, table) == expected
        assert columns(connection, "rooms") == ROOM_COLUMNS
        assert columns(connection, "participants") == PARTICIPANT_COLUMNS


def test_init_db_adds_the_tables_and_keeps_all_data(app, client, runner):
    room_id = create_room(client)
    add_typed_option(client, room_id, "Thai Garden")
    add_typed_option(client, room_id, "Burger Bar")
    assert client.post(f"/rooms/{room_id}/start").status_code in (302, 303)
    with app.app_context():
        connection = get_db()
        option_id = connection.execute("SELECT id FROM options ORDER BY id").fetchone()[0]
    assert client.post(f"/rooms/{room_id}/vote", data={"option_id": option_id, "rating": "yes"}).status_code in (302, 303)

    with app.app_context():
        connection = get_db()
        # A database from before A9.
        for table in ("group_participants", "group_rooms", "group_members", "groups"):
            connection.execute(f"DROP TABLE {table}")
        connection.commit()
        before = everything(connection)
        assert before["votes"]

    for _ in range(2):
        result = runner.invoke(args=["init-db"])
        assert result.exit_code == 0

    with app.app_context():
        connection = get_db()
        assert set(GROUP_TABLES) <= table_names(connection)
        assert everything(connection) == before


def test_member_nickname_is_unique_within_a_group_only(app):
    with app.app_context():
        connection = get_db()
        insert_group(connection, "g1")
        insert_group(connection, "g2")
        insert_member(connection, "g1", "Anna", "token-1")
        insert_member(connection, "g2", "Anna", "token-2")
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            insert_member(connection, "g1", "Anna", "token-3")
        connection.rollback()
        count = connection.execute("SELECT COUNT(*) FROM group_members").fetchone()[0]
    assert count == 2


def test_deleting_a_group_keeps_its_rooms_and_participants(app, client):
    room_id = create_room(client)
    with app.app_context():
        connection = get_db()
        insert_group(connection, "g1")
        member_id = insert_member(connection, "g1", "Anna", "token-1")
        connection.execute("INSERT INTO group_rooms (room_id, group_id) VALUES (?, 'g1')", (room_id,))
        connection.execute(
            "INSERT INTO group_participants (participant_id, group_member_id) VALUES (?, ?)",
            (participant_id(connection, room_id, "Anna"), member_id),
        )
        connection.commit()

        connection.execute("DELETE FROM groups WHERE id = 'g1'")
        connection.commit()
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("group_members", "group_rooms", "group_participants", "rooms", "participants")
        }
    assert counts == {
        "group_members": 0,
        "group_rooms": 0,
        "group_participants": 0,
        "rooms": 1,
        "participants": 1,
    }


def test_deleting_a_room_removes_its_link_and_a_room_has_one_group(app, client):
    room_id = create_room(client)
    with app.app_context():
        connection = get_db()
        insert_group(connection, "g1")
        insert_group(connection, "g2")
        connection.execute("INSERT INTO group_rooms (room_id, group_id) VALUES (?, 'g1')", (room_id,))
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO group_rooms (room_id, group_id) VALUES (?, 'g2')", (room_id,))
        connection.rollback()

        connection.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        connection.commit()
        links = connection.execute("SELECT COUNT(*) FROM group_rooms").fetchone()[0]
        groups = connection.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
    assert links == 0
    assert groups == 2


def test_group_participant_is_unique_per_participant(app, client):
    room_id = create_room(client)
    with app.app_context():
        connection = get_db()
        insert_group(connection, "g1")
        first = insert_member(connection, "g1", "Anna", "token-1")
        second = insert_member(connection, "g1", "Ben", "token-2")
        anna = participant_id(connection, room_id, "Anna")
        connection.execute(
            "INSERT INTO group_participants (participant_id, group_member_id) VALUES (?, ?)", (anna, first)
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO group_participants (participant_id, group_member_id) VALUES (?, ?)",
                (anna, second),
            )
        connection.rollback()


def test_postgres_schema_has_no_identity_on_link_columns():
    """schema_to_postgres turns every "INTEGER PRIMARY KEY" into an identity column.

    The link tables point at ids of other tables, so they must not be identity columns.
    """
    from app.db import schema_to_postgres

    translated = schema_to_postgres((PROJECT_ROOT / "app" / "schema.sql").read_text())
    start = translated.index("CREATE TABLE IF NOT EXISTS group_participants")
    end = translated.index(";", start)
    assert "IDENTITY" not in translated[start:end]
    start = translated.index("CREATE TABLE IF NOT EXISTS group_members")
    end = translated.index(";", start)
    assert "IDENTITY" in translated[start:end]


def test_init_db_twice_in_a_row_on_a_fresh_database(app):
    with app.app_context():
        init_db()
        init_db()
        assert set(GROUP_TABLES) <= table_names(get_db())
