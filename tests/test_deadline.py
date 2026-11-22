"""Tests for B5 – F11 Deadline (specs/b5-deadline.md)."""

import ast
import random
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import create_app, db
from app.db import get_db
from app.services.deadline import (
    INVALID_TIME_LIMIT_MESSAGE,
    TIME_LIMITS,
    deadline_after,
    format_utc,
    is_past,
    minutes_left,
    now_utc,
    parse_time_limit,
    time_left_text,
)
from app.services.scoring import pick_winner
from typed_option import add_typed_option

CLOSED_MESSAGE = "This room is closed. You can no longer vote."
LABELS = ["Pizza", "Sushi", "Tacos"]
DEADLINE_FILE = Path(__file__).resolve().parents[1] / "app" / "services" / "deadline.py"


# --- Helpers ---------------------------------------------------------------

def utc_text(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def in_utc(**delta):
    """Server time (UTC) plus the given timedelta, as stored text."""
    return utc_text(datetime.now(UTC) + timedelta(**delta))


def create_room(client, title="Dinner on Friday", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(app, room_id, nickname):
    browser = app.test_client()
    response = browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)
    return browser


def add_option(client, room_id, label):
    response = add_typed_option(client, room_id, label)
    assert response.status_code in (302, 303)


def start(client, room_id, **form):
    return client.post(f"/rooms/{room_id}/start", data=form)


def vote(client, room_id, option_id, rating):
    return client.post(f"/rooms/{room_id}/vote", data={"option_id": str(option_id), "rating": rating})


def room_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def set_deadline(app, room_id, deadline):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET deadline = ? WHERE id = ?", (deadline, room_id))
        connection.commit()


def set_search_centre(app, room_id):
    with app.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE rooms SET search_center_lat = 38.737, search_center_lng = -9.153, radius_m = 1000 WHERE id = ?",
            (room_id,),
        )
        connection.commit()


def vote_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS total FROM votes").fetchone()["total"]


def expected_winner(app, room_id):
    """What B3's close would store for the votes and vetoes now in the database."""
    with app.app_context():
        option_ids = [option["id"] for option in db.get_rateable_options(room_id)]
        return pick_winner(
            option_ids, db.get_votes(room_id), db.get_vetoed_option_ids(room_id), rng=random.Random(room_id)
        )


def token_of(client, room_id):
    with client.session_transaction() as session:
        return session["participant_tokens"][room_id]


def participant_id_of(app, client, room_id):
    with app.app_context():
        return db.get_participant(room_id, token_of(client, room_id))["id"]


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


@pytest.fixture
def collecting(app, client):
    """A collecting room: Anna (creator, `client`) and Ben (`guest`), options Pizza, Sushi, Tacos."""
    room_id = create_room(client)
    guest = join(app, room_id, "Ben")
    for label in LABELS:
        add_option(client, room_id, label)
    with app.app_context():
        options = {row["label"]: row["id"] for row in db.get_options(room_id)}
    return {"id": room_id, "guest": guest, "options": options}


@pytest.fixture
def room(client, collecting):
    """The same room, voting, without a deadline (tests set one where needed)."""
    assert start(client, collecting["id"]).status_code == 303
    return collecting


# --- Starting with a time limit --------------------------------------------

