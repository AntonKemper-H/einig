"""Shared test fixtures: an app with a temporary database and a test client."""

import pytest

from app import create_app
from app.db import init_db


@pytest.fixture
def app(tmp_path):
    """Create an app that uses a fresh SQLite file in a temporary folder."""
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-not-a-real-key",
            "DATABASE": str(tmp_path / "test.sqlite"),
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture
def client(app):
    """A browser-like client that sends requests to the test app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Runs Flask CLI commands (e.g. init-db) against the test app."""
    return app.test_cli_runner()
