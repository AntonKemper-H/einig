"""Database access. This is the only module that talks to the database.

For now this uses SQLite. Hosted Postgres for the deployed app follows in a
separate task (see docs/decisions.md, D4).
"""

import sqlite3
from pathlib import Path

import click
from flask import Flask, current_app, g
from flask.cli import with_appcontext

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    """Return the database connection for the current request, opening it if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row  # rows behave like dicts: row["title"]
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(error: BaseException | None = None) -> None:
    """Close the connection at the end of the request, if one was opened."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    """Create all missing tables from schema.sql. Existing data is never deleted."""
    connection = get_db()
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    connection.commit()


def reset_db() -> None:
    """Delete every table with all its data, then create empty tables again."""
    connection = get_db()
    table_names = [
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    # Foreign keys would block dropping tables that others point to.
    connection.execute("PRAGMA foreign_keys = OFF")
    for table_name in table_names:
        # Table names cannot be "?" placeholders; they come from SQLite itself, not from a user.
        connection.execute(f'DROP TABLE "{table_name}"')
    connection.execute("PRAGMA foreign_keys = ON")
    connection.commit()
    init_db()


def create_room_with_creator(
    room_id: str, title: str, mode: str, nickname: str, session_token: str
) -> bool:
    """Save a new room and its creator in one transaction. Return False if an id or token already exists."""
    connection = get_db()
    try:
        # "with connection" commits both inserts together, or rolls both back on an error,
        # so there is never a room without its creator.
        with connection:
            connection.execute(
                "INSERT INTO rooms (id, title, mode) VALUES (?, ?, ?)",
                (room_id, title, mode),
            )
            connection.execute(
                "INSERT INTO participants (room_id, nickname, session_token, is_creator)"
                " VALUES (?, ?, ?, 1)",
                (room_id, nickname, session_token),
            )
    except sqlite3.IntegrityError:
        # A duplicate room id or session token (extremely unlikely with random tokens).
        return False
    return True


def get_room(room_id: str) -> sqlite3.Row | None:
    """Return the room with this id, or None if it does not exist."""
    return get_db().execute(
        "SELECT id, title, mode, status FROM rooms WHERE id = ?", (room_id,)
    ).fetchone()


def get_participant(room_id: str, session_token: str | None) -> sqlite3.Row | None:
    """Return the participant of this room with this session token, or None."""
    if not session_token:
        return None
    return get_db().execute(
        "SELECT id, nickname, is_creator, has_finished FROM participants"
        " WHERE room_id = ? AND session_token = ?",
        (room_id, session_token),
    ).fetchone()


def get_nicknames(room_id: str) -> list[str]:
    """Return the nicknames of all participants in this room."""
    rows = get_db().execute(
        "SELECT nickname FROM participants WHERE room_id = ?", (room_id,)
    ).fetchall()
    return [row["nickname"] for row in rows]


def add_participant(room_id: str, nickname: str, session_token: str) -> bool:
    """Save a new (non-creator) participant. Return False if the database refuses it."""
    connection = get_db()
    try:
        with connection:
            connection.execute(
                "INSERT INTO participants (room_id, nickname, session_token) VALUES (?, ?, ?)",
                (room_id, nickname, session_token),
            )
    except sqlite3.IntegrityError:
        # Duplicate token, or the same nickname saved by another request a moment earlier.
        return False
    return True


def get_options(room_id: str) -> list[sqlite3.Row]:
    """Return all options of a room in the order they were added."""
    return get_db().execute(
        "SELECT id, label FROM options WHERE room_id = ? ORDER BY id",
        (room_id,),
    ).fetchall()


def get_option_labels(room_id: str) -> list[str]:
    """Return the labels of all manual options in this room (used for the duplicate check)."""
    rows = get_db().execute(
        "SELECT label FROM options WHERE room_id = ? AND label IS NOT NULL", (room_id,)
    ).fetchall()
    return [row["label"] for row in rows]


def add_manual_option(room_id: str, label: str) -> bool:
    """Save a manually entered option. Return False if the database refuses it."""
    connection = get_db()
    try:
        with connection:
            connection.execute(
                "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', ?)",
                (room_id, label),
            )
    except sqlite3.IntegrityError:
        # The same label saved by another request a moment earlier (UNIQUE room_id, label).
        return False
    return True


@click.command("init-db")
@with_appcontext  # gives the command access to the app config and get_db()
def init_db_command() -> None:
    """CLI: uv run flask --app app init-db (safe: only creates what is missing)."""
    init_db()
    click.echo("Initialized the database.")


@click.command("reset-db")
@with_appcontext
def reset_db_command() -> None:
    """CLI: uv run flask --app app reset-db (deletes all data after confirmation)."""
    if not click.confirm("This will delete all data in the database. Continue?", default=False):
        click.echo("Cancelled. Nothing was changed.")
        return
    reset_db()
    click.echo("Database reset. All tables are empty.")


def init_app(app: Flask) -> None:
    """Register the close handler and the database commands with the app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(reset_db_command)
