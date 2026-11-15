"""Extra lobby tests from mkim-nova's review of PR #15 (specs/a5-lobby.md).

These live in a new file because tests/test_lobby.py was already reviewed
and must not be edited.
"""

import pytest

from app.services.lobby import status_text

TOO_FEW_OPTIONS_MESSAGE = "Add at least 2 options before starting the voting."
WAITING_MESSAGE = "Waiting for the creator to start the voting."


def create_room(client):
    """Create a room as its creator "Anna" and return the room id."""
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": "Anna"})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def add_options(client, room_id, labels):
    for label in labels:
        response = client.post(f"/rooms/{room_id}/options", data={"label": label})
        assert response.status_code in (302, 303)


def lobby_html(client, room_id):
    response = client.get(f"/rooms/{room_id}/lobby")
    assert response.status_code == 200
    return response.data.decode()


@pytest.fixture
def room_id(client):
    return create_room(client)


# --- Point 1: the creator sees why the start is not possible yet ------------

@pytest.mark.parametrize("labels", [[], ["Pizza place"]], ids=["no-options", "one-option"])
def test_creator_sees_too_few_options_hint_in_lobby(client, room_id, labels):
    # Shown on the normal lobby page, so it stays visible across the refresh.
    add_options(client, room_id, labels)
    html = lobby_html(client, room_id)
    assert TOO_FEW_OPTIONS_MESSAGE in html
    assert f'action="/rooms/{room_id}/start"' in html


def test_no_hint_with_enough_options(client, room_id):
    add_options(client, room_id, ["Pizza place", "Cinema"])
    assert TOO_FEW_OPTIONS_MESSAGE not in lobby_html(client, room_id)


def test_other_participant_sees_no_hint(app, room_id):
    guest = app.test_client()
    response = guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"})
    assert response.status_code in (302, 303)
    html = lobby_html(guest, room_id)
    assert TOO_FEW_OPTIONS_MESSAGE not in html
    assert WAITING_MESSAGE in html


def test_rejected_start_shows_message_once(client, room_id):
    response = client.post(f"/rooms/{room_id}/start")
    assert response.status_code == 400
    assert response.data.decode().count(TOO_FEW_OPTIONS_MESSAGE) == 1


# --- Point 2: an unknown status never crashes the lobby ---------------------

def test_status_text_of_unknown_status_is_empty():
    assert status_text("archived") == ""


def test_lobby_with_unknown_status_does_not_crash(client, room_id, monkeypatch):
    monkeypatch.setattr(
        "app.db.get_room",
        lambda room_id: {"id": room_id, "title": "Dinner", "mode": "manual", "status": "archived"},
    )
    html = lobby_html(client, room_id)
    assert "Lobby" in html
