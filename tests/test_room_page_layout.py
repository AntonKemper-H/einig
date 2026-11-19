"""Tests for B6 – Room page layout (specs/b6-room-page-layout.md)."""

import html as html_lib
import re

import pytest

from app import db
from app.db import get_db
from app.services import places

DETAILS_URL = "https://places.googleapis.com/v1/places/"
FAKE_KEY = "fake-key-for-tests-0123456789"
NAMES = {"place-a": "Pizza Roma", "place-b": "Sushi Bar", "place-c": "Café Lisboa"}
DONE_LINK = "I'm done – wait for the others"


# --- Fake Google -----------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.body = {} if body is None else body
        self.content = b""
        self.headers = {"Content-Type": "application/json"}
        self.text = str(self.body)

    def json(self):
        return self.body


class FakeGet:
    def __init__(self):
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append(url)
        place_id = url[len(DETAILS_URL):] if url.startswith(DETAILS_URL) else None
        if place_id in NAMES:
            return FakeResponse(body={
                "displayName": {"text": NAMES[place_id]},
                "rating": 4.5,
                "photos": [{"name": f"places/{place_id}/photos/photo-ref-1", "authorAttributions": []}],
            })
        return FakeResponse(status_code=404, body={"error": {}})

    def detail_calls(self):
        return [url for url in self.calls if url.startswith(DETAILS_URL) and not url.endswith("/media")]


