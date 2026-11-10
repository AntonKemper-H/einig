"""Tests for safe database commands (specs/f0-project-skeleton.md, review #1 point 2).

`init-db` must never delete data. Deleting everything is a separate command,
`reset-db`, which asks for confirmation first.
"""

from app.db import get_db


def add_test_row(app):
    """Store one extra row so we can check whether data survives a command."""
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO app_info (key, value) VALUES ('test_row', 'keep me')")
        db.commit()


def test_row_exists(app) -> bool:
    """Return True if the row from add_test_row is still in the database."""
    with app.app_context():
        row = get_db().execute("SELECT value FROM app_info WHERE key = 'test_row'").fetchone()
    return row is not None


# Tell pytest that the helper above is not a test.
test_row_exists.__test__ = False


def test_init_db_keeps_existing_data(app, runner):
    add_test_row(app)
    result = runner.invoke(args=["init-db"])
    assert "Initialized the database" in result.output
    assert test_row_exists(app)


def test_reset_db_asks_for_confirmation(app, runner):
    result = runner.invoke(args=["reset-db"], input="n\n")
    assert "delete all data" in result.output.lower()


def test_reset_db_cancelled_keeps_data(app, runner):
    """Rejected: answering 'n' leaves the data unchanged."""
    add_test_row(app)
    result = runner.invoke(args=["reset-db"], input="n\n")
    assert "Cancelled" in result.output
    assert test_row_exists(app)


def test_reset_db_confirmed_deletes_data(app, runner):
    add_test_row(app)
    result = runner.invoke(args=["reset-db"], input="y\n")
    assert "Database reset" in result.output
    assert not test_row_exists(app)


def test_reset_db_leaves_a_working_empty_database(app, runner, client):
    """After a reset the tables exist again and the app still works."""
    runner.invoke(args=["reset-db"], input="y\n")
    with app.app_context():
        version = get_db().execute(
            "SELECT value FROM app_info WHERE key = 'schema_version'"
        ).fetchone()
    assert version is not None
    assert client.get("/").status_code == 200
