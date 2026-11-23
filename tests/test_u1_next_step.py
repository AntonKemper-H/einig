"""Tests for U1 – one next step at a time (specs/u1-next-step.md)."""

import re

from app.db import get_db
from typed_option import add_typed_option


def create_room(client, **fields):
    data = {"title": "Dinner", "mode": "manual", "nickname": "Anna", **fields}
    response = client.post("/rooms", data=data)
    assert response.status_code in (302, 303)
    room_id = response.headers["Location"].rsplit("/rooms/", 1)[1]
    add_typed_option(client, room_id, "Pizza")
    add_typed_option(client, room_id, "Tacos")
    return room_id


def join(app, room_id, nickname="Ben"):
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": nickname}).status_code in (302, 303)
    return guest


def page(client, room_id):
    return client.get(f"/rooms/{room_id}").get_data(as_text=True)


def set_status(app, room_id, status):
    with app.app_context():
        db = get_db()
        db.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        db.commit()


def finish(app, room_id, nickname):
    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE participants SET has_finished = 1 WHERE room_id = ? AND nickname = ?",
            (room_id, nickname),
        )
        db.commit()


def test_the_creator_sees_start_voting_at_the_top_while_collecting(client):
    room_id = create_room(client)
    html = page(client, room_id)
    assert re.search(r'<a[^>]*href="#start-voting"[^>]*>\s*Start voting\s*</a>', html)
    assert 'id="start-voting"' in html
    assert html.index("Start voting") < html.index("<h2>Options</h2>")


def test_a_guest_waits_for_the_start_while_collecting(app, client):
    room_id = create_room(client)
    html = page(join(app, room_id), room_id)
    assert "Waiting for the creator to start" in html
    assert 'href="#start-voting"' not in html


def test_while_voting_a_participant_sees_rate_now(app, client):
    room_id = create_room(client)
    guest = join(app, room_id)
    assert client.post(f"/rooms/{room_id}/start").status_code in (302, 303)
    html = page(guest, room_id)
    assert re.search(rf'<a[^>]*href="/rooms/{room_id}/vote"[^>]*>\s*Rate now\s*</a>', html)


def test_once_done_a_participant_waits_for_the_others(app, client):
    room_id = create_room(client)
    guest = join(app, room_id)
    client.post(f"/rooms/{room_id}/start")
    finish(app, room_id, "Ben")
    html = page(guest, room_id)
    assert "Waiting for 1 more" in html
    assert "Rate now" not in html


def test_a_closed_room_shows_see_the_result(app, client):
    room_id = create_room(client)
    set_status(app, room_id, "closed")
    html = page(client, room_id)
    assert re.search(rf'<a[^>]*href="/rooms/{room_id}/result"[^>]*>\s*See the result\s*</a>', html)


def test_a_visitor_sees_no_main_step(app, client):
    room_id = create_room(client)
    html = page(app.test_client(), room_id)
    for text in ("Start voting", "Rate now", "See the result", "Waiting for"):
        assert text not in html


def test_the_rating_page_counts_the_joker(app, client):
    room_id = create_room(client)
    client.post(f"/rooms/{room_id}/start")
    html = client.get(f"/rooms/{room_id}/vote").get_data(as_text=True)
    assert "Joker · 1 left" in html
    option_id = re.search(r'name="option_id" value="(\d+)"', html).group(1)
    assert client.post(f"/rooms/{room_id}/veto", data={"option_id": option_id}).status_code in (302, 303)
    html = client.get(f"/rooms/{room_id}/vote").get_data(as_text=True)
    assert "Joker · used" in html
    assert "Joker · 1 left" not in html


def make_group_room(client):
    response = client.post("/groups", data={"name": "Friday friends", "nickname": "Anna"})
    group_id = response.headers["Location"].rsplit("/groups/", 1)[1]
    planned = client.post(f"/groups/{group_id}/rooms", data={"title": "Dinner", "mode": "nearby"})
    room_id = planned.headers["Location"].rsplit("/rooms/", 1)[1]
    return group_id, room_id


def test_a_group_member_can_go_again_with_the_same_people(app, client):
    group_id, room_id = make_group_room(client)
    set_status(app, room_id, "closed")
    html = client.get(f"/rooms/{room_id}/result").get_data(as_text=True)
    assert f'action="/groups/{group_id}/rooms"' in html
    assert "Again with the same people" in html
    again = client.post(f"/groups/{group_id}/rooms", data={"title": "Dinner", "mode": "nearby"})
    assert again.status_code in (302, 303)
    with app.app_context():
        rows = get_db().execute(
            "SELECT r.title, r.mode FROM rooms r JOIN group_rooms g ON g.room_id = r.id WHERE g.group_id = ?",
            (group_id,),
        ).fetchall()
    assert len(rows) == 2
    assert {(row["title"], row["mode"]) for row in rows} == {("Dinner", "nearby")}


def test_a_room_without_a_group_links_to_create_a_new_room(app, client):
    room_id = create_room(client)
    set_status(app, room_id, "closed")
    html = client.get(f"/rooms/{room_id}/result").get_data(as_text=True)
    assert "Again with the same people" not in html
    assert re.search(r'<a[^>]*href="/"[^>]*>\s*Create a new room\s*</a>', html)