def test_start_with_a_time_limit_stores_the_deadline(app, client, collecting):
    before = datetime.now(UTC)
    response = start(client, collecting["id"], time_limit="30")
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{collecting['id']}/lobby")
    row = room_row(app, collecting["id"])
    assert row["status"] == "voting"
    stored = datetime.strptime(row["deadline"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    expected = before + timedelta(minutes=30)
    assert abs((stored - expected).total_seconds()) < 5


@pytest.mark.parametrize("form", [{}, {"time_limit": ""}])
def test_start_without_a_time_limit_keeps_no_deadline(app, client, collecting, form):
    assert start(client, collecting["id"], **form).status_code == 303
    row = room_row(app, collecting["id"])
    assert row["status"] == "voting"
    assert row["deadline"] is None


@pytest.mark.parametrize("value", ["45", "abc", "-15"])
def test_start_with_an_invalid_time_limit_is_rejected(app, client, collecting, value):
    response = start(client, collecting["id"], time_limit=value)
    assert response.status_code == 400
    assert INVALID_TIME_LIMIT_MESSAGE in response.get_data(as_text=True)
    row = room_row(app, collecting["id"])
    assert row["status"] == "collecting"
    assert row["deadline"] is None


def test_lobby_start_form_has_the_time_limit_choice(client, collecting):
    html = page(client, f"/rooms/{collecting['id']}/lobby")
    form = re.search(rf'<form[^>]*action="/rooms/{collecting["id"]}/start".*?</form>', html, flags=re.DOTALL)
    assert form, "start form missing"
    select = re.search(r'<select[^>]*name="time_limit".*?</select>', form.group(0), flags=re.DOTALL)
    assert select, "time_limit choice missing in the start form"
    values = re.findall(r'<option[^>]*value="([^"]*)"', select.group(0))
    assert values == ["", "15", "30", "60"]
    guest_html = page(collecting["guest"], f"/rooms/{collecting['id']}/lobby")
    assert 'name="time_limit"' not in guest_html


# --- While voting ----------------------------------------------------------

def test_pages_show_the_minutes_left(app, client, room):
    set_deadline(app, room["id"], in_utc(minutes=11, seconds=30))
    assert "Time left: 12 min" in page(client, f"/rooms/{room['id']}/vote")
    assert "Time left: 12 min" in page(client, f"/rooms/{room['id']}/lobby")


def test_no_time_left_text_without_a_deadline(client, room):
    assert "Time left" not in page(client, f"/rooms/{room['id']}/vote")
    assert "Time left" not in page(client, f"/rooms/{room['id']}/lobby")


def test_vote_before_the_deadline_is_saved(app, client, room):
    set_deadline(app, room["id"], in_utc(minutes=10))
    assert vote(client, room["id"], room["options"]["Pizza"], "yes").status_code == 303
    assert vote_count(app) == 1


def test_pages_before_the_deadline_do_not_close_the_room(app, client, room):
    set_deadline(app, room["id"], in_utc(minutes=10))
    for path in ("vote", "lobby", "result", ""):
        page(client, f"/rooms/{room['id']}/{path}".rstrip("/"))
    assert room_row(app, room["id"])["status"] == "voting"


def test_room_without_a_deadline_is_never_closed_by_pages(app, client, room):
    for path in ("vote", "lobby", "result", ""):
        page(client, f"/rooms/{room['id']}/{path}".rstrip("/"))
    assert room_row(app, room["id"])["status"] == "voting"


# --- Closing when the time is up -------------------------------------------

def test_rating_page_closes_the_room_when_time_is_up(app, client, room):
    pizza, sushi = room["options"]["Pizza"], room["options"]["Sushi"]
    vote(client, room["id"], pizza, "no")
    vote(room["guest"], room["id"], sushi, "yes")
    set_search_centre(app, room["id"])
    set_deadline(app, room["id"], in_utc(seconds=-5))
    winner = expected_winner(app, room["id"])
    html = page(client, f"/rooms/{room['id']}/vote")
    row = room_row(app, room["id"])
    assert row["status"] == "closed"
    assert row["winner_option_id"] == winner == sushi
    assert row["search_center_lat"] is None and row["search_center_lng"] is None
    assert CLOSED_MESSAGE in html
    assert f'href="/rooms/{room["id"]}/result"' in html


@pytest.mark.parametrize("path", ["lobby", "result", ""])
def test_other_pages_also_close_the_room(app, client, room, path):
    vote(client, room["id"], room["options"]["Tacos"], "yes")
    set_deadline(app, room["id"], in_utc(seconds=-5))
    html = page(client, f"/rooms/{room['id']}/{path}".rstrip("/"))
    row = room_row(app, room["id"])
    assert row["status"] == "closed"
    assert row["winner_option_id"] == room["options"]["Tacos"]
    if path == "result":
        assert "The group's choice: Tacos" in html


def test_a_visitor_opening_the_room_page_closes_it(app, room):
    set_deadline(app, room["id"], in_utc(seconds=-5))
    visitor = app.test_client()
    page(visitor, f"/rooms/{room['id']}")
    assert room_row(app, room["id"])["status"] == "closed"


def test_participants_who_did_not_vote_are_not_counted(app, client, room):
    vote(client, room["id"], room["options"]["Pizza"], "no")
    vote(client, room["id"], room["options"]["Sushi"], "ok")
    vote(client, room["id"], room["options"]["Tacos"], "yes")
    set_deadline(app, room["id"], in_utc(seconds=-5))
    page(room["guest"], f"/rooms/{room['id']}/vote")
    assert room_row(app, room["id"])["winner_option_id"] == room["options"]["Tacos"]


def test_automatic_close_is_idempotent(app, client, room):
    vote(client, room["id"], room["options"]["Sushi"], "yes")
    set_deadline(app, room["id"], in_utc(seconds=-5))
    page(client, f"/rooms/{room['id']}/vote")
    first = room_row(app, room["id"])["winner_option_id"]
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE votes SET rating = 'no'")
        connection.execute(
            "INSERT INTO votes (room_id, participant_id, option_id, rating) VALUES (?, ?, ?, 'yes')",
            (room["id"], participant_id_of(app, client, room["id"]), room["options"]["Pizza"]),
        )
        connection.commit()
    page(client, f"/rooms/{room['id']}/lobby")
    page(client, f"/rooms/{room['id']}/result")
    assert room_row(app, room["id"])["winner_option_id"] == first == room["options"]["Sushi"]


def test_two_closes_at_once_keep_the_first_winner(app, client, room, monkeypatch):
    vote(client, room["id"], room["options"]["Sushi"], "yes")
    set_deadline(app, room["id"], in_utc(seconds=-5))
    page(client, f"/rooms/{room['id']}/vote")
    first = room_row(app, room["id"])["winner_option_id"]
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE votes SET option_id = ?", (room["options"]["Pizza"],))
        connection.commit()
    real_get_room = db.get_room

    def room_still_voting(room_id):
        row = dict(real_get_room(room_id))
        row["status"] = "voting"
        return row

    # This request loaded the room a moment before the other one closed it.
    monkeypatch.setattr(db, "get_room", room_still_voting)
    client.get(f"/rooms/{room['id']}/vote")
    monkeypatch.undo()
    assert room_row(app, room["id"])["winner_option_id"] == first == room["options"]["Sushi"]


def test_a_joker_counts_in_the_automatic_close(app, client, room):
    pizza, sushi, tacos = (room["options"][label] for label in LABELS)
    join(app, room["id"], "Cara")  # never rates, so only the deadline closes the room
    for browser in (client, room["guest"]):
        vote(browser, room["id"], pizza, "yes")
        vote(browser, room["id"], sushi, "ok")
        vote(browser, room["id"], tacos, "no")
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO vetoes (room_id, participant_id, option_id) VALUES (?, ?, ?)",
            (room["id"], participant_id_of(app, room["guest"], room["id"]), pizza),
        )
        connection.commit()
    set_deadline(app, room["id"], in_utc(seconds=-5))
    page(client, f"/rooms/{room['id']}/vote")
    assert room_row(app, room["id"])["winner_option_id"] == sushi


def test_full_tie_is_decided_with_the_room_id_as_seed(app):
    # Eight rooms where every option ties: an unseeded choice would match all eight
    # stored winners only by chance (1 in 3 per room).
    for number in range(8):
        creator = app.test_client()
        room_id = create_room(creator, title=f"Tie {number}")
        for label in LABELS:
            add_option(creator, room_id, label)
        assert start(creator, room_id).status_code == 303
        with app.app_context():
            option_ids = [option["id"] for option in db.get_options(room_id)]
        for option_id in option_ids:
            vote(creator, room_id, option_id, "ok")
        set_deadline(app, room_id, in_utc(seconds=-5))
        expected = expected_winner(app, room_id)
        page(creator, f"/rooms/{room_id}/vote")
        assert room_row(app, room_id)["winner_option_id"] == expected


def test_creator_can_still_close_before_the_deadline(app, client, room):
    vote(client, room["id"], room["options"]["Pizza"], "yes")
    set_deadline(app, room["id"], in_utc(minutes=10))
    assert client.post(f"/rooms/{room['id']}/close").status_code == 303
    assert room_row(app, room["id"])["winner_option_id"] == room["options"]["Pizza"]
    vote(room["guest"], room["id"], room["options"]["Sushi"], "yes")
    set_deadline(app, room["id"], in_utc(seconds=-5))
    page(client, f"/rooms/{room['id']}/vote")
    assert room_row(app, room["id"])["winner_option_id"] == room["options"]["Pizza"]


# --- Closing when everyone is done -----------------------------------------

def rate_all(browser, room, rating="ok"):
    responses = [vote(browser, room["id"], option_id, rating) for option_id in room["options"].values()]
    return responses[-1]


def test_last_rating_of_the_last_participant_closes_the_room(app, client, room):
    set_search_centre(app, room["id"])
    rate_all(client, room, "ok")
    assert room_row(app, room["id"])["status"] == "voting"
    vote(room["guest"], room["id"], room["options"]["Pizza"], "no")
    vote(room["guest"], room["id"], room["options"]["Sushi"], "yes")
    winner = None
    with app.app_context():
        # What B3's close will store once Ben's last rating is in.
        option_ids = [option["id"] for option in db.get_rateable_options(room["id"])]
        votes = db.get_votes(room["id"])
        votes[participant_id_of(app, room["guest"], room["id"])][room["options"]["Tacos"]] = "no"
        winner = pick_winner(option_ids, votes, [], rng=random.Random(room["id"]))
    response = vote(room["guest"], room["id"], room["options"]["Tacos"], "no")
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{room['id']}/result")
    row = room_row(app, room["id"])
    assert row["status"] == "closed"
    assert row["winner_option_id"] == winner == room["options"]["Sushi"]
    assert row["search_center_lat"] is None and row["search_center_lng"] is None


def test_partly_rated_keeps_the_room_open(app, client, room):
    rate_all(client, room)
    response = vote(room["guest"], room["id"], room["options"]["Pizza"], "yes")
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{room['id']}/vote")
    assert room_row(app, room["id"])["status"] == "voting"


def test_a_participant_who_rated_nothing_keeps_the_room_open(app, client, room):
    join(app, room["id"], "Cara")
    rate_all(client, room)
    response = rate_all(room["guest"], room)
    assert response.headers["Location"].endswith(f"/rooms/{room['id']}/vote")
    assert room_row(app, room["id"])["status"] == "voting"


def test_a_joker_does_not_count_as_done(app, client, room):
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO vetoes (room_id, participant_id, option_id) VALUES (?, ?, ?)",
            (room["id"], participant_id_of(app, room["guest"], room["id"]), room["options"]["Pizza"]),
        )
        connection.commit()
    rate_all(client, room)
    assert room_row(app, room["id"])["status"] == "voting"


