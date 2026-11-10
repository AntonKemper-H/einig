"""Tests for F0 – project skeleton (specs/f0-project-skeleton.md)."""

import os

import pytest

from app import create_app


# --- App factory -----------------------------------------------------------

def test_create_app_uses_test_config(app):
    """With a test config, the app uses it instead of environment variables."""
    assert app.testing is True
    assert app.config["SECRET_KEY"] == "test-only-not-a-real-key"


def test_app_refuses_to_start_without_secret_key(tmp_path):
    """Rejected: no SECRET_KEY means no app, with a message naming the variable."""
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.sqlite")})


# --- Home page -------------------------------------------------------------

def test_home_page_shows_app_name(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Einig" in response.data


def test_home_page_is_mobile_first(client):
    response = client.get("/")
    assert b'name="viewport"' in response.data


def test_home_page_loads_pico_css_locally(client):
    """Privacy rule: styles come from our own static folder, never from a CDN."""
    html = client.get("/").data.decode()
    assert "/static/css/pico" in html
    assert "https://" not in html


def test_pico_css_file_is_served(client):
    html = client.get("/").data.decode()
    start = html.index("/static/css/pico")
    end = html.index('"', start)
    css_url = html[start:end]
    response = client.get(css_url)
    assert response.status_code == 200


# --- Health check and errors ----------------------------------------------

def test_health_check_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.data.decode().strip() == "ok"


def test_unknown_url_shows_friendly_404(client):
    """Edge case: an unknown URL gives a 404 page, not a crash."""
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert b"Page not found" in response.data


# --- Database --------------------------------------------------------------

def test_init_db_command_creates_database(runner, app):
    os.remove(app.config["DATABASE"])
    result = runner.invoke(args=["init-db"])
    assert "Initialized the database" in result.output
    assert os.path.exists(app.config["DATABASE"])


def test_tests_use_a_temporary_database(app, tmp_path):
    """Tests must never touch a real database file."""
    assert app.config["DATABASE"].startswith(str(tmp_path))
