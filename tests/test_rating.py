"""Tests for B2 – F4 Three-level rating (specs/b2-rating.md)."""

import ast
import re
from pathlib import Path

import pytest

from app import create_app, db
from app.db import get_db
from app.services.scoring import pick_winner
from app.services.voting import (
    RATING_LABELS,
    next_option_to_rate,
    rating_order,
    vote_errors,
)

NOT_STARTED_MESSAGE = "Voting has not started yet."
CLOSED_MESSAGE = "This room is closed. You can no longer vote."
INVALID_RATING_MESSAGE = "Please choose one of the three ratings."
UNKNOWN_OPTION_MESSAGE = "This option does not exist in this room."
ALL_RATED_MESSAGE = "You have rated all options."
LABELS = ["Pizza", "Sushi", "Tacos"]
VOTING_FILE = Path(__file__).resolve().parents[1] / "app" / "services" / "voting.py"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner on Friday", nickname="Anna"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    """Join a room (A3) with a second browser."""
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_option(app, room_id, label, is_replaced=0):
    """Insert a manual option directly (adding options is A4) and return its id."""
    with app.app_context():
        connection = get_db()
        cursor = connection.execute(
            "INSERT INTO options (room_id, source, label, is_replaced) VALUES (?, 'manual', ?, ?)",
            (room_id, label, is_replaced),
        )
        connection.commit()
        return cursor.lastrowid


def set_room_status(app, room_id, status):
    """Change a room's status directly (starting and closing come in other tasks)."""
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def token_of(client, room_id):
    """The participant token this browser stored for the room."""
    with client.session_transaction() as session:
        return session["participant_tokens"][room_id]


def participant_id_of(app, room_id, token):
    with app.app_context():
        return db.get_participant(room_id, token)["id"]


def vote_rows(app, room_id=None):
    """All saved votes (optionally of one room) as plain tuples."""
    with app.app_context():
        sql = "SELECT room_id, participant_id, option_id, rating FROM votes"
        params = ()
        if room_id is not None:
            sql += " WHERE room_id = ?"
            params = (room_id,)
        return [tuple(row) for row in get_db().execute(sql + " ORDER BY id", params).fetchall()]


def has_finished(app, participant_id):
    with app.app_context():
        return get_db().execute(
            "SELECT has_finished FROM participants WHERE id = ?", (participant_id,)
        ).fetchone()["has_finished"]


def vote(client, room_id, option_id, rating):
    """Post the rating form. A value of None leaves that field out."""
    form = {}
    if option_id is not None:
        form["option_id"] = str(option_id)
    if rating is not None:
        form["rating"] = rating
    return client.post(f"/rooms/{room_id}/vote", data=form)


def shown_option_ids(html):
    """The option ids in the hidden option_id fields of the page."""
    ids = set()
    for tag in re.findall(r"<input[^>]*>", html):
        if 'name="option_id"' in tag:
            ids.add(int(re.search(r'value="(\d+)"', tag).group(1)))
    return ids


def page(client, room_id):
    response = client.get(f"/rooms/{room_id}/vote")
    assert response.status_code == 200
    return response.get_data(as_text=True)


@pytest.fixture
def room(app, client):
    """A room in voting status with three options; the client is its creator."""
    room_id = create_room(client)
    option_ids = [add_option(app, room_id, label) for label in LABELS]
    set_room_status(app, room_id, "voting")
    return {"id": room_id, "options": option_ids, "token": token_of(client, room_id)}


# --- Accepted --------------------------------------------------------------

def test_rating_is_saved_and_redirects(app, client, room):
    response = vote(client, room["id"], room["options"][0], "yes")
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{room['id']}/vote")
    participant = participant_id_of(app, room["id"], room["token"])
    assert vote_rows(app) == [(room["id"], participant, room["options"][0], "yes")]


def test_rating_again_replaces_the_earlier_rating(app, client, room):
    vote(client, room["id"], room["options"][0], "yes")
    vote(client, room["id"], room["options"][0], "no")
    rows = vote_rows(app)
    assert len(rows) == 1
    assert rows[0][3] == "no"


def test_page_shows_exactly_one_card_with_three_buttons(client, room):
    html = page(client, room["id"])
    assert len(shown_option_ids(html)) == 1
    assert sum(label in html for label in LABELS) == 1
    for label in ["Rather yes", "Fine with me", "Rather not"]:
        assert label in html


def test_after_a_rating_the_next_option_is_shown(client, room):
    first = shown_option_ids(page(client, room["id"])).pop()
    vote(client, room["id"], first, "ok")
    second = shown_option_ids(page(client, room["id"]))
    assert len(second) == 1
    assert first not in second


def test_all_rated_page_lists_own_ratings_with_buttons(client, room):
    for option_id, rating in zip(room["options"], ["yes", "ok", "no"]):
        vote(client, room["id"], option_id, rating)
    html = page(client, room["id"])
    assert ALL_RATED_MESSAGE in html
    for label in LABELS:
        assert label in html
    assert shown_option_ids(html) == set(room["options"])
    for text in ["Your rating: Rather yes", "Your rating: Fine with me", "Your rating: Rather not"]:
        assert text in html