def test_room_closed_by_everyone_done_is_not_recalculated(app, client, room):
    rate_all(client, room, "ok")
    vote(room["guest"], room["id"], room["options"]["Pizza"], "ok")
    vote(room["guest"], room["id"], room["options"]["Sushi"], "ok")
    vote(room["guest"], room["id"], room["options"]["Tacos"], "yes")
    first = room_row(app, room["id"])["winner_option_id"]
    assert first == room["options"]["Tacos"]
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE votes SET rating = 'no' WHERE option_id = ?", (room["options"]["Tacos"],))
        connection.commit()
    set_deadline(app, room["id"], in_utc(seconds=-5))
    page(client, f"/rooms/{room['id']}/vote")
    assert client.post(f"/rooms/{room['id']}/close").status_code == 303
    assert room_row(app, room["id"])["winner_option_id"] == first


def test_everyone_finished(app, client, room):
    with app.app_context():
        assert db.everyone_finished(room["id"]) is False
    rate_all(client, room)
    with app.app_context():
        assert db.everyone_finished(room["id"]) is False
        connection = get_db()
        connection.execute("UPDATE participants SET has_finished = 1 WHERE room_id = ?", (room["id"],))
        connection.commit()
        assert db.everyone_finished(room["id"]) is True
        assert db.everyone_finished("no-such-room") is False


