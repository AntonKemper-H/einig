"""Tests for U5 – explain the joker on the rating card (specs/u5-joker-help.md).

Manual options only, so no test needs Google.
"""

import re

from typed_option import add_typed_option

FREE_LINES = [
    "Your joker takes this option out for the whole group (unless every option gets a joker).",
    "You have one joker per room. It can't be undone.",
    "To use it, swipe the card down.",
]
USED_LINES = [
    "You used your joker in this room.",
    "Your joker takes that option out for the whole group (unless every option gets a joker).",
]


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(browser, room_id, nickname):
    assert browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname}).status_code in (302, 303)


def voting_room(app, client, labels=("Pizza", "Tacos")):
    """A manual room by Anna (`client`), a guest Ben who joined before the start, voting started."""
    room_id = create_room(client)
    for label in labels:
        assert add_typed_option(client, room_id, label).status_code in (302, 303)
    guest = app.test_client()
    join(guest, room_id, "Ben")
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": ""}).status_code in (302, 303)
    return room_id, guest


def vote_page(client, room_id):
    response = client.get(f"/rooms/{room_id}/vote")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def shown_option(html):
    return re.findall(r'name="option_id" value="(\d+)"', html)[0]


def element(html, attribute):
    """The opening tag and the inner HTML of the first element with this attribute (no nesting of the same tag)."""
    open_tag = re.search(rf"<(\w+)\b[^>]*\b{re.escape(attribute)}\b[^>]*>", html)
    assert open_tag, f"no element with {attribute}"
    name = open_tag.group(1)
    end = html.index(f"</{name}>", open_tag.end())
    return open_tag.group(0), html[open_tag.end():end]


def card_line(html):
    start = html.index('<div class="card-line">')
    end = html.index("data-swipe-hint", start)
    return html[start:end]


def joker_help(html):
    tag, inner = element(html, "data-joker-help")
    summary = re.search(r"<summary\b[^>]*>(.*?)</summary>", inner, re.DOTALL)
    assert summary
    panel = inner[summary.end():]
    return tag, summary.group(1), panel


def use_joker(client, room_id):
    option_id = shown_option(vote_page(client, room_id))
    assert client.post(f"/rooms/{room_id}/veto", data={"option_id": option_id}).status_code in (302, 303)


# --- Tests -----------------------------------------------------------------

def test_the_counter_opens_a_joker_explanation(app, client):
    room_id, _ = voting_room(app, client)
    html = vote_page(client, room_id)
    assert "data-joker-help" in card_line(html)
    tag, summary, _ = joker_help(html)
    assert tag.startswith("<details")
    assert "Joker · 1 left" in summary
    assert re.search(r'<span[^>]*aria-hidden="true"[^>]*>\s*\?\s*</span>', summary)
    assert re.search(r'<span[^>]*class="visually-hidden"[^>]*>\s*What is the joker\?\s*</span>', summary)


def test_the_panel_explains_a_free_joker(app, client):
    room_id, _ = voting_room(app, client)
    _, _, panel = joker_help(vote_page(client, room_id))
    assert "menu-panel" in panel
    for line in FREE_LINES:
        assert line in panel


def test_after_using_the_joker_the_panel_says_so(app, client):
    room_id, _ = voting_room(app, client)
    use_joker(client, room_id)
    _, summary, panel = joker_help(vote_page(client, room_id))
    assert "Joker · used" in summary
    for line in USED_LINES:
        assert line in panel
    assert "To use it, swipe the card down." not in panel


def test_the_card_menu_is_still_there(app, client):
    room_id, _ = voting_room(app, client)
    line = card_line(vote_page(client, room_id))
    assert "data-card-menu" in line
    assert f'href="/rooms/{room_id}/lobby"' in line
    assert line.count("<details") == 2


def test_no_joker_help_on_the_overview(app, client):
    room_id, _ = voting_room(app, client)
    for _ in range(2):
        option_id = shown_option(vote_page(client, room_id))
        assert client.post(f"/rooms/{room_id}/vote", data={"option_id": option_id, "rating": "ok"}).status_code in (302, 303)
    html = vote_page(client, room_id)
    assert "You have rated all options." in html
    assert "data-joker-help" not in html


def test_the_help_only_tells_about_the_own_joker(app, client):
    room_id, guest = voting_room(app, client)
    use_joker(client, room_id)
    _, summary, panel = joker_help(vote_page(guest, room_id))
    assert "Joker · 1 left" in summary
    for line in FREE_LINES:
        assert line in panel
    assert "You used your joker" not in panel


def test_no_new_script_on_the_rating_page(app, client):
    room_id, _ = voting_room(app, client)
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', vote_page(client, room_id))
    assert sorted(set(scripts)) == sorted({src for src in scripts if src.endswith(("swipe.js", "register-sw.js"))})
