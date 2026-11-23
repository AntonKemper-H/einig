"""Tests for U2 – choose what first (specs/u2-what-first.md).

The create form gets an optional activity; with one, the room setup is saved right away and
an empty title becomes the activity's name. In a Nearby or Surprise room the search form
only appears once a setup is saved. Nothing here calls Google.
"""

import re

from app.db import get_db

BAR = "drinks.bar"
TITLE_MESSAGE = "Please enter a title."
KIND_MESSAGE = "Please choose an activity."


def create(client, **fields):
    data = {"title": "", "mode": "manual", "nickname": "Anna", **fields}
    return client.post("/rooms", data=data)


def room_id_of(response):
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def room_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()


def setup_row(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT * FROM room_setups WHERE room_id = ?", (room_id,)).fetchone()


def room_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS n FROM rooms").fetchone()["n"]


def room_html(client, room_id):
    return client.get(f"/rooms/{room_id}").get_data(as_text=True)


def test_the_create_form_has_the_activity_and_three_mode_tiles(client):
    html = client.get("/").get_data(as_text=True)
    assert 'name="kind"' in html
    assert f'value="{BAR}"' in html
    for mode in ("manual", "nearby", "surprise"):
        assert f'name="mode" value="{mode}"' in html
    assert html.count('class="mode-tile"') == 3


def test_an_activity_without_a_title_names_the_room_and_saves_the_setup(app, client):
    room_id = room_id_of(create(client, kind=BAR))
    assert room_row(app, room_id)["title"] == "Bar"
    setup = setup_row(app, room_id)
    assert (setup["activity"], setup["kind"]) == ("drinks", "bar")
    assert setup["options_per_person"] is None
    assert setup["hide_ideas"] == 1
    assert setup["reveal_places"] == 1
    assert "Activity: Drinks &amp; café – Bar" in room_html(client, room_id)


def test_an_own_title_is_kept_when_an_activity_is_chosen(app, client):
    room_id = room_id_of(create(client, title="Friday drinks", kind=BAR))
    assert room_row(app, room_id)["title"] == "Friday drinks"
    assert setup_row(app, room_id) is not None


def test_no_activity_and_no_title_is_still_rejected(app, client):
    response = create(client)
    assert response.status_code == 400
    assert TITLE_MESSAGE in response.get_data(as_text=True)
    assert room_count(app) == 0


def test_an_unknown_activity_is_rejected_and_nothing_is_saved(app, client):
    response = create(client, title="Dinner", kind="drinks.unicorn")
    assert response.status_code == 400
    assert KIND_MESSAGE in response.get_data(as_text=True)
    assert room_count(app) == 0


def test_a_group_member_can_plan_an_activity_without_a_title(app, client):
    response = client.post("/groups", data={"name": "Friday friends", "nickname": "Anna"})
    group_id = response.headers["Location"].rsplit("/groups/", 1)[1]
    planned = client.post(f"/groups/{group_id}/rooms", data={"title": "", "mode": "manual", "kind": BAR})
    room_id = room_id_of(planned)
    assert room_row(app, room_id)["title"] == "Bar"
    assert setup_row(app, room_id)["kind"] == "bar"


def has_search_form(html, room_id, route):
    return f'action="/rooms/{room_id}/{route}"' in html


def test_a_nearby_room_shows_the_search_form_only_after_the_setup(client):
    room_id = room_id_of(create(client, title="Lunch", mode="nearby"))
    html = room_html(client, room_id)
    assert not has_search_form(html, room_id, "suggest")
    assert 'name="category"' not in html
    assert client.post(f"/rooms/{room_id}/setup", data={"kind": BAR, "options_per_person": ""}).status_code == 303
    html = room_html(client, room_id)
    assert has_search_form(html, room_id, "suggest")
    assert 'name="category"' not in html


def test_a_surprise_room_shows_the_surprise_form_only_after_the_setup(client):
    room_id = room_id_of(create(client, title="Night out", mode="surprise"))
    html = room_html(client, room_id)
    assert not has_search_form(html, room_id, "surprise")
    assert 'name="category"' not in html
    assert client.post(f"/rooms/{room_id}/setup", data={"kind": BAR, "options_per_person": ""}).status_code == 303
    assert has_search_form(room_html(client, room_id), room_id, "surprise")


def test_a_room_created_with_an_activity_shows_the_search_form_at_once(client):
    room_id = room_id_of(create(client, mode="surprise", kind=BAR))
    html = room_html(client, room_id)
    assert has_search_form(html, room_id, "surprise")
    assert re.search(r"Searching for: Bar", html)
