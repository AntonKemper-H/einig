"""Tests for B3 – F6 Close the room and show the result (specs/b3-result.md)."""

import ast
import random
from pathlib import Path

import pytest

from app import create_app, db
from app.db import get_db
from app.services.results import close_errors, rating_counts
from app.services.scoring import pick_winner

ONLY_CREATOR_MESSAGE = "Only the creator can close the room."
NOT_STARTED_MESSAGE = "Voting has not started yet."
CLOSED_MESSAGE = "This room is closed. You can no longer vote."
NOT_CLOSED_MESSAGE = "The result is shown once the room is closed."
NO_WINNER_MESSAGE = "No winner: nobody rated any option."
LABELS = ["Pizza", "Sushi", "Tacos"]
RESULTS_FILE = Path(__file__).resolve().parents[1] / "app" / "services" / "results.py"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner on Friday", nickname="Anna", mode="manual"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(client, room_id, nickname):
    """Join a room (A3) with another browser."""
    response = client.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)


def add_option(client, room_id, label):
    """Add a manual option through the A4 form."""
    response = client.post(f"/rooms/{room_id}/options", data={"label": label})
    assert response.status_code in (302, 303)


def start(client, room_id):
    """Start the voting through the A5 button."""
    response = client.post(f"/rooms/{room_id}/start")
    assert response.status_code in (302, 303)


def vote(client, room_id, option_id, rating):
    return client.post(f"/rooms/{room_id}/vote", data={"option_id": str(option_id), "rating": rating})


def close(client, room_id):
    return client.post(f"/rooms/{room_id}/close")


def room_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def vote_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS total FROM votes").fetchone()["total"]


def set_room_status(app, room_id, status):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def set_search_centre(app, room_id):
    """Store a search centre as C2a does after a search."""
    with app.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE rooms SET search_center_lat = 38.737, search_center_lng = -9.153,"
            " radius_m = 1000, filters = '{}' WHERE id = ?",
            (room_id,),
        )
        connection.commit()


def add_veto(app, room_id, participant_id, option_id):
    """Insert a veto directly (the joker button comes in B4)."""
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO vetoes (room_id, participant_id, option_id) VALUES (?, ?, ?)",
            (room_id, participant_id, option_id),
        )
        connection.commit()


def token_of(client, room_id):
    with client.session_transaction() as session:
        return session["participant_tokens"][room_id]


def participant_id_of(app, client, room_id):
    with app.app_context():
        return db.get_participant(room_id, token_of(client, room_id))["id"]


def result_page(client, room_id):
    response = client.get(f"/rooms/{room_id}/result")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def assert_redirects_to(response, path):
    assert response.status_code == 303
    assert response.headers["Location"].endswith(path)


@pytest.fixture
def room(app, client):
    """A voting room: Anna (creator, `client`) and Ben (`guest`), options Pizza, Sushi, Tacos."""
    room_id = create_room(client)
    guest = app.test_client()
    join(guest, room_id, "Ben")
    for label in LABELS:
        add_option(client, room_id, label)
    start(client, room_id)
    with app.app_context():
        option_ids = {row["label"]: row["id"] for row in db.get_options(room_id)}
    return {"id": room_id, "guest": guest, "options": option_ids}


# --- Closing (accepted) ----------------------------------------------------

def test_creator_closes_and_winner_is_stored(app, client, room):
    pizza, sushi = room["options"]["Pizza"], room["options"]["Sushi"]
    vote(client, room["id"], pizza, "yes")
    vote(room["guest"], room["id"], pizza, "yes")
    vote(room["guest"], room["id"], sushi, "no")
    response = close(client, room["id"])
    assert_redirects_to(response, f"/rooms/{room['id']}/result")
    stored = room_row(app, room["id"])
    assert stored["status"] == "closed"
    assert stored["winner_option_id"] == pizza


def test_closing_deletes_the_search_centre(app, client, room):
    set_search_centre(app, room["id"])
    vote(client, room["id"], room["options"]["Pizza"], "yes")
    close(client, room["id"])
    stored = room_row(app, room["id"])
    assert stored["search_center_lat"] is None
    assert stored["search_center_lng"] is None
    assert stored["radius_m"] == 1000
    assert stored["filters"] == "{}"


