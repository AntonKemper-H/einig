"""Tests for the A11 fix: the creator's start hint counts hidden options too
(specs/a11-fix-start-hint.md, A11 / F28, B6).

The helpers and the fake Google come from the A11 tests; importing the autouse
`google` fixture makes it active here as well, so no test calls Google.
"""

from tests.test_hidden_collecting import (  # noqa: F401 (google is an autouse fixture)
    CREATOR_IDEA,
    GUEST_IDEA,
    add_option,
    create_room,
    google,
    join,
    page,
    query,
    save_setup,
    surprise_me,
)

TOO_FEW_OPTIONS_MESSAGE = "Add at least 2 options before starting the voting."
HINT_START = "Add at least"


def test_hidden_ideas_count_for_the_start_hint(app, client):
    room_id = create_room(client)
    assert save_setup(client, room_id, hide=True).status_code in (302, 303)
    guest = join(app, room_id)
    assert add_option(client, room_id, CREATOR_IDEA).status_code in (302, 303)
    assert add_option(guest, room_id, GUEST_IDEA).status_code in (302, 303)

    html = page(client, room_id)
    assert GUEST_IDEA not in html  # precondition: the guest's idea is hidden from the creator
    assert HINT_START not in html

    response = client.post(f"/rooms/{room_id}/start", data={"time_limit": ""})
    assert response.status_code in (302, 303)
    assert query(app, "SELECT status FROM rooms WHERE id = ?", (room_id,))[0]["status"] == "voting"


def test_one_hidden_idea_alone_still_gets_the_hint(app, client):
    room_id = create_room(client)
    assert save_setup(client, room_id, hide=True).status_code in (302, 303)
    guest = join(app, room_id)
    assert add_option(guest, room_id, GUEST_IDEA).status_code in (302, 303)

    html = page(client, room_id)
    assert GUEST_IDEA not in html
    assert TOO_FEW_OPTIONS_MESSAGE in html


def test_secret_places_count_for_the_start_hint(app, client):
    room_id = create_room(client, mode="surprise")
    assert save_setup(client, room_id, hide=True, reveal=False).status_code in (302, 303)
    surprise_me(client, room_id)

    html = page(client, room_id)
    assert "suggested places are waiting" in html  # precondition: the places are secret
    assert HINT_START not in html
