"""Tests for A5 – F7 Lobby with room status (specs/a5-lobby.md)."""

import pytest

from app import create_app
from app.db import get_db

ONLY_CREATOR_MESSAGE = "Only the creator can start the voting."
ALREADY_STARTED_MESSAGE = "Voting has already started."
CLOSED_MESSAGE = "This room is closed."
TOO_FEW_OPTIONS_MESSAGE = "Add at least 2 options before starting the voting."
WAITING_MESSAGE = "Waiting for the creator to start the voting."
CLOSED_JOIN_MESSAGE = "This room is closed. You can no longer join."
STATUS_TEXTS = {
    "collecting": "Collecting options.",
    "voting": "Voting has started.",
    "closed": "This room is closed.",
}


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


def add_options(client, room_id, labels):
    """Add manual options through the app (A4)."""
    for label in labels:
        response = client.post(f"/rooms/{room_id}/options", data={"label": label})
        assert response.status_code in (302, 303)


def lobby(client, room_id):
    return client.get(f"/rooms/{room_id}/lobby")


def lobby_html(client, room_id):
    response = lobby(client, room_id)
    assert response.status_code == 200
    return response.data.decode()


def start(client, room_id):
    return client.post(f"/rooms/{room_id}/start")


def assert_redirects_to(response, path):
    assert response.status_code in (302, 303)
    assert response.headers["Location"].endswith(path)


def room_status(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()["status"]


def set_room_status(app, room_id, status):
    """Change a room's status directly in the database (closing comes in B3)."""
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def set_finished(app, room_id, nickname):
    """Mark a participant as done directly in the database (B2 sets this when rating)."""
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE participants SET has_finished = 1 WHERE room_id = ? AND nickname = ?",
            (room_id, nickname),
        )
        db.commit()


def refresh_tag(room_id):
    return f'<meta http-equiv="refresh" content="4; url=/rooms/{room_id}/lobby">'


def start_form_action(room_id):
    return f'action="/rooms/{room_id}/start"'


def join_form_action(room_id):
    return f'action="/rooms/{room_id}/join"'


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


@pytest.fixture
def visitor(app):
    """A browser that has not joined any room."""
    return app.test_client()


@pytest.fixture
def ready_room_id(client, room_id):
    """Anna's room with two options, so the voting can be started."""
    add_options(client, room_id, ["Pizza place", "Cinema"])
    return room_id


# --- Lobby page ------------------------------------------------------------

def test_participant_sees_lobby_with_title_and_link_back(client, guest, room_id):
    for browser in (client, guest):
        html = lobby_html(browser, room_id)
        assert "Lobby" in html
        assert "Dinner on Friday" in html
        assert f'href="/rooms/{room_id}"' in html


def test_lobby_lists_participants_in_join_order_with_creator_marked(app, client, guest, room_id):
    join(app.test_client(), room_id, "Carla")
    html = lobby_html(guest, room_id)
    positions = [html.index(name) for name in ["Anna", "Ben", "Carla"]]
    assert positions == sorted(positions)
    assert "(creator)" in html
    # The creator mark belongs to Anna, not to Ben or Carla.
    assert html.index("Anna") < html.index("(creator)") < html.index("Ben")
    assert html.count("(creator)") == 1


def test_lobby_marks_finished_participants_and_counts_them(app, client, guest, room_id):
    join(app.test_client(), room_id, "Carla")
    html = lobby_html(client, room_id)
    assert "0 of 3 done" in html
    assert "done" not in html.replace("0 of 3 done", "")

    set_finished(app, room_id, "Ben")
    html = lobby_html(client, room_id)
    assert "1 of 3 done" in html
    rest = html.replace("1 of 3 done", "")
    assert rest.count("done") == 1
    # The one "done" mark is next to Ben, after his name and before Carla's.
    assert rest.index("Ben") < rest.index("done") < rest.index("Carla")


