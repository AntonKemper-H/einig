"""Tests for A3 – F2 Join without an account (specs/a3-join-room.md)."""

import pytest

from app import create_app
from app.db import get_db

TAKEN_MESSAGE = "This nickname is already taken in this room. Please choose another one."
CLOSED_MESSAGE = "This room is closed. You can no longer join."
COLLISION_MESSAGE = "Something went wrong while joining. Please try again."


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner on Friday", nickname="Anna"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    """Post the join form. A nickname of None leaves the field out completely."""
    form = {} if nickname is None else {"nickname": nickname}
    return client.post(f"/rooms/{room_id}/join", data=form)


def assert_redirects_to_room(response, room_id):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


def participants(app, room_id):
    """Return all saved participants of a room, oldest first."""
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM participants WHERE room_id = ? ORDER BY id", (room_id,)
        ).fetchall()


def participant_count(app):
    """Return how many participants are saved in all rooms."""
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) FROM participants").fetchone()[0]


def set_room_status(app, room_id, status):
    """Change a room's status directly in the database (start/close come in later tasks)."""
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def session_tokens(client):
    """Return the participant tokens stored in the client's signed session."""
    with client.session_transaction() as session:
        return dict(session.get("participant_tokens", {}))


def join_form_action(room_id):
    return f'action="/rooms/{room_id}/join"'


@pytest.fixture
def room_id(client):
    """A room created by "Anna" in the creator's browser (the `client` fixture)."""
    return create_room(client)


@pytest.fixture
def guest(app):
    """A second browser that has not joined anything yet."""
    return app.test_client()


# --- Room page before and after joining -------------------------------------

def test_room_page_shows_join_form_when_not_joined(guest, room_id):
    response = guest.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Dinner on Friday" in html
    assert join_form_action(room_id) in html
    assert 'name="nickname"' in html


def test_creator_sees_joined_message_and_no_join_form(client, room_id):
    html = client.get(f"/rooms/{room_id}").data.decode()
    assert "You joined as Anna." in html
    assert join_form_action(room_id) not in html


def test_unknown_session_token_counts_as_not_joined(guest, room_id):
    with guest.session_transaction() as session:
        session["participant_tokens"] = {room_id: "token-that-is-not-in-the-database"}
    html = guest.get(f"/rooms/{room_id}").data.decode()
    assert join_form_action(room_id) in html
    assert "You joined as" not in html


# --- Accepted --------------------------------------------------------------

def test_valid_nickname_redirects_to_room_page(guest, room_id):
    assert_redirects_to_room(join(guest, room_id, "Ben"), room_id)


def test_participant_is_stored(app, guest, room_id):
    join(guest, room_id, "  Ben \t")
    stored = participants(app, room_id)
    assert len(stored) == 2
    ben = stored[1]
    assert ben["nickname"] == "Ben"
    assert ben["is_creator"] == 0
    assert ben["has_finished"] == 0
    assert ben["session_token"]
    assert ben["session_token"] != stored[0]["session_token"]


def test_session_holds_token_of_joined_participant(app, guest, room_id):
    join(guest, room_id, "Ben")
    ben = participants(app, room_id)[1]
    assert session_tokens(guest) == {room_id: ben["session_token"]}


def test_joined_participant_is_recognised_on_every_reload(guest, room_id):
    join(guest, room_id, "Ben")
    for _ in range(2):
        html = guest.get(f"/rooms/{room_id}").data.decode()
        assert "You joined as Ben." in html
        assert join_form_action(room_id) not in html


def test_joining_second_room_keeps_first_token(client, guest, room_id):
    second_room_id = create_room(client, title="Cinema", nickname="Carla")
    join(guest, room_id, "Ben")
    first_token = session_tokens(guest)[room_id]
    join(guest, second_room_id, "Ben")
    tokens = session_tokens(guest)
    assert tokens[room_id] == first_token
    assert second_room_id in tokens
    assert tokens[second_room_id] != first_token


def test_several_browsers_join_the_same_room(app, room_id):
    nicknames = ["Ben", "Carla", "Deniz", "Emil"]
    for nickname in nicknames:
        browser = app.test_client()
        assert_redirects_to_room(join(browser, room_id, nickname), room_id)
    stored = participants(app, room_id)
    assert [row["nickname"] for row in stored] == ["Anna", *nicknames]
    assert len({row["session_token"] for row in stored}) == 5