def test_stored_winner_matches_the_algorithm_with_unrated_options(app, client, room):
    # D11 example: Pizza rated only by Anna ("yes"); Sushi "ok" by both.
    pizza, sushi = room["options"]["Pizza"], room["options"]["Sushi"]
    vote(client, room["id"], pizza, "yes")
    vote(client, room["id"], sushi, "ok")
    vote(room["guest"], room["id"], sushi, "ok")
    with app.app_context():
        expected = pick_winner(
            list(room["options"].values()), db.get_votes(room["id"]), [], rng=random.Random(room["id"])
        )
    close(client, room["id"])
    assert room_row(app, room["id"])["winner_option_id"] == expected == pizza


def test_vetoed_option_is_not_chosen(app, client, room):
    pizza, sushi = room["options"]["Pizza"], room["options"]["Sushi"]
    vote(client, room["id"], pizza, "yes")
    vote(room["guest"], room["id"], pizza, "yes")
    add_veto(app, room["id"], participant_id_of(app, room["guest"], room["id"]), pizza)
    close(client, room["id"])
    winner = room_row(app, room["id"])["winner_option_id"]
    assert winner is not None
    assert winner != pizza
    assert winner in (sushi, room["options"]["Tacos"])


def test_nobody_voted_closes_without_winner(app, client, room):
    close(client, room["id"])
    stored = room_row(app, room["id"])
    assert stored["status"] == "closed"
    assert stored["winner_option_id"] is None


def test_full_tie_is_decided_with_the_room_id_as_seed(app):
    # Eight rooms with a full three-way tie: an unseeded random choice would match
    # random.Random(room_id) in all of them only by luck (1 in 3^8).
    for number in range(8):
        browser = app.test_client()
        room_id = create_room(browser, title=f"Tie {number}")
        for label in LABELS:
            add_option(browser, room_id, label)
        start(browser, room_id)
        with app.app_context():
            option_ids = [row["id"] for row in db.get_options(room_id)]
        for option_id in option_ids:
            vote(browser, room_id, option_id, "ok")
        with app.app_context():
            expected = pick_winner(
                option_ids, db.get_votes(room_id), [], rng=random.Random(room_id)
            )
        close(browser, room_id)
        assert room_row(app, room_id)["winner_option_id"] == expected


def test_closing_again_keeps_the_stored_winner(app, client, room):
    pizza, sushi = room["options"]["Pizza"], room["options"]["Sushi"]
    vote(client, room["id"], pizza, "yes")
    close(client, room["id"])
    # Change the votes directly in the database: a second close must not recalculate.
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE votes SET rating = 'no' WHERE option_id = ?", (pizza,))
        connection.execute(
            "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, 'yes')",
            (room["id"], participant_id_of(app, client, room["id"]), sushi),
        )
        connection.commit()
    response = close(client, room["id"])
    assert_redirects_to(response, f"/rooms/{room['id']}/result")
    assert room_row(app, room["id"])["winner_option_id"] == pizza


# --- Closing (rejected) ----------------------------------------------------

def test_non_creator_cannot_close(app, room):
    before = tuple(room_row(app, room["id"]))
    response = close(room["guest"], room["id"])
    assert response.status_code == 403
    assert ONLY_CREATOR_MESSAGE in response.get_data(as_text=True)
    assert tuple(room_row(app, room["id"])) == before


def test_visitor_and_other_room_participant_cannot_close(app, room):
    before = tuple(room_row(app, room["id"]))
    visitor = app.test_client()
    assert close(visitor, room["id"]).status_code == 403
    stranger = app.test_client()
    create_room(stranger, title="Other room", nickname="Cleo")
    assert close(stranger, room["id"]).status_code == 403
    assert tuple(room_row(app, room["id"])) == before


def test_collecting_room_cannot_be_closed(app, client):
    room_id = create_room(client)
    add_option(client, room_id, "Pizza")
    before = tuple(room_row(app, room_id))
    response = close(client, room_id)
    assert response.status_code == 400
    assert NOT_STARTED_MESSAGE in response.get_data(as_text=True)
    assert tuple(room_row(app, room_id)) == before