def test_lobby_shows_number_of_options(client, room_id):
    assert "0 options" in lobby_html(client, room_id)
    add_options(client, room_id, ["Pizza place", "Cinema", "Bowling"])
    assert "3 options" in lobby_html(client, room_id)


@pytest.mark.parametrize("status", ["collecting", "voting", "closed"])
def test_lobby_shows_status_text(app, client, room_id, status):
    set_room_status(app, room_id, status)
    assert STATUS_TEXTS[status] in lobby_html(client, room_id)


@pytest.mark.parametrize("status", ["collecting", "voting"])
def test_lobby_refreshes_while_room_is_open(app, client, room_id, status):
    set_room_status(app, room_id, status)
    assert refresh_tag(room_id) in lobby_html(client, room_id)


def test_lobby_does_not_refresh_when_closed(app, client, room_id):
    set_room_status(app, room_id, "closed")
    assert 'http-equiv="refresh"' not in lobby_html(client, room_id)


def test_creator_sees_start_form_while_collecting(client, room_id):
    html = lobby_html(client, room_id)
    assert start_form_action(room_id) in html
    assert "Start voting" in html
    assert WAITING_MESSAGE not in html


def test_other_participant_sees_waiting_text_and_no_start_form(guest, room_id):
    html = lobby_html(guest, room_id)
    assert start_form_action(room_id) not in html
    assert WAITING_MESSAGE in html


def test_lobby_links_to_rating_page_while_voting(app, client, guest, room_id):
    set_room_status(app, room_id, "voting")
    for browser in (client, guest):
        html = lobby_html(browser, room_id)
        assert f'href="/rooms/{room_id}/vote"' in html
        assert start_form_action(room_id) not in html


def test_lobby_shows_nickname_escaped(app, client, room_id):
    join(app.test_client(), room_id, "<b>Ben</b>")
    html = lobby_html(client, room_id)
    assert "<b>Ben</b>" not in html
    assert "&lt;b&gt;Ben&lt;/b&gt;" in html


def test_visitor_is_redirected_to_room_page(visitor, room_id):
    assert_redirects_to(lobby(visitor, room_id), f"/rooms/{room_id}")


def test_participant_of_another_room_is_redirected_to_room_page(app, room_id):
    other_browser = app.test_client()
    other_room_id = create_room(other_browser, title="Saturday", nickname="Carla")
    # Carla's token for her own room, presented for Anna's room.
    with other_browser.session_transaction() as session:
        carla_token = session["participant_tokens"][other_room_id]
        session["participant_tokens"] = {room_id: carla_token}

    assert_redirects_to(lobby(other_browser, room_id), f"/rooms/{room_id}")


def test_lobby_of_unknown_room_shows_404(client):
    assert lobby(client, "does-not-exist").status_code == 404


# --- Room page -------------------------------------------------------------

def test_room_page_links_to_lobby_and_does_not_refresh(client, guest, room_id):
    for browser in (client, guest):
        html = browser.get(f"/rooms/{room_id}").data.decode()
        assert f'href="/rooms/{room_id}/lobby"' in html
        assert 'http-equiv="refresh"' not in html


def test_visitor_of_closed_room_sees_closed_text_and_no_join_form(app, visitor, room_id):
    set_room_status(app, room_id, "closed")
    html = visitor.get(f"/rooms/{room_id}").data.decode()
    assert CLOSED_JOIN_MESSAGE in html
    assert join_form_action(room_id) not in html


@pytest.mark.parametrize("status", ["collecting", "voting"])
def test_visitor_of_open_room_still_sees_join_form(app, visitor, room_id, status):
    set_room_status(app, room_id, status)
    html = visitor.get(f"/rooms/{room_id}").data.decode()
    assert join_form_action(room_id) in html
    assert CLOSED_JOIN_MESSAGE not in html


# --- Start voting: accepted ------------------------------------------------

def test_creator_starts_voting(app, client, ready_room_id):
    response = start(client, ready_room_id)
    assert_redirects_to(response, f"/rooms/{ready_room_id}/lobby")
    assert room_status(app, ready_room_id) == "voting"
    assert STATUS_TEXTS["voting"] in lobby_html(client, ready_room_id)