def test_has_finished_after_rating_every_option(app, client, room):
    participant = participant_id_of(app, room["id"], room["token"])
    for option_id in room["options"][:-1]:
        vote(client, room["id"], option_id, "yes")
    assert has_finished(app, participant) == 0
    vote(client, room["id"], room["options"][-1], "yes")
    assert has_finished(app, participant) == 1
    vote(client, room["id"], room["options"][0], "no")  # changing a rating later
    assert has_finished(app, participant) == 1


def test_get_votes_has_the_shape_the_winner_algorithm_takes(app, client, room):
    other = app.test_client()
    join(other, room["id"], "Ben")
    a, b, _ = room["options"]
    vote(client, room["id"], a, "yes")
    vote(client, room["id"], b, "no")
    vote(other, room["id"], a, "ok")
    # A vote in another room must not show up.
    stranger = app.test_client()
    other_room = create_room(stranger, title="Other room", nickname="Cleo")
    foreign_option = add_option(app, other_room, "Burger")
    set_room_status(app, other_room, "voting")
    vote(stranger, other_room, foreign_option, "no")
    anna = participant_id_of(app, room["id"], room["token"])
    ben = participant_id_of(app, room["id"], token_of(other, room["id"]))
    with app.app_context():
        votes = db.get_votes(room["id"])
    assert votes == {anna: {a: "yes", b: "no"}, ben: {a: "ok"}}
    assert pick_winner(room["options"], votes, []) == a


# --- Random order (F4) -----------------------------------------------------

def test_rating_order_contains_every_option_once():
    option_ids = [5, 3, 9, 1, 7]
    order = rating_order(option_ids, "some-token")
    assert sorted(order) == sorted(option_ids)


def test_rating_order_is_the_same_for_the_same_seed():
    option_ids = [1, 2, 3, 4, 5, 6]
    assert rating_order(option_ids, "token-a") == rating_order(option_ids, "token-a")
    # The order of the input list must not matter either.
    assert rating_order(option_ids, "token-a") == rating_order(list(reversed(option_ids)), "token-a")


def test_rating_order_differs_between_seeds():
    option_ids = [1, 2, 3, 4, 5, 6]
    orders = {tuple(rating_order(option_ids, f"token-{n}")) for n in range(50)}
    assert len(orders) > 1
    assert len({order[0] for order in orders}) > 1


def test_page_order_is_stable_and_seeded_by_the_session_token(client, room):
    first = shown_option_ids(page(client, room["id"]))
    assert shown_option_ids(page(client, room["id"])) == first  # reload
    expected = next_option_to_rate(rating_order(room["options"], room["token"]), set())
    assert first == {expected}


def test_next_option_to_rate():
    assert next_option_to_rate([3, 1, 2], set()) == 3
    assert next_option_to_rate([3, 1, 2], {3}) == 1
    assert next_option_to_rate([3, 1, 2], {3, 1, 2}) is None


# --- Rejected --------------------------------------------------------------

def test_collecting_room_rejects_votes(app, client):
    room_id = create_room(client)
    option_id = add_option(app, room_id, "Pizza")
    response = vote(client, room_id, option_id, "yes")
    assert response.status_code == 400
    assert NOT_STARTED_MESSAGE in response.get_data(as_text=True)
    assert vote_rows(app) == []
    html = page(client, room_id)
    assert NOT_STARTED_MESSAGE in html
    assert shown_option_ids(html) == set()


def test_closed_room_rejects_votes_and_keeps_earlier_rating(app, client, room):
    vote(client, room["id"], room["options"][0], "yes")
    set_room_status(app, room["id"], "closed")
    response = vote(client, room["id"], room["options"][0], "no")
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert [row[3] for row in vote_rows(app)] == ["yes"]
    assert CLOSED_MESSAGE in page(client, room["id"])


@pytest.mark.parametrize("rating", ["maybe", "", "YES", None])
def test_invalid_rating_is_rejected(app, client, room, rating):
    response = vote(client, room["id"], room["options"][0], rating)
    assert response.status_code == 400
    assert INVALID_RATING_MESSAGE in response.get_data(as_text=True)
    assert vote_rows(app) == []


def test_option_of_another_room_is_rejected(app, client, room):
    other_room = create_room(app.test_client(), title="Other room", nickname="Cleo")
    foreign_option = add_option(app, other_room, "Burger")
    response = vote(client, room["id"], foreign_option, "yes")
    assert response.status_code == 400
    assert UNKNOWN_OPTION_MESSAGE in response.get_data(as_text=True)
    assert vote_rows(app) == []


@pytest.mark.parametrize("option_id", ["99999", "abc", "", None])
def test_unknown_or_malformed_option_is_rejected(app, client, room, option_id):
    form = {"rating": "yes"}
    if option_id is not None:
        form["option_id"] = option_id
    response = client.post(f"/rooms/{room['id']}/vote", data=form)
    assert response.status_code == 400
    assert UNKNOWN_OPTION_MESSAGE in response.get_data(as_text=True)
    assert vote_rows(app) == []