# --- Votes after the deadline ----------------------------------------------

def test_vote_after_the_deadline_is_rejected(app, client, room):
    set_deadline(app, room["id"], in_utc(seconds=-5))
    response = vote(room["guest"], room["id"], room["options"]["Pizza"], "yes")
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert vote_count(app) == 0
    assert room_row(app, room["id"])["status"] == "closed"


def test_vote_reaching_the_database_after_the_deadline_is_not_saved(app, client, room, monkeypatch):
    set_deadline(app, room["id"], in_utc(seconds=-5))
    real_get_room = db.get_room

    def room_with_time_left(room_id):
        row = dict(real_get_room(room_id))
        row["deadline"] = in_utc(minutes=10)
        return row

    # The route still sees time left, as if it checked a moment before the deadline.
    monkeypatch.setattr(db, "get_room", room_with_time_left)
    response = vote(room["guest"], room["id"], room["options"]["Pizza"], "yes")
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert vote_count(app) == 0


def test_save_vote_respects_the_deadline(app, client, room):
    participant = participant_id_of(app, client, room["id"])
    pizza = room["options"]["Pizza"]
    set_deadline(app, room["id"], "2026-11-20 19:00:00")
    with app.app_context(), db.transaction():
        assert db.save_vote(room["id"], participant, pizza, "yes", now="2026-11-20 18:59:59") is True
    for now in ("2026-11-20 19:00:00", "2026-11-20 19:00:01"):
        with app.app_context(), db.transaction():
            assert db.save_vote(room["id"], participant, pizza, "no", now=now) is False
    with app.app_context():
        assert db.get_votes(room["id"]) == {participant: {pizza: "yes"}}