def test_same_nickname_in_another_room_is_accepted(app, client, guest, room_id):
    other_room_id = create_room(client, title="Cinema", nickname="Carla")
    assert_redirects_to_room(join(guest, other_room_id, "Anna"), other_room_id)
    assert [row["nickname"] for row in participants(app, other_room_id)] == ["Carla", "Anna"]


def test_joining_while_voting_is_accepted(app, guest, room_id):
    set_room_status(app, room_id, "voting")
    assert_redirects_to_room(join(guest, room_id, "Ben"), room_id)
    assert len(participants(app, room_id)) == 2


def test_nickname_at_maximum_length_is_accepted(app, guest, room_id):
    nickname = "n" * 30
    assert_redirects_to_room(join(guest, room_id, f"  {nickname} "), room_id)
    assert participants(app, room_id)[1]["nickname"] == nickname


# --- Rejected --------------------------------------------------------------

REJECTED_NICKNAMES = [
    pytest.param("", "Please enter a nickname.", id="empty"),
    pytest.param(None, "Please enter a nickname.", id="missing"),
    pytest.param(" \t\r\n ", "Please enter a nickname.", id="whitespace"),
    pytest.param("n" * 31, "The nickname can be at most 30 characters.", id="too-long"),
    pytest.param("Anna", TAKEN_MESSAGE, id="taken-exact"),
    pytest.param("anna", TAKEN_MESSAGE, id="taken-lowercase"),
    pytest.param("ANNA", TAKEN_MESSAGE, id="taken-uppercase"),
    pytest.param("  Anna\t", TAKEN_MESSAGE, id="taken-with-whitespace"),
]


@pytest.mark.parametrize("nickname, message", REJECTED_NICKNAMES)
def test_rejected_nickname_shows_message_and_saves_nothing(app, guest, room_id, nickname, message):
    before = participant_count(app)
    response = join(guest, room_id, nickname)
    assert response.status_code == 400
    assert message in response.data.decode()
    assert participant_count(app) == before
    assert session_tokens(guest) == {}


def test_rejected_form_keeps_entered_nickname(guest, room_id):
    response = join(guest, room_id, "anna")
    html = response.data.decode()
    assert response.status_code == 400
    assert join_form_action(room_id) in html
    assert 'value="anna"' in html


def test_joining_closed_room_is_rejected(app, guest, room_id):
    set_room_status(app, room_id, "closed")
    before = participant_count(app)
    response = join(guest, room_id, "Ben")
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.data.decode()
    assert participant_count(app) == before
    assert session_tokens(guest) == {}


def test_joining_unknown_room_shows_404(app, guest, room_id):
    before = participant_count(app)
    response = join(guest, "does-not-exist", "Ben")
    assert response.status_code == 404
    assert participant_count(app) == before


def test_joining_twice_creates_no_second_participant(app, guest, room_id):
    join(guest, room_id, "Ben")
    token = session_tokens(guest)[room_id]
    response = join(guest, room_id, "Benjamin")
    assert_redirects_to_room(response, room_id)
    assert [row["nickname"] for row in participants(app, room_id)] == ["Anna", "Ben"]
    assert session_tokens(guest)[room_id] == token


def test_creator_joining_own_room_creates_no_second_participant(app, client, room_id):
    assert_redirects_to_room(join(client, room_id, "Someone else"), room_id)
    assert len(participants(app, room_id)) == 1


def test_token_collision_shows_message_and_saves_nothing(app, client, guest, room_id, monkeypatch):
    creator_token = session_tokens(client)[room_id]
    monkeypatch.setattr("secrets.token_urlsafe", lambda nbytes=None: creator_token)
    before = participant_count(app)

    response = join(guest, room_id, "Ben")

    assert COLLISION_MESSAGE in response.data.decode()
    assert participant_count(app) == before
    assert session_tokens(guest) == {}


# --- Persistence -----------------------------------------------------------

def test_joined_participant_survives_restart(app, guest, room_id):
    join(guest, room_id, "Ben")
    session_cookie = guest.get_cookie("session")
    assert session_cookie is not None

    # A restart: a brand-new app object on the same database file and secret key.
    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
        }
    )
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)

    html = restarted_browser.get(f"/rooms/{room_id}").data.decode()
    assert "You joined as Ben." in html
    assert [row["nickname"] for row in participants(restarted_app, room_id)] == ["Anna", "Ben"]
