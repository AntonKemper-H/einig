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
    """Create all tables from schema.sql (existing tables are dropped first)."""
    connection = get_db()
    connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
    connection.commit()


@click.command("init-db")
@with_appcontext  # gives the command access to the app config and get_db()
def init_db_command() -> None:
    """CLI: uv run flask --app app init-db"""
    init_db()
    click.echo("Initialized the database.")


def init_app(app: Flask) -> None:
    """Register the close handler and the init-db command with the app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
