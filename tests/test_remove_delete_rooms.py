"""Tests for E3 – remove a room from my list, and delete a room (specs/e3-remove-and-delete-rooms.md)."""

import pytest

from app.db import get_db

ONLY_CREATOR_MESSAGE = "Only the creator can delete this room."
DELETE_WARNING = "This deletes the room for everyone"
REMOVE_HINT = "You cannot get back into it as the same person."
CREATOR_WARNING = "You are the creator: nobody else can start or close this room."
CREATE_HEADING = "Create a room"
STATUSES = ["collecting", "voting", "closed"]
ROOM_TABLES = ["participants", "options", "votes", "vetoes", "option_authors", "room_setups", "group_rooms"]


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def rows(app, sql, params=()):
    with app.app_context():
        return [tuple(row) for row in get_db().execute(sql, params)]


def count(app, table, room_id):
    return rows(app, f"SELECT COUNT(*) FROM {table} WHERE room_id = ?", (room_id,))[0][0]


def set_status(app, room_id, status):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def fill_room(app, room_id):
    """Give the room an option, a vote and a veto from its creator, so cascades have work to do."""
    with app.app_context():
        connection = get_db()
        option_id = connection.execute(
            "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', 'Pizza') RETURNING id",
            (room_id,),
        ).fetchone()["id"]
        participant_id = connection.execute(
            "SELECT id FROM participants WHERE room_id = ? AND is_creator = 1", (room_id,)
        ).fetchone()["id"]
        connection.execute(
            "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, 'yes')",
            (room_id, participant_id, option_id),
        )
        connection.execute(
            "INSERT INTO vetoes (room_id, participant_id, option_id) VALUES (?, ?, ?)",
            (room_id, participant_id, option_id),
        )
        connection.execute(
            "INSERT INTO option_authors (option_id, room_id, participant_id) VALUES (?, ?, ?)",
            (option_id, room_id, participant_id),
        )
        connection.commit()
    return option_id


def remembered(client):
    with client.session_transaction() as session:
        return dict(session.get("participant_tokens", {}))


def home(client):
    response = client.get("/")
    assert response.status_code == 200
    return response.data.decode()


def my_rooms_part(html):
    return html.split(CREATE_HEADING, 1)[0]


def room_exists(app, room_id):
    return rows(app, "SELECT COUNT(*) FROM rooms WHERE id = ?", (room_id,))[0][0] == 1


@pytest.fixture
def anna(client):
    """The creator's browser."""
    return client


@pytest.fixture
def ben(app):
    """A second browser."""
    return app.test_client()


@pytest.fixture
def room(app, anna, ben):
    """A room created by Anna that Ben joined, with an option, a vote and a veto."""
    room_id = create_room(anna, "Dinner", "Anna")
    join(ben, room_id, "Ben")
    fill_room(app, room_id)
    return room_id


# --- F31: remove from my list ------------------------------------------------

def test_home_shows_a_remove_form_for_every_room(anna, room):
    html = my_rooms_part(home(anna))
    assert f'action="/rooms/{room}/forget"' in html
    assert REMOVE_HINT in html


def test_remove_takes_the_room_off_my_list_and_redirects_home(anna, room):
    response = anna.post(f"/rooms/{room}/forget")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/")
    assert room not in remembered(anna)
    assert "Dinner" not in my_rooms_part(home(anna))


def test_remove_changes_nothing_in_the_database(app, anna, ben, room):
    before = {table: count(app, table, room) for table in ROOM_TABLES}
    ben.post(f"/rooms/{room}/forget")
    assert room_exists(app, room)
    assert {table: count(app, table, room) for table in ROOM_TABLES} == before


def test_remove_only_affects_this_browser(anna, ben, room):
    ben.post(f"/rooms/{room}/forget")
    assert room in remembered(anna)
    assert "Dinner" in my_rooms_part(home(anna))


