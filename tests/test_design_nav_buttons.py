"""Plain text links at the end of a page become buttons (D21 design follow-up after the phone test)."""

import re
from pathlib import Path

from typed_option import add_typed_option

APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"


def create_room(client, title="Dinner"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": "Anna"})
    assert response.status_code in (302, 303)
    room_id = response.headers["Location"].rsplit("/rooms/", 1)[1]
    add_typed_option(client, room_id, "Pizza")
    add_typed_option(client, room_id, "Tacos")
    return room_id


def closed_room(client):
    room_id = create_room(client, "Weekend")
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": ""}).status_code in (302, 303)
    assert client.post(f"/rooms/{room_id}/close").status_code in (302, 303)
    return room_id


def html_of(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


def link_classes(html, href, text):
    match = re.search(rf'<a\b([^>]*)href="{re.escape(href)}"([^>]*)>\s*{re.escape(text)}\s*</a>', html)
    assert match, f"no link {text!r} to {href}"
    classes = re.search(r'class="([^"]*)"', match.group(1) + match.group(2))
    return classes.group(1).split() if classes else []


def test_back_links_at_the_end_of_pages_are_buttons(client):
    room_id = create_room(client)
    assert "nav-button" in link_classes(html_of(client, f"/rooms/{room_id}/lobby"), f"/rooms/{room_id}", "Back to the room")
    closed = closed_room(client)
    assert "nav-button" in link_classes(html_of(client, f"/rooms/{closed}/result"), f"/rooms/{closed}/lobby", "Back to the lobby")
    vote_page = html_of(client, f"/rooms/{closed}/vote")
    assert "nav-button" in link_classes(vote_page, f"/rooms/{closed}/result", "See the result")
    assert "nav-button" in link_classes(vote_page, f"/rooms/{closed}/lobby", "Back to the lobby")


def test_cancel_on_the_confirmation_pages_is_a_button(client):
    room_id = create_room(client)
    assert "nav-button" in link_classes(html_of(client, f"/rooms/{room_id}/delete"), f"/rooms/{room_id}", "Cancel")
    assert "nav-button" in link_classes(html_of(client, f"/rooms/{room_id}/forget"), "/", "Cancel")


def test_refresh_in_the_participants_card_is_a_small_button(client):
    room_id = create_room(client)
    assert "inline-button" in link_classes(html_of(client, f"/rooms/{room_id}"), f"/rooms/{room_id}", "Refresh")


def test_the_button_classes_are_styled():
    css = re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.DOTALL)
    assert re.search(r"\.nav-button\b[^{]*\{", css)
    assert re.search(r"\.inline-button\b[^{]*\{", css)
