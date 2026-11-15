"""Tests for C1c – several requests at once on Render (specs/c1c-gunicorn-workers.md).

The first part reads render.yaml as text (pyyaml is not a dependency) and checks
the gunicorn part of the start command. The second part checks that the app is
safe to run in several threads: every request gets its own database connection.
"""

import shlex
import sqlite3
import threading
from pathlib import Path

from app import db
from app.db import get_db

PROJECT_ROOT = Path(__file__).parent.parent
THREAD_COUNT = 8  # as many requests as 2 workers x 4 threads can run at once


# --- Helpers -----------------------------------------------------------------

def read_start_command() -> str:
    """Return the value of the startCommand line in render.yaml."""
    config = (PROJECT_ROOT / "render.yaml").read_text(encoding="utf-8")
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.startswith("startCommand:"):
            return stripped.removeprefix("startCommand:").strip()
    raise AssertionError("render.yaml has no startCommand line")


def gunicorn_arguments() -> list[str]:
    """Split the start command and return only the words of the gunicorn command."""
    commands = read_start_command().split("&&")
    gunicorn_commands = [command for command in commands if "gunicorn" in command]
    assert len(gunicorn_commands) == 1, "expected exactly one gunicorn command"
    words = shlex.split(gunicorn_commands[0])
    # Everything after the word "gunicorn" belongs to gunicorn (not to "uv run").
    return words[words.index("gunicorn") + 1:]


def option_value(arguments: list[str], name: str) -> str:
    """Return the value written right after an option like --workers."""
    assert name in arguments, f"gunicorn is started without {name}"
    return arguments[arguments.index(name) + 1]


def run_in_threads(target, count: int) -> list:
    """Run target(index, barrier) in `count` threads at once; return results, re-raise errors."""
    barrier = threading.Barrier(count, timeout=10)
    results = [None] * count
    errors = []

    def run(index):
        try:
            results[index] = target(index, barrier)
        except BaseException as error:  # collect, so the test (main thread) can fail on it
            errors.append(error)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    if errors:
        raise errors[0]
    return results


# --- The start command in render.yaml -------------------------------------------

def test_gunicorn_starts_two_workers():
    assert option_value(gunicorn_arguments(), "--workers") == "2"


def test_gunicorn_starts_four_threads_per_worker():
    assert option_value(gunicorn_arguments(), "--threads") == "4"


def test_gunicorn_timeout_is_written_out_as_30_seconds():
    assert option_value(gunicorn_arguments(), "--timeout") == "30"


def test_new_flags_belong_to_gunicorn_not_to_init_db():
    """Edge case: the flags must not end up on the init-db command before it."""
    init_db_commands = [c for c in read_start_command().split("&&") if "init-db" in c]
    assert len(init_db_commands) == 1
    for flag in ["--workers", "--threads", "--timeout"]:
        assert flag not in init_db_commands[0]


def test_gunicorn_still_binds_the_render_port_and_loads_the_app():
    arguments = gunicorn_arguments()
    assert option_value(arguments, "--bind") == "0.0.0.0:$PORT"
    # shlex removes the quotes, so the app appears as one word.
    assert "app:create_app()" in arguments


def test_worker_count_stays_inside_the_free_plan_memory():
    """Edge case: each worker is a full copy of the app (about 55 MB); Render free has 512 MB."""
    assert 1 <= int(option_value(gunicorn_arguments(), "--workers")) <= 2


def test_server_can_handle_at_least_two_requests_at_once():
    """Edge case: one slow Google call must not block everyone else."""
    arguments = gunicorn_arguments()
    workers = int(option_value(arguments, "--workers"))
    threads = int(option_value(arguments, "--threads"))
    assert workers * threads >= 2


# --- The app is safe to run in several threads ------------------------------------

def test_requests_in_two_threads_get_their_own_connection_and_both_are_closed(app):
    """Two requests open at the same moment never share a database connection."""

    def open_connection(index, barrier):
        with app.app_context():
            connection = get_db()
            connection.execute("SELECT 1")
            barrier.wait()  # both connections are open at the same time here
        # After the request (app context) ends, close_db must have closed it.
        try:
            connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            closed = True
        else:
            closed = False
        return connection, closed

    results = run_in_threads(open_connection, 2)
    (first_connection, first_closed), (second_connection, second_closed) = results
    assert first_connection is not second_connection
    assert first_closed and second_closed


def test_rooms_created_in_parallel_threads_are_all_saved(app):
    """Accepted: eight people creating a room at the same moment all get their room."""

    def create_room(index, barrier):
        client = app.test_client()  # every thread is its own browser
        barrier.wait()  # send all requests at the same moment
        return client.post(
            "/rooms", data={"title": f"Room {index}", "mode": "manual", "nickname": f"Person {index}"}
        )

    responses = run_in_threads(create_room, THREAD_COUNT)
    assert all(response.status_code in (302, 303) for response in responses)

    with app.app_context():
        rooms = get_db().execute("SELECT id, title FROM rooms").fetchall()
        creators = get_db().execute(
            "SELECT room_id, nickname FROM participants WHERE is_creator = 1"
        ).fetchall()
    assert sorted(row["title"] for row in rooms) == sorted(f"Room {i}" for i in range(THREAD_COUNT))
    # Every room has exactly its own creator: no room without one, none mixed up.
    assert {row["room_id"] for row in creators} == {row["id"] for row in rooms}
    assert len(creators) == THREAD_COUNT


def test_close_db_is_registered_for_the_end_of_every_request(app):
    """Without this, connections opened by threads would stay open."""
    assert db.close_db in app.teardown_appcontext_funcs
