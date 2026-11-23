"""Tests for D1b – design of the rating card, lobby and result (specs/d1b-design-vote-result.md, D21).

The looks themselves are checked by eye (screenshots in the PR). These tests pin what can be checked
in the HTML, the stylesheet and swipe.js: the hint row, the joker stamp, the menu button, the lobby
ring and pills, the result bars and tiles, and that nothing outside the D1b section of app.css is touched.
"""

import re
from pathlib import Path

import pytest
from typed_option import add_typed_option

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "app" / "static" / "css" / "app.css"
SWIPE_JS = ROOT / "app" / "static" / "js" / "swipe.js"
D1B_MARKER = "/* D1b vote, lobby, result */"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def add_options(client, room_id, labels):
    for label in labels:
        assert add_typed_option(client, room_id, label).status_code in (302, 303)


def join(guest, room_id, nickname):
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": nickname}).status_code in (302, 303)


def start(client, room_id):
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": ""}).status_code in (302, 303)


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def voting_room(client, labels=("Pizza", "Tacos")):
    room_id = create_room(client)
    add_options(client, room_id, labels)
    start(client, room_id)
    return room_id


def option_ids(html):
    return re.findall(r'name="option_id" value="(\d+)"', html)


def element(html, attribute):
    """The opening tag and the inner HTML of the first element that carries this attribute."""
    open_tag = re.search(rf"<(\w+)\b[^>]*\b{re.escape(attribute)}\b[^>]*>", html)
    assert open_tag, f"no element with {attribute}"
    name = open_tag.group(1)
    end = html.index(f"</{name}>", open_tag.end())
    return open_tag.group(0), html[open_tag.end():end]


def text_of(inner):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()


def set_finished(app, room_id, nickname):
    from app.db import get_db

    with app.app_context():
        db = get_db()
        db.execute(
            "UPDATE participants SET has_finished = 1 WHERE room_id = ? AND nickname = ?",
            (room_id, nickname),
        )
        db.commit()


# --- Rating card: hint row and joker stamp ---------------------------------

def test_the_swipe_hints_sit_under_the_card_as_hidden_from_screen_readers_text(client):
    # U4 (D27, changed with the team's OK): D1b's text row is replaced by the icon row,
    # which holds the real buttons and sits in the card (swipe.js looks for them there).
    room_id = voting_room(client)
    html = page(client, f"/rooms/{room_id}/vote")
    assert "data-swipe-legend" not in html
    card_start = html.index("<article data-swipe-card")
    card_end = html.index("</article>", card_start)
    row_start = html.index("data-rating-row")
    assert card_start < row_start < card_end
    _, inner = element(html, "data-rating-row")
    for icon in ("✕", "🤷", "♥", "🚫"):
        assert icon in inner
    assert inner.count('name="rating"') == 3


def test_the_joker_hint_is_left_out_once_the_joker_is_used(client):
    # U4 (D27, changed with the team's OK): the joker button leaves the icon row once used.
    room_id = voting_room(client)
    first = option_ids(page(client, f"/rooms/{room_id}/vote"))[0]
    assert client.post(f"/rooms/{room_id}/veto", data={"option_id": first}).status_code in (302, 303)
    html = page(client, f"/rooms/{room_id}/vote")
    _, inner = element(html, "data-rating-row")
    assert "🚫" not in inner
    assert "✕" in inner


def test_no_hint_row_on_the_overview_after_all_options_are_rated(app, client):
    room_id = voting_room(client)
    join(app.test_client(), room_id, "Idle")  # never rates, so the room stays open (B5)
    for _ in range(2):  # one card at a time: rate the shown card, then the next one
        shown = option_ids(page(client, f"/rooms/{room_id}/vote"))[0]
        assert client.post(f"/rooms/{room_id}/vote", data={"option_id": shown, "rating": "yes"}).status_code in (302, 303)
    html = page(client, f"/rooms/{room_id}/vote")
    assert "You have rated all options." in html
    assert "data-swipe-legend" not in html


