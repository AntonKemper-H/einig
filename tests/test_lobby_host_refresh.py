"""D25: the creator's lobby does not reload by itself while the room is collecting
(specs/e7-lobby-host-refresh.md).

The lobby reloaded every 4 seconds for everyone. The creator picks the time limit in the
lobby's start form, and every reload set the choice back to "No time limit" before they could
press "Start voting". While collecting, the creator now reloads on request with a button;
everybody else, and everybody once the voting runs, keeps the automatic reload.
"""

import re

import pytest

from app.db import get_db


def refresh_tag(room_id):
    return f'<meta http-equiv="refresh" content="4; url=/rooms/{room_id}/lobby">'


def create_room(client):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": "Anna"})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def lobby_html(client, room_id):
    response = client.get(f"/rooms/{room_id}/lobby")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def set_status(app, room_id, status):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def refresh_button(html, room_id):
    return re.search(rf'<a\b[^>]*href="/rooms/{room_id}/lobby"[^>]*>\s*Refresh\s*</a>', html)


@pytest.fixture
def room(app, client):
    room_id = create_room(client)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"}).status_code in (302, 303)
    return room_id, guest


def test_the_creator_lobby_does_not_reload_by_itself_while_collecting(client, room):
    room_id, _ = room
    html = lobby_html(client, room_id)
    assert 'http-equiv="refresh"' not in html
    assert refresh_button(html, room_id)
    assert 'name="time_limit"' in html  # the choice that used to be reset


def test_guests_keep_the_automatic_reload_while_collecting(client, room):
    room_id, guest = room
    html = lobby_html(guest, room_id)
    assert refresh_tag(room_id) in html
    assert not refresh_button(html, room_id)


def test_everybody_reloads_automatically_while_voting(app, client, room):
    room_id, guest = room
    set_status(app, room_id, "voting")
    for browser in (client, guest):
        html = lobby_html(browser, room_id)
        assert refresh_tag(room_id) in html
        assert not refresh_button(html, room_id)


def test_nobody_reloads_in_a_closed_room(app, client, room):
    room_id, guest = room
    set_status(app, room_id, "closed")
    for browser in (client, guest):
        assert 'http-equiv="refresh"' not in lobby_html(browser, room_id)


def test_a_rejected_start_shows_the_refresh_button_and_never_reloads_the_post(client, room):
    room_id, _ = room
    response = client.post(f"/rooms/{room_id}/start", data={"time_limit": "15"})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert 'http-equiv="refresh"' not in html
    assert refresh_button(html, room_id)
    assert f"url=/rooms/{room_id}/start" not in html