@pytest.fixture(autouse=True)
def google(app, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGet()
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna", mode="manual"):
    response = client.post("/rooms", data={"title": "Dinner on Friday", "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(app, room_id, nickname):
    browser = app.test_client()
    assert browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname}).status_code in (302, 303)
    return browser


def add_option(client, room_id, label):
    assert client.post(f"/rooms/{room_id}/options", data={"label": label}).status_code in (302, 303)


def add_google_options(app, room_id, place_ids):
    with app.app_context():
        connection = get_db()
        for place_id in place_ids:
            connection.execute(
                "INSERT INTO options (room_id, source, place_id, category) VALUES (?, 'google', ?, 'restaurant')",
                (room_id, place_id),
            )
        connection.commit()


def option_id(app, room_id, key):
    with app.app_context():
        for row in db.get_options(room_id):
            if key in (row["label"], row["place_id"]):
                return row["id"]
    raise AssertionError(key)


def room_status(app, room_id):
    with app.app_context():
        return get_db().execute("SELECT status, deadline FROM rooms WHERE id = ?", (room_id,)).fetchone()


def page(client, room_id):
    response = client.get(f"/rooms/{room_id}")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def details_blocks(page_html):
    return re.findall(r"<details\b[^>]*>.*?</details>", page_html, flags=re.DOTALL)


def participants_section(page_html):
    for block in details_blocks(page_html):
        if re.search(r"<summary>\s*Participants \(", block):
            return block
    return None


def options_region(page_html):
    """From the "Options" heading to the end of the options list."""
    start = page_html.index("<h2>Options</h2>")
    return page_html[start:page_html.index("</ol>", start)]


def invite_url(room_id):
    return f"http://localhost/rooms/{room_id}"


@pytest.fixture
def room(app, client):
    """A collecting room: Anna (creator, `client`), Ben (`guest`), manual options Pizza and Tacos."""
    room_id = create_room(client)
    guest = join(app, room_id, "Ben")
    add_option(client, room_id, "Pizza")
    add_option(guest, room_id, "Tacos")
    return {"id": room_id, "guest": guest}


# --- Participants ----------------------------------------------------------

def test_participants_section_is_collapsible_with_counts(client, room):
    section = participants_section(page(client, room["id"]))
    assert section, "participants <details> missing"
    assert re.search(r"<summary>\s*Participants \(2 · 0 done\)\s*</summary>", section)
    assert "Anna" in section and "(creator)" in section
    assert "Ben" in section


def test_participants_section_counts_and_marks_who_is_done(app, client, room):
    with app.app_context():
        connection = get_db()
        connection.execute(
            "UPDATE participants SET has_finished = 1 WHERE room_id = ? AND nickname = 'Ben'", (room["id"],)
        )
        connection.commit()
    section = participants_section(page(client, room["id"]))
    assert re.search(r"<summary>\s*Participants \(2 · 1 done\)\s*</summary>", section)
    assert re.search(r"Ben\s*– done", section)
    assert not re.search(r"Anna[^<]*– done", section)


def test_start_form_only_in_the_creators_participants_section(client, room):
    start_action = f'action="/rooms/{room["id"]}/start"'
    assert start_action in participants_section(page(client, room["id"]))
    guest_page = page(room["guest"], room["id"])
    assert start_action not in guest_page


def test_start_form_has_the_time_limit_choice(app, client, room):
    section = participants_section(page(client, room["id"]))
    form = re.search(rf'<form[^>]*action="/rooms/{room["id"]}/start".*?</form>', section, flags=re.DOTALL)
    assert form
    select = re.search(r'<select[^>]*name="time_limit".*?</select>', form.group(0), flags=re.DOTALL)
    assert select, "time_limit choice missing"
    assert re.findall(r'<option[^>]*value="([^"]*)"', select.group(0)) == ["", "15", "30", "60"]
    assert client.post(f"/rooms/{room['id']}/start", data={"time_limit": "30"}).status_code == 303
    row = room_status(app, room["id"])
    assert row["status"] == "voting"
    assert row["deadline"] is not None


def test_starting_from_the_room_page(app, client):
    room_id = create_room(client)
    add_option(client, room_id, "Pizza")
    rejected = client.post(f"/rooms/{room_id}/start")
    assert rejected.status_code == 400
    assert "Add at least 2 options before starting the voting." in rejected.get_data(as_text=True)
    add_option(client, room_id, "Tacos")
    response = client.post(f"/rooms/{room_id}/start")
    assert response.status_code == 303
    assert room_status(app, room_id)["status"] == "voting"


def test_refresh_link_and_no_meta_refresh(client, room):
    page_html = page(client, room["id"])
    section = participants_section(page_html)
    assert re.search(rf'<a[^>]*href="/rooms/{room["id"]}"[^>]*>\s*Refresh\s*</a>', section)
    assert 'http-equiv="refresh"' not in page_html


def test_done_link_to_the_lobby(client, room):
    page_html = html_lib.unescape(page(client, room["id"]))
    assert re.search(rf'<a[^>]*href="/rooms/{room["id"]}/lobby"[^>]*>\s*{re.escape(DONE_LINK)}\s*</a>', page_html)
    assert "to see who has joined" not in page_html


# --- Options ---------------------------------------------------------------

def test_google_option_is_collapsible_manual_option_is_not(app, client, room):
    add_google_options(app, room["id"], ["place-a"])
    page_html = page(client, room["id"])
    google_blocks = [block for block in details_blocks(page_html) if "Pizza Roma" in block]
    assert len(google_blocks) == 1
    block = google_blocks[0]
    assert re.search(r"<summary>\s*Pizza Roma\s*</summary>", block)
    assert '/photo/places/place-a/photos/photo-ref-1' in block
    assert "4.5 ★" in block
    for block in details_blocks(page_html):
        assert "Tacos" not in block


def test_google_option_without_details_is_the_plain_card(app, client, room):
    add_google_options(app, room["id"], ["place-x", "place-y"])  # the fake has no details for these
    page_html = page(client, room["id"])
    assert page_html.count("Place from Google Maps") == 2
    assert page_html.count("Details are not available right now.") == 2
    for block in details_blocks(page_html):
        assert "Place from Google Maps" not in block


def test_been_there_and_delete_are_outside_the_place_details(app, client):
    room_id = create_room(client, mode="surprise")
    add_google_options(app, room_id, ["place-a"])
    page_html = page(client, room_id)
    place_block = next(block for block in details_blocks(page_html) if "Pizza Roma" in block)
    assert "Been there" not in place_block and "/been-there" not in place_block
    assert "Delete" not in place_block and "/delete" not in place_block
    place_option = option_id(app, room_id, "place-a")
    assert f'action="/rooms/{room_id}/options/{place_option}/been-there"' in page_html
    delete_action = f'action="/rooms/{room_id}/options/{place_option}/delete"'
    assert delete_action in page_html
    response = client.post(f"/rooms/{room_id}/options/{place_option}/delete")
    assert response.status_code in (302, 303)
    with client.application.app_context():
        assert all(row["id"] != place_option for row in db.get_options(room_id))


def test_place_details_calls_stay_one_per_google_option(app, client, room, google):
    add_google_options(app, room["id"], ["place-a", "place-b", "place-c"])
    google.calls.clear()
    page(client, room["id"])
    assert sorted(google.detail_calls()) == sorted(DETAILS_URL + place_id for place_id in NAMES)


# --- Order of the page -----------------------------------------------------

def test_setup_line_first_setup_form_after_the_options(app, client, room):
    response = client.post(f"/rooms/{room['id']}/setup", data={"kind": "food.restaurant", "options_per_person": ""})
    assert response.status_code in (302, 303)
    page_html = page(client, room["id"])
    setup_line = page_html.index("Restaurant")
    participants = page_html.index("Participants (")
    options_end = page_html.index("</ol>", page_html.index("<h2>Options</h2>"))
    setup_form = page_html.index(f'action="/rooms/{room["id"]}/setup"')
    assert setup_line < participants < options_end < setup_form


def test_invite_and_qr_code_come_after_options_and_add_form(client, room):
    page_html = page(client, room["id"])
    add_form = page_html.index(f'action="/rooms/{room["id"]}/options"')
    last_option = page_html.index("Tacos")
    invite_field = page_html.index('aria-label="Invite link"')
    qr_code = page_html.index("Scan to join this room.")
    assert last_option < add_form < invite_field
    assert add_form < qr_code


def test_invite_url_in_one_block_at_the_end(client, room):
    page_html = page(client, room["id"])
    url = invite_url(room["id"])
    positions = [match.start() for match in re.finditer(re.escape(url) + r'(?=["<])', page_html)]
    assert len(positions) == 3, positions  # field value, link href, link text
    assert positions[0] > page_html.index("</ol>")
    between = page_html[positions[0]:positions[-1]]
    for closing in ("</section>", "</div>", "</footer>", "</details>", "</article>"):
        assert closing not in between, closing


# --- Unchanged behaviour ---------------------------------------------------

def test_visitor_and_closed_room_are_unchanged(app, client, room):
    visitor = app.test_client()
    visitor_page = page(visitor, room["id"])
    assert "Join this room" in visitor_page
    assert "Participants (" not in visitor_page
    assert "Pizza" not in visitor_page
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = 'closed' WHERE id = ?", (room["id"],))
        connection.commit()
    assert "This room is closed. You can no longer join." in page(app.test_client(), room["id"])


def test_options_list_shows_no_author_and_no_votes(client, room):
    region = options_region(page(client, room["id"]))
    assert "Anna" not in region
    assert "Ben" not in region
    assert "Your rating" not in region