def test_the_old_screen_reader_hint_stays_for_the_swipe_script(client):
    """C11/D16's hint element is pinned by reviewed tests; D1b only hides it visually."""
    room_id = voting_room(client)
    html = page(client, f"/rooms/{room_id}/vote")
    assert "Swipe right: Rather yes · up: Fine with me · left: Rather not" in html


def test_a_swipe_down_shows_a_joker_stamp_and_the_ratings_are_unchanged():
    css = APP_CSS.read_text()
    assert re.search(r'\[data-swipe-choice="joker"\]::before\s*\{[^}]*content:\s*"Joker\?"', css)
    js = SWIPE_JS.read_text()
    # The distances and the three rating mappings are exactly as in C11/D20.
    assert "var SWIPE_DISTANCE = 110;" in js
    assert 'if (dx >= SWIPE_DISTANCE) { return "yes"; }' in js
    assert 'if (dx <= -SWIPE_DISTANCE) { return "no"; }' in js
    assert re.search(r'dy <= -SWIPE_DISTANCE\) \{\s*return "ok";', js)
    assert "buttons[choice].click()" in js
    # The joker is still only asked about, never pressed by the swipe itself.
    assert "question.hidden = false;" in js
    # The stamp for "down" is only a label: choiceFor() still never returns "joker".
    choice_for = js[js.index("function choiceFor"):js.index("// Move and tilt")]
    assert 'return "joker"' not in choice_for


# --- Rating card: menu button ----------------------------------------------

def test_the_card_menu_is_a_round_button_with_a_name_and_keeps_its_links(client):
    room_id = voting_room(client)
    html = page(client, f"/rooms/{room_id}/vote")
    _, menu = element(html, "data-card-menu")
    summary = re.search(r"<summary\b([^>]*)>(.*?)</summary>", menu, flags=re.DOTALL)
    assert summary
    assert "menu-button" in summary.group(1)
    assert 'aria-label="Menu"' in summary.group(1)
    assert "⋯" in summary.group(2)
    assert f'href="/rooms/{room_id}/lobby"' in menu
    assert f'action="/rooms/{room_id}/close"' in menu  # the creator's close button (B3)


# --- Lobby -----------------------------------------------------------------

@pytest.fixture
def lobby_room(app, client):
    room_id = create_room(client, nickname="Anna")
    add_options(client, room_id, ["Pizza", "Tacos"])
    for name in ("Ben", "Carla"):
        join(app.test_client(), room_id, name)
    return room_id


def test_lobby_shows_a_progress_ring_with_the_count_as_text(app, client, lobby_room):
    for percent, finished in (("0%", []), ("33%", ["Ben"]), ("100%", ["Ben", "Anna", "Carla"])):
        for name in finished:
            set_finished(app, lobby_room, name)
        html = page(client, f"/rooms/{lobby_room}/lobby")
        tag, inner = element(html, "data-progress-ring")
        assert f"--progress: {percent}" in tag
        assert f"{len(finished)} of 3 done" in text_of(inner)


def test_lobby_shows_a_pill_per_participant(app, client, lobby_room):
    set_finished(app, lobby_room, "Ben")
    html = page(client, f"/rooms/{lobby_room}/lobby")
    items = {}
    for name in ("Ben", "Carla"):
        items[name] = next(item for item in html.split("<li") if re.match(rf"[^>]*>\s*{name}\b", item))
    assert re.search(r'class="pill[^"]*"[^>]*>\s*done\s*<', items["Ben"])
    assert re.search(r'class="pill[^"]*"[^>]*>\s*Still adding\s*<', items["Carla"])
    assert "Still adding" not in items["Ben"] and "done" not in items["Carla"]


def test_lobby_pill_says_still_rating_while_the_room_is_voting(app, client, lobby_room):
    start(client, lobby_room)
    html = page(client, f"/rooms/{lobby_room}/lobby")
    assert "Still rating" in html
    assert "Still adding" not in html


