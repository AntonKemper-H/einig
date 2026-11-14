"""Tests for C1 – deployment with hosted Postgres (specs/c1-deployment.md).

No test talks to a real Postgres server: where the Postgres path is checked,
`psycopg.connect` is replaced by a fake that only records the SQL it receives.
"""

import sqlite3
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from app import create_app, db
from app.db import get_db, init_db

PROJECT_ROOT = Path(__file__).parent.parent
FAKE_DATABASE_URL = "postgresql://fake-user:fake-password@fake-host.invalid/fake-db"


# --- Helpers -----------------------------------------------------------------

class FakeCursor:
    """Stands in for a psycopg cursor and returns prepared rows."""

    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class FakePostgresConnection:
    """Records every statement instead of sending it to a server."""

    def __init__(self, table_names=()):
        self.statements = []
        self.table_names = list(table_names)
        self.closed = False
        self.commit_count = 0
        self.rollback_count = 0
        # If set, any statement containing this text fails like a broken UNIQUE rule.
        self.fail_on = None

    def execute(self, sql, params=None):
        if self.closed:
            raise psycopg.OperationalError("the connection is closed")
        self.statements.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise psycopg.IntegrityError("fake duplicate key")
        if "information_schema.tables" in sql:
            return FakeCursor([{"table_name": name} for name in self.table_names])
        return FakeCursor([])

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True

    def all_sql(self) -> str:
        """All statements joined, so a test can search them."""
        return "\n".join(sql for sql, _ in self.statements)


@pytest.fixture
def fake_postgres(monkeypatch):
    """Replace psycopg.connect; returns a dict with the connection and the connect arguments."""
    recorded = {"connection": FakePostgresConnection(table_names=["app_info", "rooms"])}

    def fake_connect(url, **keyword_arguments):
        recorded["url"] = url
        recorded["keyword_arguments"] = keyword_arguments
        return recorded["connection"]

    monkeypatch.setattr(db.psycopg, "connect", fake_connect)
    return recorded


@pytest.fixture
def postgres_app(fake_postgres):
    """An app configured for Postgres, talking to the fake connection."""
    return create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE_URL": FAKE_DATABASE_URL}
    )


def real_run_app(monkeypatch, database_url: str):
    """Build the app like the real server does (no test config) with the given DATABASE_URL."""
    monkeypatch.setenv("SECRET_KEY", "test-only-not-a-real-key")
    # Setting the variable (even to "") stops load_dotenv from taking a value from a local .env.
    monkeypatch.setenv("DATABASE_URL", database_url)
    return create_app()


# --- Choosing the database -----------------------------------------------------

def test_real_run_uses_postgres_when_database_url_is_set(monkeypatch):
    app = real_run_app(monkeypatch, FAKE_DATABASE_URL)
    assert app.config["DATABASE_URL"] == FAKE_DATABASE_URL


def test_postgresql_and_postgres_schemes_are_both_accepted(monkeypatch):
    url = "postgres://fake-user@fake-host.invalid/fake-db"
    app = real_run_app(monkeypatch, url)
    assert app.config["DATABASE_URL"] == url


def test_real_run_uses_sqlite_when_database_url_is_empty(monkeypatch):
    app = real_run_app(monkeypatch, "")
    assert "DATABASE_URL" not in app.config
    assert app.config["DATABASE"].endswith("einig.sqlite")


def test_database_url_with_only_spaces_counts_as_not_set(monkeypatch):
    """Edge case: a blank value in the hosting settings must not break the app."""
    app = real_run_app(monkeypatch, "   ")
    assert "DATABASE_URL" not in app.config
    assert app.config["DATABASE"].endswith("einig.sqlite")


def test_invalid_database_url_is_rejected_without_showing_it(monkeypatch):
    """Rejected: wrong scheme stops the app; the message names the variable, never the value."""
    secret_url = "mysql://admin:very-secret-password@fake-host.invalid/db"
    with pytest.raises(RuntimeError) as error:
        real_run_app(monkeypatch, secret_url)
    message = str(error.value)
    assert "DATABASE_URL" in message
    assert "very-secret-password" not in message
    assert secret_url not in message


