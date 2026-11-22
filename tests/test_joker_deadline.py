"""Tests for the B4 follow-up with B5: the joker and the deadline (specs/b4-joker.md, "Follow-up with B5")."""

from datetime import UTC, datetime, timedelta

import pytest

from app import db
from app.db import get_db
from typed_option import add_typed_option

CLOSED_MESSAGE = "This room is closed. You can no longer vote."
LABELS = ["Pizza", "Sushi", "Tacos"]


def in_utc(**delta):
    return (datetime.now(UTC) + timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


def create_room(client):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": "Anna"})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def use_joker(client, room_id, option_id):
    return client.post(f"/rooms/{room_id}/veto", data={"option_id": str(option_id)})


def set_deadline(app, room_id, deadline):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET deadline = ? WHERE id = ?", (deadline, room_id))
        connection.commit()


def veto_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS total FROM vetoes").fetchone()["total"]


def room_status(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()["status"]


def participant_id_of(app, client, room_id):
    with client.session_transaction() as session:
        token = session["participant_tokens"][room_id]
    with app.app_context():
        return db.get_participant(room_id, token)["id"]


@pytest.fixture
def room(app, client):
    """A voting room: Anna (creator, `client`) and Ben (`guest`), options Pizza, Sushi, Tacos."""
    room_id = create_room(client)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"}).status_code in (302, 303)
    for label in LABELS:
        assert add_typed_option(client, room_id, label).status_code in (302, 303)
    assert client.post(f"/rooms/{room_id}/start").status_code == 303
    with app.app_context():
        options = {row["label"]: row["id"] for row in db.get_options(room_id)}
    return {"id": room_id, "guest": guest, "options": options}


def test_joker_before_the_deadline_is_saved(app, client, room):
    set_deadline(app, room["id"], in_utc(minutes=10))
    assert use_joker(client, room["id"], room["options"]["Pizza"]).status_code == 303
    assert veto_count(app) == 1


def test_joker_after_the_deadline_is_rejected(app, client, room):
    set_deadline(app, room["id"], in_utc(seconds=-5))
    response = use_joker(room["guest"], room["id"], room["options"]["Pizza"])
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert veto_count(app) == 0
    assert room_status(app, room["id"]) == "closed"


def test_joker_reaching_the_database_after_the_deadline_is_not_saved(app, client, room, monkeypatch):
    set_deadline(app, room["id"], in_utc(seconds=-5))
    real_get_room = db.get_room

    def room_with_time_left(room_id):
        row = dict(real_get_room(room_id))
        row["deadline"] = in_utc(minutes=10)
        return row

    # The route still sees time left, as if it checked a moment before the deadline.
    monkeypatch.setattr(db, "get_room", room_with_time_left)
    response = use_joker(room["guest"], room["id"], room["options"]["Pizza"])
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert veto_count(app) == 0


def test_save_veto_respects_the_deadline(app, client, room):
    participant = participant_id_of(app, client, room["id"])
    pizza = room["options"]["Pizza"]
    set_deadline(app, room["id"], "2026-11-20 19:00:00")
    for now in ("2026-11-20 19:00:00", "2026-11-20 19:00:01"):
        with app.app_context(), db.transaction():
            assert db.save_veto(room["id"], participant, pizza, now=now) is False
    assert veto_count(app) == 0
    with app.app_context(), db.transaction():
        assert db.save_veto(room["id"], participant, pizza, now="2026-11-20 18:59:59") is True
    assert veto_count(app) == 1
