"""Route tests for A9 – F16 Fixed groups (specs/a9-groups.md)."""

import re

import pytest

from app import create_app
from app import db as database
from app.db import get_db

NOT_MEMBER_PLAN_MESSAGE = "Please join the group before planning an activity."
NOT_IN_GROUP_MESSAGE = "You are not a member of this group."
GROUP_NICKNAME_TAKEN_IN_ROOM = (
    "Your group nickname is already taken in this room. Please choose another one."
)
NICKNAME_TAKEN_IN_GROUP = "This nickname is already taken in this group."
NAME_EMPTY = "Please enter a group name."
NICKNAME_EMPTY = "Please enter a nickname."
TITLE_EMPTY = "Please enter a title."
MODE_INVALID = "Please choose a valid mode."
ROOM_NICKNAME_FIELD = 'name="nickname"'


# --- Helpers ---------------------------------------------------------------

def create_group(client, name="Friday friends", nickname="Anna"):
    response = client.post("/groups", data={"name": name, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/groups/", 1)[1]


def join_group(client, group_id, nickname):
    return client.post(f"/groups/{group_id}/join", data={"nickname": nickname})


def plan(client, group_id, title="Dinner", mode="manual"):
    return client.post(f"/groups/{group_id}/rooms", data={"title": title, "mode": mode})


def plan_room(client, group_id, title="Dinner"):
    response = plan(client, group_id, title)
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join_as_member(client, room_id, nickname_in_form=None):
    data = {"as_group_member": "1"}
    if nickname_in_form is not None:
        data["nickname"] = nickname_in_form
    return client.post(f"/rooms/{room_id}/join", data=data)


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.data.decode()


def tokens(client, key):
    with client.session_transaction() as session:
        return dict(session.get(key, {}))


def rows(app, sql, params=()):
    with app.app_context():
        return [tuple(row) for row in get_db().execute(sql, params)]


def count(app, table):
    return rows(app, f"SELECT COUNT(*) FROM {table}")[0][0]


def snapshot(app):
    tables = ("groups", "group_members", "group_rooms", "group_participants", "rooms", "participants")
    return {table: rows(app, f"SELECT * FROM {table} ORDER BY 1") for table in tables}


def assert_redirects(response, path):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(path)


@pytest.fixture
def anna(client):
    return client


@pytest.fixture
def ben(app):
    return app.test_client()


@pytest.fixture
def zoe(app):
    """A guest: never a member of the group."""
    return app.test_client()


@pytest.fixture
def group_id(anna, ben):
    """A group with Anna (creator) and Ben."""
    new_id = create_group(anna, "Friday friends", "Anna")
    assert join_group(ben, new_id, "Ben").status_code in (302, 303)
    return new_id


# --- Creating and joining a group ------------------------------------------

def test_new_group_form(client):
    html = page(client, "/groups/new")
    assert 'action="/groups"' in html
    assert 'name="name"' in html
    assert 'name="nickname"' in html


def test_creating_a_group_stores_it_and_shows_the_group_page(app, anna):
    response = anna.post("/groups", data={"name": "  Friday friends ", "nickname": " Anna "})
    assert response.status_code in (302, 303)
    new_id = response.headers["Location"].rsplit("/groups/", 1)[1]

    assert rows(app, "SELECT id, name FROM groups") == [(new_id, "Friday friends")]
    assert rows(app, "SELECT group_id, nickname, is_creator FROM group_members") == [(new_id, "Anna", 1)]
    assert list(tokens(anna, "group_tokens")) == [new_id]

    html = page(anna, f"/groups/{new_id}")
    assert "Friday friends" in html
    assert "Anna" in html
    assert f"http://localhost/groups/{new_id}" in html
    assert "<svg" in html


def test_second_browser_sees_only_the_join_form_then_joins(app, anna, ben):
    new_id = create_group(anna, "Friday friends", "Anna")
    html = page(ben, f"/groups/{new_id}")
    assert "Friday friends" in html
    assert f'action="/groups/{new_id}/join"' in html
    assert "Anna" not in html

    assert_redirects(join_group(ben, new_id, " Ben "), f"/groups/{new_id}")
    html = page(ben, f"/groups/{new_id}")
    assert "Anna" in html
    assert "Ben" in html
    assert rows(app, "SELECT nickname, is_creator FROM group_members ORDER BY id") == [
        ("Anna", 1),
        ("Ben", 0),
    ]


# --- Planning an activity ----------------------------------------------------

def test_member_plans_an_activity(app, ben, group_id):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE groups SET last_activity_at = '2026-01-01 00:00:00'")
        connection.commit()

    room_id = plan_room(ben, group_id, "Sunday cinema")

    assert rows(app, "SELECT room_id, group_id FROM group_rooms") == [(room_id, group_id)]
    assert rows(app, "SELECT title FROM rooms") == [("Sunday cinema",)]
    participants = rows(app, "SELECT id, nickname, is_creator FROM participants WHERE room_id = ?", (room_id,))
    assert [(nickname, is_creator) for _, nickname, is_creator in participants] == [("Ben", 1)]
    ben_member = rows(app, "SELECT id FROM group_members WHERE nickname = 'Ben'")[0][0]
    assert rows(app, "SELECT participant_id, group_member_id FROM group_participants") == [
        (participants[0][0], ben_member)
    ]
    assert room_id in tokens(ben, "participant_tokens")
    assert rows(app, "SELECT last_activity_at FROM groups")[0][0] != "2026-01-01 00:00:00"

    html = page(ben, f"/groups/{group_id}")
    assert f'href="/rooms/{room_id}"' in html
    assert "Sunday cinema" in html
    assert "Collecting ideas" in html


def test_group_page_lists_rooms_newest_first(app, anna, group_id):
    first = plan_room(anna, group_id, "First activity")
    second = plan_room(anna, group_id, "Second activity")
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET created_at = '2026-11-01 10:00:00' WHERE id = ?", (first,))
        connection.execute("UPDATE rooms SET created_at = '2026-11-02 10:00:00' WHERE id = ?", (second,))
        connection.commit()
    html = page(anna, f"/groups/{group_id}")
    assert html.index("Second activity") < html.index("First activity")


def test_other_member_joins_with_one_tap(app, anna, ben, group_id):
    room_id = plan_room(ben, group_id)
    html = page(anna, f"/rooms/{room_id}")
    assert "Join as Anna" in html
    assert 'name="as_group_member"' in html

    # A nickname sent along in the form is ignored: the group nickname is used.
    assert_redirects(join_as_member(anna, room_id, nickname_in_form="Someone else"), f"/rooms/{room_id}")
    assert ("Someone else",) not in rows(app, "SELECT nickname FROM participants")
    participant = rows(
        app, "SELECT id, nickname, is_creator FROM participants WHERE room_id = ? AND nickname = 'Anna'", (room_id,)
    )
    assert [(nickname, is_creator) for _, nickname, is_creator in participant] == [("Anna", 0)]
    anna_member = rows(app, "SELECT id FROM group_members WHERE nickname = 'Anna'")[0][0]
    assert (participant[0][0], anna_member) in rows(app, "SELECT participant_id, group_member_id FROM group_participants")

    html = page(anna, f"/rooms/{room_id}")
    assert "You joined as Anna." in html
    assert "Part of Friday friends" in html
    assert f'href="/groups/{group_id}"' in html


def test_guest_joins_a_group_room_like_any_room(app, ben, zoe, group_id):
    room_id = plan_room(ben, group_id)
    html = page(zoe, f"/rooms/{room_id}")
    assert ROOM_NICKNAME_FIELD in html
    assert "Join as" not in html

    response = zoe.post(f"/rooms/{room_id}/join", data={"nickname": "Zoe"})
    assert_redirects(response, f"/rooms/{room_id}")
    assert ("Zoe",) in rows(app, "SELECT nickname FROM participants WHERE room_id = ?", (room_id,))
    assert ("Zoe",) not in rows(app, "SELECT nickname FROM group_members")
    assert count(app, "group_participants") == 1  # only Ben, the planner

    html = page(zoe, f"/rooms/{room_id}")
    assert "Part of Friday friends" not in html
    group_html = page(zoe, f"/groups/{group_id}")
    assert "Ben" not in group_html
    assert f'action="/groups/{group_id}/join"' in group_html


def test_home_page_lists_groups_above_rooms(app, anna, ben, group_id):
    plan_room(anna, group_id, "Sunday cinema")
    html = page(anna, "/")
    assert "My groups" in html
    assert "Friday friends" in html
    assert "2 members" in html
    assert f'href="/groups/{group_id}"' in html
    assert 'href="/groups/new"' in html
    assert "Create a group" in html
    assert html.index("Friday friends") < html.index("Sunday cinema")
    assert html.index("My groups") < re.search(r"<h2[^>]*>\s*My rooms", html).start()

    stranger = app.test_client()
    assert "Friday friends" not in page(stranger, "/")


def test_home_page_drops_tokens_of_deleted_groups(app, anna):
    kept = create_group(anna, "Kept group", "Anna")
    gone = create_group(anna, "Gone group", "Anna")
    with app.app_context():
        connection = get_db()
        connection.execute("DELETE FROM groups WHERE id = ?", (gone,))
        connection.commit()
    html = page(anna, "/")
    assert "Kept group" in html
    assert "Gone group" not in html
    assert list(tokens(anna, "group_tokens")) == [kept]


def test_joining_an_11th_group_drops_the_oldest_remembered(app, anna, ben):
    # Ben's group is older than all of Anna's, but Anna joins it last, so it must stay.
    bens = create_group(ben, "Bens group", "Ben")
    own = [create_group(anna, f"Group {number:02d}", "Anna") for number in range(10)]
    assert join_group(anna, bens, "Anna").status_code in (302, 303)
    remembered = tokens(anna, "group_tokens")
    assert len(remembered) == 10
    assert own[0] not in remembered
    assert bens in remembered


# --- Rejected ----------------------------------------------------------------

def test_invalid_group_is_rejected(app, anna):
    before = snapshot(app)
    response = anna.post("/groups", data={"name": "   ", "nickname": ""})
    assert response.status_code == 400
    html = response.data.decode()
    assert NAME_EMPTY in html
    assert NICKNAME_EMPTY in html
    assert snapshot(app) == before
    assert tokens(anna, "group_tokens") == {}


def test_joining_a_group_with_a_taken_nickname_is_rejected(app, zoe, group_id):
    before = snapshot(app)
    response = join_group(zoe, group_id, "anna")
    assert response.status_code == 400
    assert NICKNAME_TAKEN_IN_GROUP in response.data.decode()
    assert snapshot(app) == before


def test_non_member_cannot_plan_an_activity(app, zoe, group_id):
    before = snapshot(app)
    response = plan(zoe, group_id, "Party")
    assert response.status_code == 403
    assert NOT_MEMBER_PLAN_MESSAGE in response.data.decode()
    assert snapshot(app) == before


@pytest.mark.parametrize("title, mode, message", [
    ("", "manual", TITLE_EMPTY),
    ("Party", "teleport", MODE_INVALID),
])
def test_planning_with_invalid_values_is_rejected(app, anna, group_id, title, mode, message):
    before = snapshot(app)
    response = plan(anna, group_id, title, mode)
    assert response.status_code == 400
    assert message in response.data.decode()
    assert snapshot(app) == before


def test_join_as_member_from_a_non_member_is_rejected(app, ben, zoe, group_id):
    room_id = plan_room(ben, group_id)
    # Zoe is a member of another group, but not of this one.
    create_group(zoe, "Other group", "Zoe")
    before = snapshot(app)
    response = join_as_member(zoe, room_id, nickname_in_form="Anna")
    assert response.status_code == 403
    assert NOT_IN_GROUP_MESSAGE in response.data.decode()
    assert snapshot(app) == before
    assert room_id not in tokens(zoe, "participant_tokens")


def test_group_nickname_taken_in_the_room_by_a_guest(app, anna, ben, zoe, group_id):
    room_id = plan_room(ben, group_id)
    assert zoe.post(f"/rooms/{room_id}/join", data={"nickname": "Anna"}).status_code in (302, 303)
    before = snapshot(app)
    response = join_as_member(anna, room_id)
    assert response.status_code == 400
    html = response.data.decode()
    assert GROUP_NICKNAME_TAKEN_IN_ROOM in html
    assert ROOM_NICKNAME_FIELD in html
    assert snapshot(app) == before


# --- Edge cases --------------------------------------------------------------

def test_joining_the_same_group_twice_keeps_one_member(app, ben, group_id):
    assert_redirects(join_group(ben, group_id, "Benjamin"), f"/groups/{group_id}")
    assert rows(app, "SELECT nickname FROM group_members ORDER BY id") == [("Anna",), ("Ben",)]


def test_join_as_member_twice_keeps_one_participant(app, anna, ben, group_id):
    room_id = plan_room(ben, group_id)
    join_as_member(anna, room_id)
    before = snapshot(app)
    assert_redirects(join_as_member(anna, room_id), f"/rooms/{room_id}")
    assert snapshot(app) == before


def test_failed_group_participant_row_saves_no_participant(app, ben, group_id):
    room_id = plan_room(ben, group_id)
    before = snapshot(app)
    with app.app_context():
        # A group member id that does not exist: the database refuses the link row.
        saved = database.add_group_participant(room_id, "Ghost", "ghost-token", 999999)
    assert saved is False
    assert snapshot(app) == before


@pytest.mark.parametrize("method, path", [
    ("get", "/groups/no-such-group"),
    ("post", "/groups/no-such-group/join"),
    ("post", "/groups/no-such-group/rooms"),
])
def test_unknown_group_is_404(anna, method, path):
    create_group(anna)
    response = getattr(anna, method)(path, data={"nickname": "Anna", "title": "x", "mode": "manual"})
    assert response.status_code == 404


# --- Privacy and persistence -------------------------------------------------

def test_non_member_sees_no_members_rooms_or_votes(app, anna, ben, zoe, group_id):
    room_id = plan_room(anna, group_id, "Sunday cinema")
    anna.post(f"/rooms/{room_id}/options", data={"label": "Thai Garden"})
    anna.post(f"/rooms/{room_id}/options", data={"label": "Burger Bar"})

    html = page(zoe, f"/groups/{group_id}")
    for secret in ("Anna", "Ben", "Sunday cinema", room_id):
        assert secret not in html

    member_html = page(ben, f"/groups/{group_id}")
    assert "Sunday cinema" in member_html
    assert "Thai Garden" not in member_html
    assert "Burger Bar" not in member_html


def test_groups_survive_a_restart(app, anna, ben, group_id):
    plan_room(anna, group_id, "Sunday cinema")
    session_cookie = ben.get_cookie("session")

    restarted_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": app.config["SECRET_KEY"],
            "DATABASE": app.config["DATABASE"],
        }
    )
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)
    html = page(restarted_browser, f"/groups/{group_id}")
    assert "Anna" in html
    assert "Ben" in html
    assert "Sunday cinema" in html