def test_replaced_option_is_rejected_and_not_shown(app, client, room):
    replaced = add_option(app, room["id"], "Kebab", is_replaced=1)
    response = vote(client, room["id"], replaced, "yes")
    assert response.status_code == 400
    assert UNKNOWN_OPTION_MESSAGE in response.get_data(as_text=True)
    assert vote_rows(app) == []
    for option_id in room["options"]:
        vote(client, room["id"], option_id, "ok")
    html = page(client, room["id"])
    assert ALL_RATED_MESSAGE in html
    assert "Kebab" not in html


def test_visitor_without_token_cannot_vote(app, room):
    visitor = app.test_client()
    response = vote(visitor, room["id"], room["options"][0], "yes")
    assert response.status_code == 403
    assert vote_rows(app) == []
    response = visitor.get(f"/rooms/{room['id']}/vote")
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{room['id']}")


def test_token_of_another_room_counts_as_no_token(app, room):
    stranger = app.test_client()
    other_room = create_room(stranger, title="Other room", nickname="Cleo")
    foreign_token = token_of(stranger, other_room)
    with stranger.session_transaction() as session:
        tokens = dict(session["participant_tokens"])
        tokens[room["id"]] = foreign_token
        session["participant_tokens"] = tokens
    response = vote(stranger, room["id"], room["options"][0], "yes")
    assert response.status_code == 403
    assert vote_rows(app) == []


def test_unknown_room_is_404(client):
    assert client.get("/rooms/does-not-exist/vote").status_code == 404
    assert vote(client, "does-not-exist", 1, "yes").status_code == 404


def test_vote_errors_helper():
    assert vote_errors("voting", "yes", 1, [1, 2]) == []
    assert vote_errors("collecting", "yes", 1, [1, 2]) == [NOT_STARTED_MESSAGE]
    assert vote_errors("closed", "yes", 1, [1, 2]) == [CLOSED_MESSAGE]
    assert vote_errors("voting", "maybe", 1, [1, 2]) == [INVALID_RATING_MESSAGE]
    assert vote_errors("voting", "yes", 3, [1, 2]) == [UNKNOWN_OPTION_MESSAGE]
    assert vote_errors("voting", "yes", None, [1, 2]) == [UNKNOWN_OPTION_MESSAGE]


def test_rating_labels():
    assert RATING_LABELS == {"yes": "Rather yes", "ok": "Fine with me", "no": "Rather not"}


# --- Privacy ---------------------------------------------------------------

def test_no_page_shows_another_participants_rating(app, client, room):
    other = app.test_client()
    join(other, room["id"], "Ben")
    for option_id in room["options"]:
        vote(client, room["id"], option_id, "no")
    html = page(other, room["id"])
    assert "Your rating" not in html
    # Ben rates everything "yes": his overview shows only his own ratings.
    for option_id in room["options"]:
        vote(other, room["id"], option_id, "yes")
    html = page(other, room["id"])
    assert html.count("Your rating: Rather yes") == len(room["options"])
    assert "Your rating: Rather not" not in html


# --- Persistence -----------------------------------------------------------

def test_ratings_survive_a_restart(app, client, room):
    first = shown_option_ids(page(client, room["id"])).pop()
    vote(client, room["id"], first, "yes")
    for option_id in room["options"]:
        if option_id != first:
            vote(client, room["id"], option_id, "ok")
    participant = participant_id_of(app, room["id"], room["token"])
    rows_before = vote_rows(app)

    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": app.config["DATABASE"]}
    )
    assert vote_rows(restarted) == rows_before
    assert has_finished(restarted, participant) == 1
    browser = restarted.test_client()
    with browser.session_transaction() as session:
        session["participant_tokens"] = {room["id"]: room["token"]}
    assert ALL_RATED_MESSAGE in page(browser, room["id"])


def test_partial_ratings_continue_after_a_restart(app, client, room):
    first = shown_option_ids(page(client, room["id"])).pop()
    vote(client, room["id"], first, "yes")
    second = shown_option_ids(page(client, room["id"]))

    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": app.config["DATABASE"]}
    )
    browser = restarted.test_client()
    with browser.session_transaction() as session:
        session["participant_tokens"] = {room["id"]: room["token"]}
    assert shown_option_ids(page(browser, room["id"])) == second


# --- Code rules ------------------------------------------------------------

def test_voting_module_has_no_forbidden_imports():
    source = VOTING_FILE.read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import on line {node.lineno}"
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    for name in imported:
        assert name.split(".")[0] not in {"flask", "requests"}, name
        assert name != "app.db" and not name.startswith("app.db."), name


def test_save_vote_updates_a_row_saved_a_moment_earlier(app, room):
    """Simulates two simultaneous clicks: the second request finds the first one's row."""
    participant = participant_id_of(app, room["id"], room["token"])
    option_id = room["options"][0]
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, 'yes')",
            (room["id"], participant, option_id),
        )
        connection.commit()
        db.save_vote(room["id"], participant, option_id, "no")  # must not raise
    assert vote_rows(app) == [(room["id"], participant, option_id, "no")]
