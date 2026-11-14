"""Extra join tests from mkim-nova's review of PR #9 (specs/a3-join-room.md).

These live in a new file because tests/test_join.py was already reviewed
and must not be edited.
"""

import pytest

from app.db import get_db

TAKEN_MESSAGE = "This nickname is already taken in this room. Please choose another one."


def create_room(client, nickname):
    """Create a room as its creator and return the room id."""
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def participant_count(app):
    """Return how many participants are saved in all rooms."""
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM participants").fetchone()[0]


@pytest.mark.parametrize(
    "creator_nickname, joining_nickname",
    [
        ("Ärger", "ärger"),
        ("ärger", "ÄRGER"),
        ("Élodie", "élodie"),
        ("Łukasz", "łukasz"),
        ("Ömer", "öMER"),
    ],
)
def test_taken_nickname_with_non_ascii_letters_is_rejected(
    app, client, creator_nickname, joining_nickname
):
    room_id = create_room(client, creator_nickname)
    guest = app.test_client()
    before = participant_count(app)

    response = guest.post(f"/rooms/{room_id}/join", data={"nickname": joining_nickname})

    assert response.status_code == 400
    assert TAKEN_MESSAGE in response.data.decode()
    assert participant_count(app) == before


def test_different_non_ascii_nickname_is_accepted(app, client):
    room_id = create_room(client, "Ärger")
    guest = app.test_client()
    response = guest.post(f"/rooms/{room_id}/join", data={"nickname": "Arger"})
    assert response.status_code in (302, 303)
    assert participant_count(app) == 2
