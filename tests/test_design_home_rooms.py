"""Tests for D1a – design of the home page, groups and the room page (specs/d1a-design-home-rooms.md, D21)."""

import re

import pytest

HOME_PARTS = {"groups": "My groups", "rooms": "My rooms", "create": "Create a room"}
OWN_IDEA_SUMMARY = "Add your own idea"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner", mode="manual", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def details_blocks(html, class_name):
    """Every <details> with this class: (opening tag, whole block). Blocks of this kind are not nested."""
    blocks = []
    for match in re.finditer(r"<details\b[^>]*>", html):
        tag = match.group(0)
        classes = re.search(r'class="([^"]*)"', tag)
        if classes and class_name in classes.group(1).split():
            end = html.index("</details>", match.end())
            # Skip nested <details> inside the block (e.g. Google place cards).
            inner_start = match.end()
            while html.count("<details", inner_start, end) > html.count("</details>", inner_start, end):
                end = html.index("</details>", end + 1)
            blocks.append((tag, html[match.start():end + len("</details>")]))
    return blocks


def home_part(html, key):
    """The <details class="home-part"> block whose summary has this part's heading."""
    heading = re.compile(rf"<summary\b.*?<h2[^>]*>\s*{re.escape(HOME_PARTS[key])}\s*</h2>.*?</summary>", re.DOTALL)
    found = [(tag, block) for tag, block in details_blocks(html, "home-part") if heading.search(block)]
    assert len(found) == 1, f"one home part for {HOME_PARTS[key]!r} expected, found {len(found)}"
    return found[0]


def is_open(tag):
    return re.search(r"\sopen(\s|>|=)", tag) is not None


# --- Home page -------------------------------------------------------------

def test_home_page_has_the_three_parts_as_details(client):
    create_room(client, "Sunday cinema")
    html = page(client, "/")
    for key in HOME_PARTS:
        home_part(html, key)
    _, rooms = home_part(html, "rooms")
    assert "Sunday cinema" in rooms
    _, create = home_part(html, "create")
    assert 'action="/rooms"' in create and 'method="post"' in create.lower()
    _, groups = home_part(html, "groups")
    assert 'href="/groups/new"' in groups


def test_home_parts_are_closed_on_a_normal_visit(client):
    html = page(client, "/")
    for key in HOME_PARTS:
        tag, _ = home_part(html, key)
        assert not is_open(tag), HOME_PARTS[key]


def test_rejected_create_opens_the_create_part_with_the_errors(client):
    response = client.post("/rooms", data={"title": "", "mode": "manual", "nickname": "Anna"})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    tag, create = home_part(html, "create")
    assert is_open(tag)
    assert 'role="alert"' in create
    for key in ("groups", "rooms"):
        other_tag, _ = home_part(html, key)
        assert not is_open(other_tag)


# --- Room page -------------------------------------------------------------

@pytest.mark.parametrize("mode", ["surprise", "nearby"])
def test_own_ideas_are_collapsed_in_rooms_with_suggested_places(client, mode):
    room_id = create_room(client, mode=mode)
    html = page(client, f"/rooms/{room_id}")
    blocks = details_blocks(html, "own-idea")
    assert len(blocks) == 1
    tag, block = blocks[0]
    assert not is_open(tag)
    assert re.search(rf"<summary[^>]*>\s*{OWN_IDEA_SUMMARY}\s*</summary>", block)
    assert f'action="/rooms/{room_id}/options"' in block
    assert f'action="/rooms/{room_id}/find"' in block


def test_own_ideas_are_not_collapsed_in_a_manual_room(client):
    room_id = create_room(client, mode="manual")
    html = page(client, f"/rooms/{room_id}")
    assert details_blocks(html, "own-idea") == []
    assert f'action="/rooms/{room_id}/options"' in html


def test_a_rejected_own_idea_opens_the_collapsed_part(client):
    room_id = create_room(client, mode="surprise")
    response = client.post(f"/rooms/{room_id}/options", data={"label": ""})
    assert response.status_code == 400
    tag, block = details_blocks(response.get_data(as_text=True), "own-idea")[0]
    assert is_open(tag)
    assert 'role="alert"' in block


def test_participants_section_is_open_for_the_creator_and_closed_for_guests(app, client):
    room_id = create_room(client)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"}).status_code in (302, 303)

    creator_tag, _ = details_blocks(page(client, f"/rooms/{room_id}"), "participants")[0]
    guest_tag, _ = details_blocks(page(guest, f"/rooms/{room_id}"), "participants")[0]
    assert is_open(creator_tag)
    assert not is_open(guest_tag)


def test_room_page_has_its_own_body_class(client):
    room_id = create_room(client)
    html = page(client, f"/rooms/{room_id}")
    body = re.search(r'<body class="([^"]*)"', html)
    assert body and "room-page" in body.group(1).split()
