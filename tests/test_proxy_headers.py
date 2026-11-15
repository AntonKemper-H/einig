"""Tests for C1b – invite link with https behind Render's proxy (specs/c1b-proxy-https.md)."""

import re

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.db import get_db, init_db

ROOM_FORM = {"title": "Dinner on Friday", "mode": "manual", "nickname": "Anna"}
RENDER_HOST = "nod-lqeq.onrender.com"
HTTPS_HEADERS = {"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.7"}


# --- Helpers ---------------------------------------------------------------

def make_app(tmp_path, trust_proxy_headers: bool):
    """Create a test app with a fresh SQLite file and the proxy switch on or off."""
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-not-a-real-key",
            "DATABASE": str(tmp_path / "test.sqlite"),
            "TRUST_PROXY_HEADERS": trust_proxy_headers,
        }
    )
    with app.app_context():
        init_db()
    return app


def real_run_app(monkeypatch, trust_value: str | None):
    """Build the app like the real server does (no test config) with the given switch value."""
    monkeypatch.setenv("SECRET_KEY", "test-only-not-a-real-key")
    # Setting the variables (even to "") stops load_dotenv from taking values from a local .env.
    monkeypatch.setenv("DATABASE_URL", "")
    if trust_value is None:
        monkeypatch.setenv("TRUST_PROXY_HEADERS", "")
    else:
        monkeypatch.setenv("TRUST_PROXY_HEADERS", trust_value)
    return create_app()


def create_room(client, headers=None, base_url="http://localhost"):
    """Create a room and return its id, read from the redirect target /rooms/<room_id>."""
    response = client.post("/rooms", data=ROOM_FORM, headers=headers or {}, base_url=base_url)
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def room_page(client, room_id, headers=None, base_url="http://localhost"):
    """Return the HTML of the room page for the participant stored in the client's cookie."""
    response = client.get(f"/rooms/{room_id}", headers=headers or {}, base_url=base_url)
    assert response.status_code == 200
    return response.data.decode()


def invite_urls_in(html):
    """Return the invite link from the text field, the link target and the link text."""
    field = re.search(r'value="([^"]+)" aria-label="Invite link"', html).group(1)
    anchor = re.search(r'<a href="([^"]+/rooms/[^"]+)">([^<]+)</a>', html)
    return field, anchor.group(1), anchor.group(2)


def count_rows(app, table):
    """Count the rows of one table."""
    with app.app_context():
        return get_db().execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()["total"]


# --- Switch TRUST_PROXY_HEADERS ---------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "True", "  true  "])
def test_real_run_switch_on_for_1_or_true(monkeypatch, value):
    app = real_run_app(monkeypatch, value)
    assert app.config["TRUST_PROXY_HEADERS"] is True


@pytest.mark.parametrize("value", [None, "", "   ", "0", "false", "no", "yes please"])
def test_real_run_switch_off_by_default_and_for_other_values(monkeypatch, value):
    app = real_run_app(monkeypatch, value)
    assert app.config["TRUST_PROXY_HEADERS"] is False
    assert not isinstance(app.wsgi_app, ProxyFix)


def test_tests_ignore_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    app = make_app(tmp_path, trust_proxy_headers=False)
    assert app.config["TRUST_PROXY_HEADERS"] is False
    assert not isinstance(app.wsgi_app, ProxyFix)


# --- Switch on (deployed on Render) -------------------------------------------

def test_switch_on_wraps_app_in_proxy_fix_trusting_only_the_scheme(tmp_path):
    app = make_app(tmp_path, trust_proxy_headers=True)
    assert isinstance(app.wsgi_app, ProxyFix)
    assert app.wsgi_app.x_proto == 1
    assert app.wsgi_app.x_for == 0
    assert app.wsgi_app.x_host == 0


def test_switch_on_forwarded_https_gives_https_invite_link(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=True).test_client()
    base_url = f"http://{RENDER_HOST}"
    room_id = create_room(client, HTTPS_HEADERS, base_url)
    html = room_page(client, room_id, HTTPS_HEADERS, base_url)
    assert f"https://{RENDER_HOST}/rooms/{room_id}" in html
    assert f"http://{RENDER_HOST}/rooms/{room_id}" not in html


def test_switch_on_forwarded_host_is_ignored(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=True).test_client()
    base_url = f"http://{RENDER_HOST}"
    headers = {**HTTPS_HEADERS, "X-Forwarded-Host": "evil.example"}
    room_id = create_room(client, headers, base_url)
    html = room_page(client, room_id, headers, base_url)
    assert f"https://{RENDER_HOST}/rooms/{room_id}" in html
    assert "evil.example" not in html


def test_switch_on_without_headers_keeps_local_http_link(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=True).test_client()
    room_id = create_room(client)
    html = room_page(client, room_id)
    assert f"http://localhost/rooms/{room_id}" in html
    assert "https://" not in html


def test_switch_on_invite_link_is_identical_in_field_href_and_text(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=True).test_client()
    base_url = f"http://{RENDER_HOST}"
    room_id = create_room(client, HTTPS_HEADERS, base_url)
    field, href, text = invite_urls_in(room_page(client, room_id, HTTPS_HEADERS, base_url))
    expected = f"https://{RENDER_HOST}/rooms/{room_id}"
    assert field == href == text == expected


# --- Switch off (default, local) ----------------------------------------------

def test_switch_off_does_not_wrap_app(tmp_path):
    app = make_app(tmp_path, trust_proxy_headers=False)
    assert not isinstance(app.wsgi_app, ProxyFix)


def test_switch_off_ignores_forwarded_headers(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=False).test_client()
    headers = {**HTTPS_HEADERS, "X-Forwarded-Host": "evil.example"}
    room_id = create_room(client, headers)
    html = room_page(client, room_id, headers)
    assert f"http://localhost/rooms/{room_id}" in html
    assert "evil.example" not in html
    assert f"https://localhost/rooms/{room_id}" not in html


def test_switch_off_invite_link_is_identical_in_field_href_and_text(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=False).test_client()
    room_id = create_room(client)
    field, href, text = invite_urls_in(room_page(client, room_id))
    assert field == href == text == f"http://localhost/rooms/{room_id}"


# --- Nothing else changes -----------------------------------------------------

@pytest.mark.parametrize("trust", [True, False])
def test_creating_a_room_stores_room_and_creator_with_switch_on_or_off(tmp_path, trust):
    app = make_app(tmp_path, trust_proxy_headers=trust)
    client = app.test_client()
    create_room(client, HTTPS_HEADERS)
    assert count_rows(app, "rooms") == 1
    assert count_rows(app, "participants") == 1


def test_health_still_ok_with_switch_on(tmp_path):
    client = make_app(tmp_path, trust_proxy_headers=True).test_client()
    response = client.get("/health", headers=HTTPS_HEADERS)
    assert response.status_code == 200
    assert response.data.decode().strip() == "ok"