def test_remove_keeps_the_other_rooms_of_this_browser(anna, room):
    other = create_room(anna, "Brunch", "Anna")
    anna.post(f"/rooms/{room}/forget")
    assert other in remembered(anna)
    assert "Brunch" in my_rooms_part(home(anna))


def test_remove_of_a_room_never_joined_changes_nothing(app, anna, ben, room):
    stranger = app.test_client()
    response = stranger.post(f"/rooms/{room}/forget")
    assert response.status_code in (302, 303)
    assert room_exists(app, room)
    assert room in remembered(anna)


def test_remove_twice_and_remove_of_an_unknown_room_both_redirect_home(anna, room):
    assert anna.post(f"/rooms/{room}/forget").status_code in (302, 303)
    assert anna.post(f"/rooms/{room}/forget").status_code in (302, 303)
    assert anna.post("/rooms/does-not-exist/forget").status_code in (302, 303)


def test_after_remove_the_room_link_asks_to_join_as_a_new_participant(app, anna, ben, room):
    anna.post(f"/rooms/{room}/forget")
    html = anna.get(f"/rooms/{room}").data.decode()
    assert 'name="nickname"' in html
    # Anna's old participant row is still there; she is just no longer recognised.
    assert count(app, "participants", room) == 2


def test_creator_of_an_open_room_sees_the_warning_but_a_guest_does_not(anna, ben, room):
    assert CREATOR_WARNING in my_rooms_part(home(anna))
    assert CREATOR_WARNING not in my_rooms_part(home(ben))


def test_creator_of_a_closed_room_sees_no_warning(app, anna, room):
    set_status(app, room, "closed")
    assert CREATOR_WARNING not in my_rooms_part(home(anna))


# --- F32: delete room (creator) -----------------------------------------------

def test_creator_sees_a_delete_link_and_a_guest_does_not(anna, ben, room):
    assert f'href="/rooms/{room}/delete"' in my_rooms_part(home(anna))
    assert f'href="/rooms/{room}/delete"' not in my_rooms_part(home(ben))


def test_creator_room_page_has_a_delete_link_and_a_guest_room_page_does_not(anna, ben, room):
    assert f'href="/rooms/{room}/delete"' in anna.get(f"/rooms/{room}").data.decode()
    assert f'href="/rooms/{room}/delete"' not in ben.get(f"/rooms/{room}").data.decode()


def test_confirmation_page_shows_title_warning_and_both_buttons(anna, room):
    response = anna.get(f"/rooms/{room}/delete")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Dinner" in html
    assert DELETE_WARNING in html
    assert f'action="/rooms/{room}/delete"' in html
    assert "Cancel" in html


def test_opening_the_confirmation_page_deletes_nothing(app, anna, room):
    anna.get(f"/rooms/{room}/delete")
    anna.get(f"/rooms/{room}/delete")
    assert room_exists(app, room)


@pytest.mark.parametrize("status", STATUSES)
def test_creator_deletes_the_room_with_everything_in_it(app, anna, room, status):
    set_status(app, room, status)
    assert all(count(app, table, room) > 0 for table in ["participants", "options", "votes", "vetoes", "option_authors"])

    response = anna.post(f"/rooms/{room}/delete")

    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/")
    assert not room_exists(app, room)
    assert all(count(app, table, room) == 0 for table in ROOM_TABLES)


