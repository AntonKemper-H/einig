"""Tests for A2 – F1 Create a room (specs/a2-create-room.md)."""

import itertools
import re

import pytest

from app import create_app
from app.db import get_db

VALID_FORM = {"title": "Dinner on Friday", "mode": "manual", "nickname": "Anna"}
COLLISION_MESSAGE = "Something went wrong while creating the room. Please try again."


# --- Helpers ---------------------------------------------------------------

def create_room(client, **changes):
    """Post the create-room form: the valid form with some fields changed.

    A field set to None is left out of the form completely.
    """
    form = {**VALID_FORM, **changes}
    form = {name: value for name, value in form.items() if value is not None}
    return client.post("/rooms", data=form)


def room_id_from(response):
    """Read the room id from the redirect target /rooms/<room_id>."""
    assert response.status_code in (302, 303)
    location = response.headers["Location"]
    assert "/rooms/" in location
    return location.rsplit("/rooms/", 1)[1]


def row_counts(app):
    """Return how many rooms and participants are saved, to compare before and after."""
    with app.app_context():
        db = get_db()
        return {
            "rooms": db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0],
            "participants": db.execute("SELECT COUNT(*) FROM participants").fetchone()[0],
        }


def fetch_room(app, room_id):
    """Return the saved room row, or None."""
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def fetch_participants(app, room_id):
    """Return all saved participants of a room."""
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM participants WHERE room_id = ?", (room_id,)
        ).fetchall()


def session_tokens(client):
    """Return the participant tokens stored in the client's signed session."""
    with client.session_transaction() as session:
        return dict(session.get("participant_tokens", {}))


# --- Form ------------------------------------------------------------------

def test_home_page_shows_create_room_form(client):
    html = client.get("/").data.decode()
    assert 'action="/rooms"' in html
    assert 'method="post"' in html.lower()
    for field in ("title", "mode", "nickname"):
        assert f'name="{field}"' in html
    for mode in ("manual", "nearby", "surprise"):
        assert f'value="{mode}"' in html


# --- Accepted --------------------------------------------------------------

def test_valid_form_redirects_to_room_page(client):
    response = create_room(client)
    room_id = room_id_from(response)
    assert response.headers["Location"].endswith(f"/rooms/{room_id}")


def test_room_is_stored_with_title_mode_and_status(app, client):
    room_id = room_id_from(create_room(client))
    room = fetch_room(app, room_id)
    assert room is not None
    assert room["title"] == "Dinner on Friday"
    assert room["mode"] == "manual"
    assert room["status"] == "collecting"


@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_each_mode_can_be_chosen(app, client, mode):
    room_id = room_id_from(create_room(client, mode=mode))
    assert fetch_room(app, room_id)["mode"] == mode


def test_creator_is_stored_as_first_participant(app, client):
    room_id = room_id_from(create_room(client))
    participants = fetch_participants(app, room_id)
    assert len(participants) == 1
    creator = participants[0]
    assert creator["nickname"] == "Anna"
    assert creator["is_creator"] == 1
    assert creator["has_finished"] == 0
    assert creator["session_token"]


def test_session_holds_creator_token_under_room_id(app, client):
    room_id = room_id_from(create_room(client))
    tokens = session_tokens(client)
    creator = fetch_participants(app, room_id)[0]
    assert tokens[room_id] == creator["session_token"]


def test_second_room_keeps_token_of_first_room(client):
    first_room_id = room_id_from(create_room(client, title="Dinner"))
    first_token = session_tokens(client)[first_room_id]
    second_room_id = room_id_from(create_room(client, title="Cinema"))
    tokens = session_tokens(client)
    assert tokens[first_room_id] == first_token
    assert second_room_id in tokens
    assert tokens[second_room_id] != first_token


def test_title_and_nickname_are_stored_stripped(app, client):
    room_id = room_id_from(create_room(client, title="  Dinner \t\n", nickname="\t Anna  "))
    assert fetch_room(app, room_id)["title"] == "Dinner"
    assert fetch_participants(app, room_id)[0]["nickname"] == "Anna"


def test_title_and_nickname_at_maximum_length_are_accepted(app, client):
    """Exactly 80 / 30 characters are fine; surrounding whitespace does not count."""
    title = "t" * 80
    nickname = "n" * 30
    room_id = room_id_from(create_room(client, title=f"  {title}  ", nickname=f" {nickname} "))
    assert fetch_room(app, room_id)["title"] == title
    assert fetch_participants(app, room_id)[0]["nickname"] == nickname


def test_room_ids_are_random_and_not_sequential(client):
    room_ids = [room_id_from(create_room(client)) for _ in range(20)]
    assert len(set(room_ids)) == 20
    for room_id in room_ids:
        assert re.fullmatch(r"[A-Za-z0-9_-]{10,}", room_id)
        assert not room_id.isdigit()


def test_room_page_shows_title_and_invite_url(client):
    room_id = room_id_from(create_room(client))
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    html = response.data.decode()
    assert "Dinner on Friday" in html
    assert f"http://localhost/rooms/{room_id}" in html