def test_unknown_room_is_404(client):
    assert close(client, "does-not-exist").status_code == 404
    assert client.get("/rooms/does-not-exist/result").status_code == 404


def test_lost_claim_redirects_and_keeps_first_winner(app, client, room, monkeypatch):
    pizza = room["options"]["Pizza"]
    vote(client, room["id"], pizza, "yes")
    close(client, room["id"])
    # Simulate a second close that passed the route's status check before the first one committed.
    real_get_room = db.get_room

    def room_still_voting(room_id):
        row = dict(real_get_room(room_id))
        row["status"] = "voting"
        return row

    monkeypatch.setattr(db, "get_room", room_still_voting)
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE votes SET rating = 'no' WHERE option_id = ?", (pizza,))
        connection.commit()
    response = close(client, room["id"])
    assert_redirects_to(response, f"/rooms/{room['id']}/result")
    assert room_row(app, room["id"])["winner_option_id"] == pizza


def test_claim_close_only_once(app, client, room):
    with app.app_context():
        with db.transaction():
            assert db.claim_close(room["id"]) is True
        with db.transaction():
            assert db.claim_close(room["id"]) is False
    collecting = create_room(client, title="Still collecting")
    with app.app_context(), db.transaction():
        assert db.claim_close(collecting) is False


def test_close_errors_helper():
    assert close_errors(True, "voting") is None
    assert close_errors(False, "voting") == (403, ONLY_CREATOR_MESSAGE)
    assert close_errors(True, "collecting") == (400, NOT_STARTED_MESSAGE)
    assert close_errors(True, "closed") is None  # idempotent: the route shows the result
    # The creator check comes first, whatever the status.
    assert close_errors(False, "closed") == (403, ONLY_CREATOR_MESSAGE)
    assert close_errors(False, "collecting") == (403, ONLY_CREATOR_MESSAGE)


# --- Result page -----------------------------------------------------------

def test_result_page_names_the_winner(client, room):
    vote(client, room["id"], room["options"]["Pizza"], "yes")
    close(client, room["id"])
    assert "The group's choice: Pizza" in result_page(client, room["id"])


def test_google_winner_is_named_as_a_google_place(app, client):
    room_id = create_room(client, mode="nearby")
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', 'place-x')",
            (room_id,),
        )
        connection.execute(
            "INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', 'place-y')",
            (room_id,),
        )
        connection.commit()
        option_id = connection.execute(
            "SELECT id FROM options WHERE place_id = 'place-x'"
        ).fetchone()["id"]
    set_room_status(app, room_id, "voting")
    vote(client, room_id, option_id, "yes")
    close(client, room_id)
    html = result_page(client, room_id)
    assert "The group's choice: Place from Google Maps" in html
    assert "place-x" not in html


def test_result_page_shows_anonymous_counts(client, room):
    pizza = room["options"]["Pizza"]
    vote(client, room["id"], pizza, "yes")
    vote(room["guest"], room["id"], pizza, "ok")
    close(client, room["id"])
    html = result_page(client, room["id"])
    assert "1× Rather yes · 1× Fine with me · 0× Rather not" in html
    # Sushi and Tacos were not rated by anyone.
    assert html.count("0× Rather yes · 0× Fine with me · 0× Rather not") == 2


def test_result_page_without_winner(client, room):
    close(client, room["id"])
    html = result_page(client, room["id"])
    assert NO_WINNER_MESSAGE in html
    assert "The group's choice" not in html


def test_result_page_before_closing(client, room):
    vote(client, room["id"], room["options"]["Pizza"], "yes")
    html = result_page(client, room["id"])
    assert NOT_CLOSED_MESSAGE in html
    assert f"/rooms/{room['id']}/lobby" in html
    assert "The group's choice" not in html


def test_visitor_is_sent_to_the_room_page(app, room):
    visitor = app.test_client()
    assert_redirects_to(visitor.get(f"/rooms/{room['id']}/result"), f"/rooms/{room['id']}")
    stranger = app.test_client()
    create_room(stranger, title="Other room", nickname="Cleo")
    assert_redirects_to(stranger.get(f"/rooms/{room['id']}/result"), f"/rooms/{room['id']}")