def test_creating_the_app_does_not_connect_to_the_database(fake_postgres, postgres_app):
    """The health check must answer even if the database is unreachable."""
    response = postgres_app.test_client().get("/health")
    assert response.status_code == 200
    assert "url" not in fake_postgres  # psycopg.connect was never called


def test_tests_use_sqlite_even_when_database_url_is_in_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", FAKE_DATABASE_URL)
    app = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": str(tmp_path / "t.sqlite")}
    )
    assert "DATABASE_URL" not in app.config


# --- Translating SQL for Postgres ----------------------------------------------

def test_question_mark_placeholders_become_percent_s():
    sql = "SELECT * FROM votes WHERE room_id = ? AND option_id = ?"
    assert db.to_postgres_sql(sql) == "SELECT * FROM votes WHERE room_id = %s AND option_id = %s"


def test_question_mark_inside_quoted_text_is_kept():
    sql = "SELECT * FROM options WHERE label = 'Pizza?' AND room_id = ?"
    assert db.to_postgres_sql(sql) == "SELECT * FROM options WHERE label = 'Pizza?' AND room_id = %s"


def test_literal_percent_sign_is_doubled():
    """psycopg reads a single % as the start of a placeholder."""
    sql = "SELECT * FROM options WHERE label LIKE 'Pizza%' AND room_id = ?"
    assert db.to_postgres_sql(sql) == "SELECT * FROM options WHERE label LIKE 'Pizza%%' AND room_id = %s"


def test_schema_integer_primary_key_counts_up_on_postgres():
    script = "CREATE TABLE IF NOT EXISTS votes (\n    id INTEGER PRIMARY KEY,\n    rating TEXT\n);"
    translated = db.schema_to_postgres(script)
    assert "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY," in translated


def test_schema_text_primary_key_is_unchanged():
    script = "CREATE TABLE IF NOT EXISTS rooms (\n    id TEXT PRIMARY KEY\n);"
    assert "id TEXT PRIMARY KEY" in db.schema_to_postgres(script)


def test_schema_insert_or_ignore_becomes_on_conflict_do_nothing():
    script = "INSERT OR IGNORE INTO app_info (key, value) VALUES ('schema_version', '0');"
    translated = db.schema_to_postgres(script)
    assert "INSERT OR IGNORE" not in translated
    assert "INSERT INTO app_info (key, value) VALUES ('schema_version', '0') ON CONFLICT DO NOTHING;" in translated


def test_schema_comments_are_removed():
    """Comments may mention SQLite words like INSERT OR IGNORE; they must not be translated."""
    script = '-- only creates what is missing ("INSERT OR IGNORE")\nCREATE TABLE IF NOT EXISTS a (key TEXT);'
    translated = db.schema_to_postgres(script)
    assert "--" not in translated
    assert "CREATE TABLE IF NOT EXISTS a (key TEXT);" in translated


def test_schema_current_timestamp_becomes_utc_text_on_postgres():
    """Times must be 'YYYY-MM-DD HH:MM:SS' UTC text on both databases, so they compare as text."""
    script = "CREATE TABLE IF NOT EXISTS rooms (\n    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n);"
    translated = db.schema_to_postgres(script)
    assert (
        "created_at TEXT NOT NULL DEFAULT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"
        in translated
    )


def test_real_schema_has_no_sqlite_only_syntax_after_translation():
    script = (PROJECT_ROOT / "app" / "schema.sql").read_text(encoding="utf-8")
    translated = db.schema_to_postgres(script)
    assert "INSERT OR IGNORE" not in translated
    assert "INTEGER PRIMARY KEY" not in translated.replace("AS IDENTITY PRIMARY KEY", "")
    assert "CURRENT_TIMESTAMP" not in translated


# --- The Postgres path through get_db(), init-db and reset-db ---------------------

def test_get_db_connects_to_postgres_with_dict_rows(fake_postgres, postgres_app):
    with postgres_app.app_context():
        get_db()
    assert fake_postgres["url"] == FAKE_DATABASE_URL
    assert fake_postgres["keyword_arguments"].get("row_factory") is dict_row


