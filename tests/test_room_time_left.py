"""The room page shows the time left while voting (bug found by Mika on 2026-11-23).

B5 shows "Time left: N min" in the lobby and on the rating page; the room page, where people
also land during the voting, did not show it, so a set time limit looked as if it had gone.
"""

import re

from typed_option import add_typed_option

TIME_LEFT = re.compile(r"Time left: \d+ min")


def create_room(client):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": "Anna"})
    assert response.status_code in (302, 303)
    room_id = response.headers["Location"].rsplit("/rooms/", 1)[1]
    add_typed_option(client, room_id, "Pizza")
    add_typed_option(client, room_id, "Tacos")
    return room_id


def room_page(client, room_id):
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_the_room_page_shows_the_time_left_while_voting(app, client):
    room_id = create_room(client)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"}).status_code in (302, 303)
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": "15"}).status_code in (302, 303)
    for browser in (client, guest):
        assert TIME_LEFT.search(room_page(browser, room_id))


def test_no_time_left_on_the_room_page_without_a_limit(client):
    room_id = create_room(client)
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": ""}).status_code in (302, 303)
    assert "Time left" not in room_page(client, room_id)


def test_no_time_left_on_the_room_page_while_collecting(client):
    assert "Time left" not in room_page(client, create_room(client))