def test_options_can_no_longer_be_added_after_start(app, client, ready_room_id):
    start(client, ready_room_id)
    response = client.post(f"/rooms/{ready_room_id}/options", data={"label": "Bowling"})
    assert response.status_code == 400
    with app.app_context():
        count = get_db().execute(
            "SELECT COUNT(*) FROM options WHERE room_id = ?", (ready_room_id,)
        ).fetchone()[0]
    assert count == 2


# --- Start voting: rejected ------------------------------------------------

@pytest.mark.parametrize("labels", [[], ["Pizza place"]], ids=["no-options", "one-option"])
def test_start_with_too_few_options_is_rejected(app, client, room_id, labels):
    add_options(client, room_id, labels)
    response = start(client, room_id)
    assert response.status_code == 400
    assert TOO_FEW_OPTIONS_MESSAGE in response.data.decode()
    assert room_status(app, room_id) == "collecting"


@pytest.mark.parametrize(
    "status, message",
    [("voting", ALREADY_STARTED_MESSAGE), ("closed", CLOSED_MESSAGE)],
)
def test_start_after_collecting_is_rejected(app, client, ready_room_id, status, message):
    set_room_status(app, ready_room_id, status)
    response = start(client, ready_room_id)
    assert response.status_code == 400
    assert message in response.data.decode()
    assert room_status(app, ready_room_id) == status


def test_participant_who_is_not_creator_cannot_start(app, guest, ready_room_id):
    response = start(guest, ready_room_id)
    assert response.status_code == 403
    assert ONLY_CREATOR_MESSAGE in response.data.decode()
    assert room_status(app, ready_room_id) == "collecting"


def test_visitor_without_token_cannot_start(app, visitor, ready_room_id):
    response = start(visitor, ready_room_id)
    assert response.status_code == 403
    assert ONLY_CREATOR_MESSAGE in response.data.decode()
    assert room_status(app, ready_room_id) == "collecting"


def test_visitor_with_unknown_token_cannot_start(app, visitor, ready_room_id):
    with visitor.session_transaction() as session:
        session["participant_tokens"] = {ready_room_id: "token-that-is-not-in-the-database"}
    response = start(visitor, ready_room_id)
    assert response.status_code == 403
    assert room_status(app, ready_room_id) == "collecting"


def test_start_in_unknown_room_shows_404(client):
    assert start(client, "does-not-exist").status_code == 404


def test_rejected_start_refreshes_to_lobby_not_to_start(client, room_id):
    html = start(client, room_id).data.decode()
    assert refresh_tag(room_id) in html
    assert f"url=/rooms/{room_id}/start" not in html


def test_second_start_at_same_moment_shows_message_and_does_not_crash(
    app, client, ready_room_id, monkeypatch
):
    start(client, ready_room_id)
    assert room_status(app, ready_room_id) == "voting"
    # Simulate a race: the route still sees the room as collecting, so only
    # db.start_voting's "AND status = 'collecting'" stops the second start.
    monkeypatch.setattr(
        "app.db.get_room",
        lambda room_id: {
            "id": room_id, "title": "Dinner on Friday", "mode": "manual", "status": "collecting"
        },
    )

    response = start(client, ready_room_id)

    assert response.status_code == 400
    assert ALREADY_STARTED_MESSAGE in response.data.decode()
    assert room_status(app, ready_room_id) == "voting"


# --- Persistence -----------------------------------------------------------

def test_lobby_survives_restart(app, client, guest, ready_room_id):
    start(client, ready_room_id)
    set_finished(app, ready_room_id, "Ben")
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
    restarted_browser = restarted_app.test_client()
    restarted_browser.set_cookie("session", session_cookie.value)

    html = lobby_html(restarted_browser, ready_room_id)
    assert "Anna" in html
    assert "Ben" in html
    assert "1 of 2 done" in html
    assert STATUS_TEXTS["voting"] in html