def test_delete_redirects_home_with_a_notice(anna, room):
    response = anna.post(f"/rooms/{room}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert 'Room "Dinner" was deleted.' in response.data.decode()


def test_deleted_room_is_gone_for_the_creator_and_the_old_link_is_404(anna, room):
    anna.post(f"/rooms/{room}/delete")
    assert "Dinner" not in my_rooms_part(home(anna))
    assert anna.get(f"/rooms/{room}").status_code == 404


def test_other_participants_lose_the_room_and_their_stale_token_is_cleaned(anna, ben, room):
    anna.post(f"/rooms/{room}/delete")
    assert "Dinner" not in my_rooms_part(home(ben))
    assert room not in remembered(ben)
    assert ben.get(f"/rooms/{room}").status_code == 404


def test_other_rooms_are_not_touched(app, anna, room):
    other = create_room(anna, "Brunch", "Anna")
    anna.post(f"/rooms/{room}/delete")
    assert room_exists(app, other)
    assert "Brunch" in my_rooms_part(home(anna))


def test_a_guest_cannot_delete_and_nothing_changes(app, ben, room):
    before = {table: count(app, table, room) for table in ROOM_TABLES}
    response = ben.post(f"/rooms/{room}/delete")
    assert response.status_code == 403
    assert ONLY_CREATOR_MESSAGE in response.data.decode()
    assert room_exists(app, room)
    assert {table: count(app, table, room) for table in ROOM_TABLES} == before


def test_a_guest_cannot_open_the_confirmation_page(ben, room):
    response = ben.get(f"/rooms/{room}/delete")
    assert response.status_code == 403
    assert ONLY_CREATOR_MESSAGE in response.data.decode()


def test_a_browser_without_a_token_cannot_delete_or_confirm(app, room):
    stranger = app.test_client()
    assert stranger.get(f"/rooms/{room}/delete").status_code == 403
    assert stranger.post(f"/rooms/{room}/delete").status_code == 403
    assert room_exists(app, room)


def test_a_removed_creator_can_no_longer_delete(app, anna, room):
    anna.post(f"/rooms/{room}/forget")
    assert anna.post(f"/rooms/{room}/delete").status_code == 403
    assert room_exists(app, room)


def test_deleting_twice_is_harmless(app, anna, room):
    assert anna.post(f"/rooms/{room}/delete").status_code in (302, 303)
    response = anna.post(f"/rooms/{room}/delete")
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith("/")
    assert not room_exists(app, room)


def test_confirmation_page_of_a_deleted_room_is_404(anna, room):
    anna.post(f"/rooms/{room}/delete")
    assert anna.get(f"/rooms/{room}/delete").status_code == 404


def test_a_vote_after_the_delete_is_rejected_and_leaves_no_rows(app, anna, room):
    set_status(app, room, "voting")
    option_id = fill_room_option_id(app, room)
    anna.post(f"/rooms/{room}/delete")
    response = anna.post(f"/rooms/{room}/vote", data={"option_id": str(option_id), "rating": "yes"})
    assert response.status_code == 404
    assert rows(app, "SELECT COUNT(*) FROM votes")[0][0] == 0
    assert rows(app, "SELECT COUNT(*) FROM participants")[0][0] == 0


def fill_room_option_id(app, room_id):
    return rows(app, "SELECT id FROM options WHERE room_id = ?", (room_id,))[0][0]


# --- F32 and groups ------------------------------------------------------------

def test_deleting_a_group_room_keeps_the_group_and_its_members(app, anna):
    group_id = anna.post("/groups", data={"name": "Friday friends", "nickname": "Anna"}).headers[
        "Location"
    ].rsplit("/groups/", 1)[1]
    response = anna.post(f"/groups/{group_id}/rooms", data={"title": "Dinner", "mode": "manual"})
    room_id = response.headers["Location"].rsplit("/rooms/", 1)[1]
    members_before = rows(app, "SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,))[0][0]
    assert rows(app, "SELECT COUNT(*) FROM group_rooms WHERE room_id = ?", (room_id,))[0][0] == 1

    anna.post(f"/rooms/{room_id}/join", data={"as_group_member": "1"})  # no-op if already in
    assert anna.post(f"/rooms/{room_id}/delete").status_code in (302, 303)

    assert not room_exists(app, room_id)
    assert rows(app, "SELECT COUNT(*) FROM group_rooms WHERE room_id = ?", (room_id,))[0][0] == 0
    assert rows(app, "SELECT COUNT(*) FROM groups WHERE id = ?", (group_id,))[0][0] == 1
    assert rows(app, "SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,))[0][0] == members_before
    assert anna.get(f"/groups/{group_id}").status_code == 200
