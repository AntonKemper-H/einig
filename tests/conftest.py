"""Shared pytest fixtures for the Einig tests."""

import pytest

from app import create_app


@pytest.fixture
def app():
    """An application instance configured for tests."""
    return create_app(
        {
            "TESTING": True,
            # Not a real secret: the tests only need signed cookies to work.
            "SECRET_KEY": "testing-only",
        }
    )


@pytest.fixture
def client(app):
    """A test client that sends requests to the test application."""
    return app.test_client()