def test_get_db_translates_placeholders_on_postgres(fake_postgres, postgres_app):
    with postgres_app.app_context():
        get_db().execute("SELECT value FROM app_info WHERE key = ?", ("schema_version",))
    assert ("SELECT value FROM app_info WHERE key = %s", ("schema_version",)) in fake_postgres[
        "connection"
    ].statements


def test_postgres_connection_sends_no_pragma(fake_postgres, postgres_app):
    with postgres_app.app_context():
        get_db().execute("SELECT 1")
    assert "PRAGMA" not in fake_postgres["connection"].all_sql()


def test_postgres_connection_is_closed_after_the_request(fake_postgres, postgres_app):
    with postgres_app.app_context():
        get_db()
    assert fake_postgres["connection"].closed


def test_init_db_sends_translated_schema_to_postgres(fake_postgres, postgres_app):
    with postgres_app.app_context():
        init_db()
    sent = fake_postgres["connection"].all_sql()
    assert "CREATE TABLE IF NOT EXISTS app_info" in sent
    assert "ON CONFLICT DO NOTHING" in sent
    assert "INSERT OR IGNORE" not in sent


def test_reset_db_on_postgres_drops_tables_without_sqlite_commands(fake_postgres, postgres_app):
    result = postgres_app.test_cli_runner().invoke(args=["reset-db"], input="y\n")
    assert "Database reset" in result.output
    sent = fake_postgres["connection"].all_sql()
    assert "information_schema.tables" in sent
    assert 'DROP TABLE "app_info" CASCADE' in sent
    assert 'DROP TABLE "rooms" CASCADE' in sent
    assert "sqlite_master" not in sent
    assert "PRAGMA" not in sent


# --- Transactions (review of PR #7, point 2) ------------------------------------------

def test_transaction_commits_without_closing_on_postgres(fake_postgres, postgres_app):
    connection = fake_postgres["connection"]
    with postgres_app.app_context():
        with db.transaction():
            get_db().execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("a", "1"))
        get_db().execute("SELECT 1")  # still usable after the block
    assert connection.commit_count == 1
    assert connection.rollback_count == 0


def test_transaction_rolls_back_on_error_on_postgres(fake_postgres, postgres_app):
    connection = fake_postgres["connection"]
    connection.fail_on = "INSERT"
    with postgres_app.app_context():
        with pytest.raises(db.INTEGRITY_ERRORS):
            with db.transaction():
                get_db().execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("a", "1"))
        get_db().execute("SELECT 1")  # still usable after the rollback
    assert connection.rollback_count == 1
    assert connection.commit_count == 0


def test_transaction_commits_and_keeps_connection_open_on_sqlite(app):
    with app.app_context():
        with db.transaction():
            get_db().execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("in_transaction", "yes"))
        get_db().rollback()  # a commit already happened, so nothing is undone
        row = get_db().execute("SELECT value FROM app_info WHERE key = ?", ("in_transaction",)).fetchone()
    assert row["value"] == "yes"


def test_transaction_rolls_back_every_statement_on_error_on_sqlite(app):
    """Rejected: if the second statement fails, the first one is undone too."""
    with app.app_context():
        with pytest.raises(db.INTEGRITY_ERRORS):
            with db.transaction():
                get_db().execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("first", "1"))
                get_db().execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("first", "2"))
        row = get_db().execute("SELECT value FROM app_info WHERE key = ?", ("first",)).fetchone()
    assert row is None


def test_create_room_with_creator_works_on_postgres(fake_postgres, postgres_app):
    connection = fake_postgres["connection"]
    with postgres_app.app_context():
        created = db.create_room_with_creator("room-a", "Dinner", "manual", "Mika", "token-1")
        get_db().execute("SELECT 1")  # the connection is still open for the rest of the request
    assert created is True
    sent = connection.all_sql()
    assert "INSERT INTO rooms" in sent
    assert "INSERT INTO participants" in sent
    assert "?" not in sent
    assert connection.commit_count == 1


