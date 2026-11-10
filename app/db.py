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