def test_rating_counts_counts_only_real_ratings():
    votes = {10: {1: "yes", 2: "no"}, 11: {1: "ok"}, 12: {}}
    assert rating_counts([1, 2, 3], votes) == {
        1: {"yes": 1, "ok": 1, "no": 0},
        2: {"yes": 0, "ok": 0, "no": 1},
        3: {"yes": 0, "ok": 0, "no": 0},
    }


# --- Privacy ---------------------------------------------------------------

def test_result_page_shows_no_nicknames(app):
    # Made-up names that cannot appear in normal page text (unlike "Ben" in "Benefit").
    creator, guest = app.test_client(), app.test_client()
    room_id = create_room(creator, nickname="Zorbia")
    join(guest, room_id, "Quentix")
    for label in LABELS:
        add_option(creator, room_id, label)
    start(creator, room_id)
    with app.app_context():
        option_ids = [row["id"] for row in db.get_options(room_id)]
    for option_id in option_ids:
        vote(creator, room_id, option_id, "yes")
        vote(guest, room_id, option_id, "no")
    close(creator, room_id)
    for browser in (creator, guest):
        html = result_page(browser, room_id)
        assert "Zorbia" not in html
        assert "Quentix" not in html


# --- Votes after closing ---------------------------------------------------

def test_vote_after_closing_is_rejected(app, client, room):
    close(client, room["id"])
    response = vote(room["guest"], room["id"], room["options"]["Pizza"], "yes")
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert vote_count(app) == 0


def test_vote_reaching_the_database_after_closing_is_not_saved(app, client, room, monkeypatch):
    close(client, room["id"])
    real_get_room = db.get_room

    def room_still_voting(room_id):
        row = dict(real_get_room(room_id))
        row["status"] = "voting"
        return row

    # The route still sees "voting", as if it checked a moment before the close committed.
    monkeypatch.setattr(db, "get_room", room_still_voting)
    response = vote(room["guest"], room["id"], room["options"]["Pizza"], "yes")
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert vote_count(app) == 0


def test_save_vote_returns_whether_it_saved(app, client, room):
    participant = participant_id_of(app, client, room["id"])
    pizza = room["options"]["Pizza"]
    with app.app_context(), db.transaction():
        assert db.save_vote(room["id"], participant, pizza, "yes") is True
    assert vote_count(app) == 1
    set_room_status(app, room["id"], "closed")
    with app.app_context(), db.transaction():
        assert db.save_vote(room["id"], participant, pizza, "no") is False
    with app.app_context():
        assert db.get_votes(room["id"]) == {participant: {pizza: "yes"}}


# --- Rating page links -----------------------------------------------------

def test_creator_sees_close_button_while_voting(client, room):
    close_action = f'action="/rooms/{room["id"]}/close"'
    assert close_action in client.get(f"/rooms/{room['id']}/vote").get_data(as_text=True)
    assert close_action not in room["guest"].get(f"/rooms/{room['id']}/vote").get_data(as_text=True)


def test_everyone_sees_result_link_once_closed(client, room):
    close(client, room["id"])
    for browser in (client, room["guest"]):
        html = browser.get(f"/rooms/{room['id']}/vote").get_data(as_text=True)
        assert f'href="/rooms/{room["id"]}/result"' in html


# --- Persistence -----------------------------------------------------------

def test_result_survives_a_restart(app, client, room):
    vote(client, room["id"], room["options"]["Sushi"], "yes")
    close(client, room["id"])
    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": app.config["DATABASE"]}
    )
    stored = room_row(restarted, room["id"])
    assert stored["status"] == "closed"
    assert stored["winner_option_id"] == room["options"]["Sushi"]
    browser = restarted.test_client()
    with browser.session_transaction() as session:
        session["participant_tokens"] = {room["id"]: token_of(client, room["id"])}
    assert "The group's choice: Sushi" in result_page(browser, room["id"])


# --- Code rules ------------------------------------------------------------

def test_results_module_has_no_forbidden_imports():
    source = RESULTS_FILE.read_text(encoding="utf-8")
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
