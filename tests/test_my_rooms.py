"""Tests for A8 – F25 My rooms on the home page (specs/a8-my-rooms.md)."""

import re
from datetime import timedelta

import pytest

from app import create_app
from app.db import get_db
from app.services import rooms as room_rules

NO_ROOMS_TEXT = "You are not in any room yet. Create one below or open an invite link."
CREATE_FORM_ACTION = 'action="/rooms"'
CREATE_HEADING = "Create a room"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title, nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def home(client):
    response = client.get("/")
    assert response.status_code == 200
    return response.data.decode()


def remembered(client):
    with client.session_transaction() as session:
        return dict(session.get("participant_tokens", {}))


def set_created_at(app, room_id, created_at):
    """Rooms made in the same second have the same created_at; tests set it to fix the order."""
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET created_at = ? WHERE id = ?", (created_at, room_id))
        connection.commit()


def set_status(app, room_id, status):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def my_rooms_part(html):
    """The page above the create form, where the "My rooms" list is."""
    return html.split(CREATE_HEADING, 1)[0]


def entries(html, titles):
    """Cut the list into one piece of HTML per room title, in the order the titles appear."""
    part = my_rooms_part(html)
    positions = sorted((part.index(title), title) for title in titles)
    pieces = {}
    for number, (start, title) in enumerate(positions):
        end = positions[number + 1][0] if number + 1 < len(positions) else len(part)
        pieces[title] = part[start:end]
    return pieces


def links_to(html, title):
    """The href of every link whose text is the room title."""
    return re.findall(r'<a href="([^"]*)"[^>]*>\s*' + re.escape(title) + r"\s*</a>", my_rooms_part(html))


@pytest.fixture
def anna(client):
    return client


@pytest.fixture
def ben(app):
    return app.test_client()


# --- Pure functions ----------------------------------------------------------

def test_remember_room_token_adds_a_room_without_changing_the_input():
    tokens = {"room-a": "token-a"}
    result = room_rules.remember_room_token(tokens, "room-b", "token-b")
    assert result == {"room-a": "token-a", "room-b": "token-b"}
    assert tokens == {"room-a": "token-a"}


def test_remember_room_token_replaces_the_token_of_a_known_room():
    tokens = {"room-a": "token-a", "room-b": "token-b"}
    result = room_rules.remember_room_token(tokens, "room-a", "token-new")
    assert result == {"room-a": "token-new", "room-b": "token-b"}
    assert tokens == {"room-a": "token-a", "room-b": "token-b"}


def test_rooms_to_keep_keeps_the_30_most_recently_joined():
    assert room_rules.MAX_REMEMBERED_ROOMS == 30
    # participant_id grows with every join, so a higher id was remembered later.
    rooms = [{"id": f"room-{number}", "participant_id": 100 + number} for number in range(35)]
    rooms.reverse()
    kept = room_rules.rooms_to_keep(rooms)
    assert kept == {f"room-{number}" for number in range(5, 35)}
    assert len(rooms) == 35


def test_rooms_to_keep_with_30_or_fewer_keeps_all():
    rooms = [{"id": f"room-{number}", "participant_id": number} for number in range(30)]
    assert room_rules.rooms_to_keep(rooms) == {f"room-{number}" for number in range(30)}
    assert room_rules.rooms_to_keep([]) == set()


def test_room_link_endpoint_for_each_status():
    assert room_rules.room_link_endpoint("collecting") == "rooms.show_room"
    assert room_rules.room_link_endpoint("voting") == "rooms.show_vote"
    assert room_rules.room_link_endpoint("closed") == "rooms.show_result"
    assert room_rules.room_link_endpoint("something-else") == "rooms.show_room"
    assert room_rules.STATUS_LABELS == {
        "collecting": "Collecting ideas",
        "voting": "Voting",
        "closed": "Decided",
    }


# --- Home page ---------------------------------------------------------------

def test_new_browser_sees_no_rooms_text_and_create_form(client):
    html = home(client)
    assert "My rooms" in html
    assert NO_ROOMS_TEXT in html
    assert CREATE_FORM_ACTION in html


def test_home_lists_own_rooms_newest_first(app, anna, ben):
    friday = create_room(anna, "Friday dinner", nickname="Anna")
    sunday = create_room(anna, "Sunday cinema", nickname="Anna")
    hiking = create_room(ben, "Hiking trip", nickname="Ben")
    join(anna, hiking, "Annie")
    set_created_at(app, friday, "2026-11-01 10:00:00")
    set_created_at(app, sunday, "2026-11-02 10:00:00")
    set_created_at(app, hiking, "2026-11-03 10:00:00")

    html = home(anna)
    assert NO_ROOMS_TEXT not in html
    titles = ["Friday dinner", "Sunday cinema", "Hiking trip"]
    pieces = entries(html, titles)
    part = my_rooms_part(html)
    assert part.index("Hiking trip") < part.index("Sunday cinema") < part.index("Friday dinner")

    for title in titles:
        assert "Collecting ideas" in pieces[title]
    assert "You are Anna" in pieces["Friday dinner"]
    assert "You are Anna" in pieces["Sunday cinema"]
    assert "You are Annie" in pieces["Hiking trip"]
    assert "Creator" in pieces["Friday dinner"]
    assert "Creator" in pieces["Sunday cinema"]
    assert "Creator" not in pieces["Hiking trip"]
    assert CREATE_FORM_ACTION in html