def test_create_room_with_creator_returns_false_on_postgres_duplicate(fake_postgres, postgres_app):
    """Rejected: a duplicate on Postgres is caught, rolled back, and reported as False."""
    connection = fake_postgres["connection"]
    connection.fail_on = "INSERT INTO participants"
    with postgres_app.app_context():
        created = db.create_room_with_creator("room-a", "Dinner", "manual", "Mika", "token-1")
    assert created is False
    assert connection.rollback_count == 1
    assert connection.commit_count == 0


def test_add_participant_works_on_postgres(fake_postgres, postgres_app):
    """F2 join (merged from main) must also use db.transaction(), not "with connection:"."""
    connection = fake_postgres["connection"]
    with postgres_app.app_context():
        added = db.add_participant("room-a", "Anna", "token-2")
        get_db().execute("SELECT 1")  # the connection is still open for the rest of the request
    assert added is True
    assert "INSERT INTO participants" in connection.all_sql()
    assert connection.commit_count == 1


def test_add_participant_returns_false_on_postgres_duplicate(fake_postgres, postgres_app):
    """Rejected: the same nickname saved a moment earlier is caught on Postgres, not a crash."""
    connection = fake_postgres["connection"]
    connection.fail_on = "INSERT INTO participants"
    with postgres_app.app_context():
        added = db.add_participant("room-a", "Anna", "token-2")
    assert added is False
    assert connection.rollback_count == 1
    assert connection.commit_count == 0


# --- The same interface on SQLite -------------------------------------------------

def test_integrity_errors_cover_both_databases():
    assert sqlite3.IntegrityError in db.INTEGRITY_ERRORS
    assert psycopg.IntegrityError in db.INTEGRITY_ERRORS


def test_insert_returning_id_works_on_sqlite(app):
    """Accepted: RETURNING gives the new id on both databases (Postgres has no lastrowid)."""
    with app.app_context():
        connection = get_db()
        connection.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
        row = connection.execute("INSERT INTO notes (text) VALUES (?) RETURNING id", ("hello",)).fetchone()
        connection.commit()
        assert row["id"] == 1


def test_duplicate_key_is_rejected_and_data_unchanged(app):
    """Rejected: a broken UNIQUE rule raises a catchable error and keeps the saved row."""
    with app.app_context():
        connection = get_db()
        # Own row, so the test does not depend on the schema version (review of PR #7, point 1).
        connection.execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("duplicate_check", "original"))
        connection.commit()
        with pytest.raises(db.INTEGRITY_ERRORS):
            connection.execute(
                "INSERT INTO app_info (key, value) VALUES (?, ?)", ("duplicate_check", "changed")
            )
        connection.rollback()
        row = connection.execute(
            "SELECT value FROM app_info WHERE key = ?", ("duplicate_check",)
        ).fetchone()
        assert row["value"] == "original"


def test_accepted_rows_survive_a_restart(app):
    """A new app object on the same database (= restart) still sees the saved row."""
    with app.app_context():
        connection = get_db()
        connection.execute("INSERT INTO app_info (key, value) VALUES (?, ?)", ("restart_check", "kept"))
        connection.commit()

    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": app.config["DATABASE"]}
    )
    with restarted.app_context():
        row = get_db().execute(
            "SELECT value FROM app_info WHERE key = ?", ("restart_check",)
        ).fetchone()
    assert row["value"] == "kept"


# --- Hosting config ----------------------------------------------------------------

def read_render_config() -> str:
    return (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")


def test_render_config_builds_with_pinned_dependencies():
    assert "uv sync --frozen --no-dev" in read_render_config()


def test_render_config_starts_with_init_db_then_gunicorn_on_port():
    config = read_render_config()
    assert "init-db" in config
    assert "gunicorn" in config
    assert "$PORT" in config
    assert config.index("init-db") < config.index("gunicorn")


def test_render_config_uses_the_health_check():
    assert "healthCheckPath: /health" in read_render_config()


def test_render_config_lists_secrets_without_values():
    config = read_render_config()
    for name in ["SECRET_KEY", "DATABASE_URL", "GOOGLE_MAPS_API_KEY", "GOOGLE_MAPS_EMBED_KEY"]:
        assert f"key: {name}" in config
    assert "value:" not in config  # values live only in Render's secret settings


def test_psycopg_is_a_pinned_dependency():
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"psycopg[binary]==' in pyproject