# --- Helpers ---------------------------------------------------------------

def test_parse_time_limit():
    assert TIME_LIMITS == (15, 30, 60)
    for raw in (None, "", " "):
        assert parse_time_limit(raw) == (None, [])
    for raw, minutes in (("15", 15), ("30", 30), ("60", 60)):
        assert parse_time_limit(raw) == (minutes, [])
    for raw in ("45", "abc", "-15", "15.0"):
        assert parse_time_limit(raw) == (None, [INVALID_TIME_LIMIT_MESSAGE])


def test_format_utc_and_deadline_after():
    moment = datetime(2026, 11, 16, 23, 50, 0, tzinfo=UTC)
    assert format_utc(moment) == "2026-11-16 23:50:00"
    assert deadline_after(moment, 15) == "2026-11-17 00:05:00"
    lisbon_summer = datetime(2026, 7, 1, 20, 0, 0, tzinfo=timezone(timedelta(hours=1)))
    assert format_utc(lisbon_summer) == "2026-07-01 19:00:00"


def test_is_past():
    deadline = "2026-11-20 19:00:00"
    at = datetime(2026, 11, 20, 19, 0, 0, tzinfo=UTC)
    assert is_past(None, at) is False
    assert is_past(deadline, at - timedelta(seconds=1)) is False
    assert is_past(deadline, at) is True
    assert is_past(deadline, at + timedelta(minutes=5)) is True


def test_minutes_left_and_time_left_text():
    deadline = "2026-11-20 19:00:00"
    at = datetime(2026, 11, 20, 19, 0, 0, tzinfo=UTC)
    assert minutes_left(None, at) is None
    assert time_left_text(None, at) is None
    assert minutes_left(deadline, at - timedelta(minutes=11, seconds=30)) == 12
    assert time_left_text(deadline, at - timedelta(minutes=11, seconds=30)) == "Time left: 12 min"
    assert minutes_left(deadline, at - timedelta(seconds=10)) == 1
    assert minutes_left(deadline, at) == 0
    assert minutes_left(deadline, at + timedelta(minutes=3)) == 0
    assert time_left_text(deadline, at) is None


def test_now_utc_is_aware_and_in_utc():
    moment = now_utc()
    assert moment.tzinfo is not None
    assert moment.utcoffset() == timedelta(0)
    assert abs((moment - datetime.now(UTC)).total_seconds()) < 5


# --- Persistence -----------------------------------------------------------

def test_deadline_survives_a_restart(app, client, room):
    vote(client, room["id"], room["options"]["Sushi"], "yes")
    set_deadline(app, room["id"], in_utc(seconds=-5))
    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": app.config["DATABASE"]}
    )
    assert room_row(restarted, room["id"])["deadline"] is not None
    browser = restarted.test_client()
    with browser.session_transaction() as session:
        session["participant_tokens"] = {room["id"]: token_of(client, room["id"])}
    page(browser, f"/rooms/{room['id']}/vote")
    row = room_row(restarted, room["id"])
    assert row["status"] == "closed"
    assert row["winner_option_id"] == room["options"]["Sushi"]


# --- Code rules ------------------------------------------------------------

def test_deadline_module_has_no_forbidden_imports():
    source = DEADLINE_FILE.read_text(encoding="utf-8")
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