def test_links_follow_the_room_status(app, anna):
    collecting = create_room(anna, "Room collecting")
    voting = create_room(anna, "Room voting")
    closed = create_room(anna, "Room closed")
    set_status(app, voting, "voting")
    set_status(app, closed, "closed")

    html = home(anna)
    assert links_to(html, "Room collecting") == [f"/rooms/{collecting}"]
    assert links_to(html, "Room voting") == [f"/rooms/{voting}/vote"]
    assert links_to(html, "Room closed") == [f"/rooms/{closed}/result"]
    pieces = entries(html, ["Room collecting", "Room voting", "Room closed"])
    assert "Voting" in pieces["Room voting"]
    assert "Decided" in pieces["Room closed"]


def test_other_browser_sees_none_of_these_rooms(app, anna):
    room_id = create_room(anna, "Secret party")
    stranger = app.test_client()
    html = home(stranger)
    assert "Secret party" not in html
    assert room_id not in html
    assert NO_ROOMS_TEXT in html


def test_visitor_who_only_opened_the_link_does_not_see_the_room(app, anna, ben):
    room_id = create_room(anna, "Secret party")
    assert ben.get(f"/rooms/{room_id}").status_code == 200
    html = home(ben)
    assert "Secret party" not in html
    assert NO_ROOMS_TEXT in html
    assert remembered(ben) == {}


def test_deleted_room_is_not_listed_and_its_token_is_removed(app, anna):
    kept = create_room(anna, "Kept room")
    gone = create_room(anna, "Gone room")
    with app.app_context():
        connection = get_db()
        connection.execute("DELETE FROM rooms WHERE id = ?", (gone,))
        connection.commit()

    html = home(anna)
    assert "Kept room" in html
    assert "Gone room" not in html
    tokens = remembered(anna)
    assert gone not in tokens
    assert kept in tokens


def test_token_of_no_participant_is_not_listed_and_is_removed(app, anna, ben):
    own = create_room(anna, "Own room")
    foreign = create_room(ben, "Foreign room", nickname="Ben")
    other = create_room(ben, "Other room", nickname="Ben")
    bens_token_for_other = remembered(ben)[other]
    own_token = remembered(anna)[own]
    with anna.session_transaction() as session:
        tokens = dict(session["participant_tokens"])
        tokens[other] = "forged-token"
        # A real token, but of a participant in another room.
        tokens[foreign] = bens_token_for_other
        tokens["no-such-room"] = "another-forged-token"
        session["participant_tokens"] = tokens

    html = home(anna)
    assert "Own room" in html
    assert "Foreign room" not in html
    assert "Other room" not in html
    assert remembered(anna) == {own: own_token}


def test_joining_a_31st_room_drops_the_oldest_remembered(app, anna, ben):
    # Ben's room is older than all of Anna's, but Anna joins it last, so it must stay.
    extra = create_room(ben, "Room extra", nickname="Ben")
    own_rooms = [create_room(anna, f"Room {number:02d}") for number in range(30)]
    assert len(remembered(anna)) == 30
    join(anna, extra, "Anna")

    tokens = remembered(anna)
    assert len(tokens) == 30
    assert own_rooms[0] not in tokens
    assert extra in tokens
    html = home(anna)
    assert "Room 00" not in html
    assert "Room 01" in html
    assert "Room extra" in html


def test_session_is_permanent_with_180_days(app, anna, ben):
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=180)
    room_id = create_room(anna, "Dinner")
    with anna.session_transaction() as session:
        assert session.permanent
    join(ben, room_id, "Ben")
    with ben.session_transaction() as session:
        assert session.permanent
    cookie = ben.get_cookie("session")
    assert cookie.expires is not None


@pytest.mark.parametrize("path_of", [
    lambda room_id: "/",
    lambda room_id: f"/rooms/{room_id}",
    lambda room_id: f"/rooms/{room_id}/lobby",
])
def test_every_page_has_my_rooms_link(app, anna, path_of):
    room_id = create_room(anna, "Dinner")
    html = anna.get(path_of(room_id)).data.decode()
    assert '<a href="/">My rooms</a>' in html


def test_create_form_with_errors_still_shows_the_list(anna):
    create_room(anna, "Friday dinner")
    response = anna.post("/rooms", data={"title": "", "mode": "manual", "nickname": "Anna"})
    assert response.status_code == 400
    html = response.data.decode()
    assert "Please enter a title." in html
    assert "Friday dinner" in my_rooms_part(html)
    assert NO_ROOMS_TEXT not in html


def test_list_shows_no_other_participants_and_no_votes(app, anna, ben):
    room_id = create_room(anna, "Dinner", nickname="Anna")
    join(ben, room_id, "Bernadette")
    anna.post(f"/rooms/{room_id}/options", data={"label": "Thai Garden"})
    anna.post(f"/rooms/{room_id}/options", data={"label": "Burger Bar"})
    set_status(app, room_id, "voting")

    part = my_rooms_part(home(anna))
    assert "Dinner" in part
    assert "Bernadette" not in part
    assert "Thai Garden" not in part
    assert "vote" not in part.replace(f"/rooms/{room_id}/vote", "").lower()


def test_rooms_are_still_listed_after_restart(app, anna):
    create_room(anna, "Friday dinner")
    session_cookie = anna.get_cookie("session")

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
    assert "Friday dinner" in home(restarted_browser)
