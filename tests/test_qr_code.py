"""Tests for A6 – F22 QR code for the invite link (specs/a6-qr-code.md)."""

import ast
from pathlib import Path

import pytest
import segno

from app.db import get_db
from app.services.qr import invite_qr_svg

QR_TITLE = "QR code to join this room"
CAPTION = "Scan to join this room."
QR_FILE = Path(__file__).resolve().parents[1] / "app" / "services" / "qr.py"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner on Friday", nickname="Anna"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    """Join a room (A3) in this browser."""
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def invite_url(room_id):
    """The invite URL the test client sees (A2 builds it with _external=True)."""
    return f"http://localhost/rooms/{room_id}"


def expected_svg(room_id):
    """The QR code the spec asks for, built directly with segno."""
    return segno.make(invite_url(room_id), error="m").svg_inline(scale=4, title=QR_TITLE)


def room_page(client, room_id):
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    return response.data.decode()


def lobby_page(client, room_id):
    response = client.get(f"/rooms/{room_id}/lobby")
    assert response.status_code == 200
    return response.data.decode()


def set_room_status(app, room_id, status):
    """Change a room's status directly in the database (closing comes in B3)."""
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


@pytest.fixture
def room_id(client):
    """A room created by "Anna" in the creator's browser (the `client` fixture)."""
    return create_room(client)


@pytest.fixture
def guest(app, room_id):
    """A second browser that has joined the room as "Ben"."""
    browser = app.test_client()
    join(browser, room_id, "Ben")
    return browser


# --- services/qr.py --------------------------------------------------------

def test_invite_qr_svg_returns_svg_with_title():
    svg = invite_qr_svg("http://localhost/rooms/abc")
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert f"<title>{QR_TITLE}</title>" in svg


def test_invite_qr_svg_encodes_the_given_url():
    url = "http://localhost/rooms/abc"
    assert invite_qr_svg(url) == segno.make(url, error="m").svg_inline(scale=4, title=QR_TITLE)


def test_invite_qr_svg_uses_error_level_m_for_a_deployed_url():
    # segno raises the error level by itself when it fits, so for short test URLs
    # "l" and "m" give the same code. A URL as long as the deployed one tells them apart.
    url = "https://einig.onrender.com/rooms/AbCdEfGhIjK"
    assert invite_qr_svg(url) == segno.make(url, error="m").svg_inline(scale=4, title=QR_TITLE)
    assert invite_qr_svg(url) != segno.make(url, error="l").svg_inline(scale=4, title=QR_TITLE)


def test_same_url_same_code_different_url_different_code():
    first = invite_qr_svg("http://localhost/rooms/abc")
    assert invite_qr_svg("http://localhost/rooms/abc") == first
    assert invite_qr_svg("http://localhost/rooms/xyz") != first


def test_qr_service_imports_neither_flask_nor_db():
    tree = ast.parse(QR_FILE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)
            imported.update(f"{module}.{alias.name}" for alias in node.names)
    assert not any(name == "flask" or name.startswith("flask.") for name in imported)
    assert not any(name in ("app.db", "app") or name.startswith("app.db") for name in imported)


# --- Pages -----------------------------------------------------------------

def test_creator_and_participant_see_qr_code_on_room_page(client, guest, room_id):
    for browser in (client, guest):
        html = room_page(browser, room_id)
        assert expected_svg(room_id) in html
        assert CAPTION in html


def test_participant_sees_qr_code_in_lobby(client, guest, room_id):
    for browser in (client, guest):
        html = lobby_page(browser, room_id)
        assert expected_svg(room_id) in html
        assert CAPTION in html


def test_each_room_shows_its_own_qr_code(client, room_id):
    other_room_id = create_room(client, title="Saturday")
    html = room_page(client, other_room_id)
    assert expected_svg(other_room_id) in html
    assert expected_svg(room_id) not in html


@pytest.mark.parametrize("status", ["collecting", "voting"])
def test_qr_code_is_shown_while_room_is_open(app, client, room_id, status):
    set_room_status(app, room_id, status)
    assert expected_svg(room_id) in room_page(client, room_id)
    assert expected_svg(room_id) in lobby_page(client, room_id)


def test_qr_code_is_hidden_when_room_is_closed(app, client, room_id):
    set_room_status(app, room_id, "closed")
    for html in (room_page(client, room_id), lobby_page(client, room_id)):
        assert QR_TITLE not in html
        assert CAPTION not in html


def test_visitor_sees_no_qr_code(app, room_id):
    visitor = app.test_client()
    html = room_page(visitor, room_id)
    assert QR_TITLE not in html
    assert CAPTION not in html


def test_qr_code_is_inline_without_external_image_or_script(client, room_id):
    for html in (room_page(client, room_id), lobby_page(client, room_id)):
        # The code itself is in the page, so nothing has to be loaded for it.
        assert expected_svg(room_id) in html
        assert '<img src="http' not in html
        assert "qr" not in " ".join(
            line for line in html.splitlines() if "<script" in line
        ).lower()


def test_room_title_stays_escaped_next_to_qr_code(app):
    browser = app.test_client()
    room_id = create_room(browser, title="<b>Dinner</b>")
    for html in (room_page(browser, room_id), lobby_page(browser, room_id)):
        assert expected_svg(room_id) in html
        assert "<b>Dinner</b>" not in html
        assert "&lt;b&gt;Dinner&lt;/b&gt;" in html