def test_lobby_has_a_big_rate_button_while_voting_and_keeps_the_refresh(client, lobby_room):
    start(client, lobby_room)
    html = page(client, f"/rooms/{lobby_room}/lobby")
    assert re.search(rf'<a\b[^>]*href="/rooms/{lobby_room}/vote"[^>]*role="button"[^>]*>\s*Rate the options\s*</a>', html)
    assert f'<meta http-equiv="refresh" content="4; url=/rooms/{lobby_room}/lobby">' in html


def test_lobby_keeps_the_waiting_text_for_guests_and_the_refresh(app, lobby_room):
    guest = app.test_client()
    join(guest, lobby_room, "Dora")
    html = page(guest, f"/rooms/{lobby_room}/lobby")
    assert "Waiting for the creator to start the voting." in html
    assert f'<meta http-equiv="refresh" content="4; url=/rooms/{lobby_room}/lobby">' in html


# --- Result ----------------------------------------------------------------

@pytest.fixture
def closed_room(app, client):
    """Pizza: 2 yes. Tacos: 1 fine, 1 yes. Sushi: 2 not. The cards come in a random order per person,
    so the ratings are given by label, through the database ids."""
    from app.db import get_db

    room_id = voting_room(client, ("Pizza", "Tacos", "Sushi"))
    with app.app_context():
        rows = get_db().execute("SELECT id, label FROM options WHERE room_id = ?", (room_id,)).fetchall()
    ids = {row["label"]: str(row["id"]) for row in rows}
    guest = app.test_client()
    join(guest, room_id, "Ben")
    for browser, ratings in ((client, {"Pizza": "yes", "Tacos": "ok", "Sushi": "no"}),
                             (guest, {"Pizza": "yes", "Tacos": "yes", "Sushi": "no"})):
        for label, rating in ratings.items():
            browser.post(f"/rooms/{room_id}/vote", data={"option_id": ids[label], "rating": rating})
    assert client.post(f"/rooms/{room_id}/close").status_code in (302, 303)
    return room_id


def test_result_shows_one_bar_per_option_with_the_counts_as_text(client, closed_room):
    html = page(client, f"/rooms/{closed_room}/result")
    bars = re.findall(r'<div\b[^>]*class="[^"]*\brating-bar\b[^"]*"[^>]*>', html)
    assert len(bars) == 3
    for tag in bars:
        assert 'role="img"' in tag and "aria-label=" in tag
    # The counts stay as text next to the bars (colour is never the only information).
    rated = html.split("How the options were rated", 1)[1]
    assert re.search(r"2× Rather yes", rated)
    assert re.search(r"2× Rather not", rated)


def test_result_winner_has_a_pill_and_the_two_share_tiles(client, closed_room):
    html = page(client, f"/rooms/{closed_room}/result")
    assert len(re.findall(r'class="pill pill-winner"', html)) == 1
    assert "Winner" in html
    tiles = re.findall(r'class="[^"]*\bshare-tile\b[^"]*"', html)
    assert len(tiles) == 2
    assert "Share in WhatsApp" in html and "Add to calendar" in html


def test_result_without_a_winner_has_no_winner_pill(client):
    room_id = voting_room(client)
    assert client.post(f"/rooms/{room_id}/close").status_code in (302, 303)
    html = page(client, f"/rooms/{room_id}/result")
    assert "No winner: nobody rated any option." in html
    assert "pill-winner" not in html


# --- Stylesheet ------------------------------------------------------------

# U4 (D27, changed with the team's OK): "swipe-legend" is gone with D1b's hint row.
D1B_ONLY_SELECTORS = ("progress-ring", "rating-bar", "share-tile", "menu-button", "pill-winner")


def test_d1b_styles_are_only_in_the_d1b_section():
    css = APP_CSS.read_text()
    assert D1B_MARKER in css
    before, after = css.split(D1B_MARKER, 1)
    for name in D1B_ONLY_SELECTORS:
        assert name not in before, f"{name} is styled outside the D1b section"
        assert name in after, f"{name} has no style in the D1b section"