def test_unknown_room_shows_404(client):
    response = client.get("/rooms/does-not-exist")
    assert response.status_code == 404


# --- Rejected --------------------------------------------------------------

REJECTED_FORMS = [
    pytest.param({"title": ""}, "Please enter a title.", id="empty-title"),
    pytest.param({"title": None}, "Please enter a title.", id="missing-title"),
    pytest.param({"title": "   "}, "Please enter a title.", id="spaces-title"),
    pytest.param({"title": "\t"}, "Please enter a title.", id="tab-title"),
    pytest.param({"title": "\n"}, "Please enter a title.", id="newline-title"),
    pytest.param({"title": " \t\r\n "}, "Please enter a title.", id="mixed-whitespace-title"),
    pytest.param({"title": "t" * 81}, "The title can be at most 80 characters.", id="long-title"),
    pytest.param({"mode": "blind"}, "Please choose a valid mode.", id="unknown-mode"),
    pytest.param({"mode": ""}, "Please choose a valid mode.", id="empty-mode"),
    pytest.param({"mode": None}, "Please choose a valid mode.", id="missing-mode"),
    pytest.param({"mode": "MANUAL"}, "Please choose a valid mode.", id="uppercase-mode"),
    pytest.param({"nickname": ""}, "Please enter a nickname.", id="empty-nickname"),
    pytest.param({"nickname": None}, "Please enter a nickname.", id="missing-nickname"),
    pytest.param({"nickname": " \t\n"}, "Please enter a nickname.", id="whitespace-nickname"),
    pytest.param(
        {"nickname": "n" * 31}, "The nickname can be at most 30 characters.", id="long-nickname"
    ),
]


@pytest.mark.parametrize("changes, message", REJECTED_FORMS)
def test_rejected_form_shows_message_and_saves_nothing(app, client, changes, message):
    before = row_counts(app)
    response = create_room(client, **changes)
    assert response.status_code == 400
    assert message in response.data.decode()
    assert row_counts(app) == before
    assert session_tokens(client) == {}


def test_rejected_form_keeps_entered_title(client):
    response = create_room(client, title="Dinner on Friday", nickname="")
    assert response.status_code == 400
    assert "Dinner on Friday" in response.data.decode()


def test_rejected_form_with_several_problems_shows_every_message(app, client):
    response = create_room(client, title="", mode="blind", nickname="")
    html = response.data.decode()
    assert response.status_code == 400
    assert "Please enter a title." in html
    assert "Please choose a valid mode." in html
    assert "Please enter a nickname." in html
    assert row_counts(app) == {"rooms": 0, "participants": 0}


# --- Collisions (extremely unlikely, but must never crash or half-save) ----

def fake_token_urlsafe(room_ids, session_tokens):
    """Build a replacement for secrets.token_urlsafe.

    Room ids use 8 bytes and session tokens 32 (see the spec), so the fake
    can hand out a chosen sequence for each.
    """
    def token_urlsafe(nbytes=None):
        if nbytes == 8:
            return next(room_ids)
        return next(session_tokens)

    return token_urlsafe


def numbered(prefix):
    """Endless unique values: prefix-1, prefix-2, …"""
    return (f"{prefix}-{number}" for number in itertools.count(1))


def test_room_id_collision_shows_message_and_saves_nothing(app, client, monkeypatch):
    monkeypatch.setattr(
        "secrets.token_urlsafe",
        fake_token_urlsafe(itertools.repeat("same-room-id"), numbered("token")),
    )
    room_id_from(create_room(client, title="First"))
    before = row_counts(app)

    response = create_room(client, title="Second")

    assert COLLISION_MESSAGE in response.data.decode()
    assert row_counts(app) == before
    assert fetch_room(app, "same-room-id")["title"] == "First"


def test_session_token_collision_leaves_no_room_without_creator(app, client, monkeypatch):
    monkeypatch.setattr(
        "secrets.token_urlsafe",
        fake_token_urlsafe(numbered("room"), itertools.repeat("same-session-token")),
    )
    first_room_id = room_id_from(create_room(client, title="First"))
    before = row_counts(app)

    response = create_room(client, title="Second")

    assert COLLISION_MESSAGE in response.data.decode()
    assert row_counts(app) == before
    assert fetch_room(app, "room-2") is None
    assert list(session_tokens(client)) == [first_room_id]


# --- Persistence -----------------------------------------------------------

def test_room_and_creator_survive_restart(app, client):
    room_id = room_id_from(create_room(client))
    session_cookie = client.get_cookie("session")
    assert session_cookie is not None

    # A restart: a brand-new app object on the same database file and secret key.
    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
        }
    )
    restarted_client = restarted_app.test_client()
    restarted_client.set_cookie("session", session_cookie.value)

    response = restarted_client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    assert "Dinner on Friday" in response.data.decode()

    creator = fetch_participants(restarted_app, room_id)[0]
    assert session_tokens(restarted_client)[room_id] == creator["session_token"]
    assert creator["is_creator"] == 1
