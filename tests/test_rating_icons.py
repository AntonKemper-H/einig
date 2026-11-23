"""Tests for U4 – rating buttons as icons, a "?" for help, labels on the first card
(specs/u4-rating-icons.md, decision D27).

Manual options only, so no test needs Google.
"""

import re
from pathlib import Path

from typed_option import add_typed_option

from app import create_app
from app.services import scoring

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "app" / "static" / "css" / "app.css"

ICONS = {"no": "✕", "ok": "🤷", "yes": "♥"}
JOKER_ICON = "🚫"
JOKER_TEXT = "Use my joker on this option (cannot be undone)"
FIRST_CARD_HINT = "Tap a button or swipe the card."
HELP_LABEL = 'aria-label="How rating works"'


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Anna"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def voting_room(app, client, labels=("Pizza", "Tacos", "Sushi")):
    """A manual room by Anna (`client`) with these options, voting started, plus an idle guest
    who never rates, so the room stays open (B5)."""
    room_id = create_room(client)
    for label in labels:
        assert add_typed_option(client, room_id, label).status_code in (302, 303)
    idle = app.test_client()
    assert idle.post(f"/rooms/{room_id}/join", data={"nickname": "Idle"}).status_code in (302, 303)
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": ""}).status_code in (302, 303)
    return room_id


def vote_page(client, room_id):
    response = client.get(f"/rooms/{room_id}/vote")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def shown_option(html):
    return re.findall(r'name="option_id" value="(\d+)"', html)[0]


def rate_shown(client, room_id, rating="yes"):
    option_id = shown_option(vote_page(client, room_id))
    response = client.post(f"/rooms/{room_id}/vote", data={"option_id": option_id, "rating": rating})
    assert response.status_code in (302, 303)
    return option_id


def element(html, attribute):
    """The opening tag and the inner HTML of the first element that carries this attribute."""
    open_tag = re.search(rf"<(\w+)\b[^>]*\b{re.escape(attribute)}\b[^>]*>", html)
    assert open_tag, f"no element with {attribute}"
    name = open_tag.group(1)
    end = html.index(f"</{name}>", open_tag.end())
    return open_tag.group(0), html[open_tag.end():end]


def card_html(html):
    start = html.index("<article data-swipe-card")
    return html[start : html.index("</article>", start)]


def button_tags(html):
    """{"no"/"ok"/"yes"/"joker": the whole <button ...>...</button>} in the icon row."""
    _, row = element(html, "data-rating-row")
    buttons = {}
    for tag in re.findall(r"<button\b.*?</button>", row, re.DOTALL):
        value = re.search(r'value="(\w+)"', tag)
        buttons["joker" if 'name="rating"' not in tag else value.group(1)] = tag
    return buttons


def css_rules():
    text = re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.S)
    return [(selector.strip(), rule.strip()) for selector, rule in re.findall(r"([^{}]+)\{([^{}]*)\}", text)]


def votes(app, room_id):
    with app.app_context():
        from app.db import get_db

        return get_db().execute("SELECT rating FROM votes WHERE option_id IN (SELECT id FROM options WHERE room_id = ?)", (room_id,)).fetchall()


def vetoes(app, room_id):
    with app.app_context():
        from app.db import get_db

        return get_db().execute("SELECT * FROM vetoes WHERE room_id = ?", (room_id,)).fetchall()


# --- The icon row ----------------------------------------------------------

def test_the_card_has_one_icon_row_with_four_buttons(app, client):
    room_id = voting_room(app, client)
    html = vote_page(client, room_id)
    card = card_html(html)
    assert "data-rating-row" in card
    buttons = button_tags(html)
    assert set(buttons) == {"no", "ok", "yes", "joker"}
    for value, icon in ICONS.items():
        assert re.search(rf'<span[^>]*aria-hidden="true"[^>]*>\s*{icon}\s*</span>', buttons[value])
    assert re.search(rf'<span[^>]*aria-hidden="true"[^>]*>\s*{JOKER_ICON}\s*</span>', buttons["joker"])
    assert JOKER_TEXT in buttons["joker"]


def test_the_forms_and_fields_are_unchanged(app, client):
    room_id = voting_room(app, client)
    html = vote_page(client, room_id)
    card = card_html(html)
    assert f'action="/rooms/{room_id}/vote"' in card
    assert f'action="/rooms/{room_id}/veto"' in card
    assert card.count('name="option_id"') == 2
    buttons = button_tags(html)
    for value in ("no", "ok", "yes"):
        assert 'type="submit"' in buttons[value]
        assert 'name="rating"' in buttons[value]
    assert 'type="submit"' in buttons["joker"]
    assert 'name="rating"' not in buttons["joker"]


def test_the_css_orders_the_row_and_never_hides_the_buttons():
    rules = css_rules()
    order = {}
    for selector, rule in rules:
        found = re.search(r"\border:\s*(\d+)", rule)
        if found is None:
            continue
        for key, pattern in (("no", 'value="no"'), ("ok", 'value="ok"'), ("yes", 'value="yes"'), ("joker", "veto")):
            if pattern in selector:
                order[key] = int(found.group(1))
    assert order["no"] < order["joker"] < order["ok"] < order["yes"]
    for selector, rule in rules:
        if "rating-row" in selector or "rating-buttons" in selector or "veto" in selector or 'name="rating"' in selector:
            assert "clip:" not in rule
            assert "display: none" not in rule and "display:none" not in rule


# --- Labels on the first card ----------------------------------------------

def test_the_first_card_shows_the_labels_and_the_hint(app, client):
    room_id = voting_room(app, client)
    html = vote_page(client, room_id)
    tag, _ = element(html, "data-rating-row")
    assert 'data-rating-labels="shown"' in tag
    assert FIRST_CARD_HINT in html
    buttons = button_tags(html)
    for value, label in (("no", "Rather not"), ("ok", "Fine with me"), ("yes", "Rather yes")):
        assert label in buttons[value]
    assert re.search(r">\s*Joker\s*<", buttons["joker"])


def test_after_one_rating_the_labels_are_hidden_but_still_there(app, client):
    room_id = voting_room(app, client)
    rate_shown(client, room_id)
    html = vote_page(client, room_id)
    tag, _ = element(html, "data-rating-row")
    assert 'data-rating-labels="hidden"' in tag
    assert FIRST_CARD_HINT not in html
    buttons = button_tags(html)
    for value, label in (("no", "Rather not"), ("ok", "Fine with me"), ("yes", "Rather yes")):
        assert label in buttons[value]  # still read by screen readers


def test_another_participant_still_gets_the_labels(app, client):
    """The labels depend on this participant's own votes, not on anybody else's."""
    room_id = create_room(client)
    for label in ("Pizza", "Tacos"):
        assert add_typed_option(client, room_id, label).status_code in (302, 303)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Ben"}).status_code in (302, 303)
    assert client.post(f"/rooms/{room_id}/start", data={"time_limit": ""}).status_code in (302, 303)
    rate_shown(client, room_id)
    html = vote_page(guest, room_id)
    assert 'data-rating-labels="shown"' in element(html, "data-rating-row")[0]


# --- The "?" panel ---------------------------------------------------------

def test_the_help_panel_explains_the_buttons_and_swipes(app, client):
    room_id = voting_room(app, client)
    html = vote_page(client, room_id)
    tag, inner = element(html, "data-rating-help")
    assert tag.startswith("<details")
    assert re.search(rf"<summary[^>]*{re.escape(HELP_LABEL)}[^>]*>.*\?.*</summary>", inner, re.DOTALL)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner))
    assert f"✕ Rather not – counts −{abs(scoring.POINTS['no'])}" in text
    assert f"🤷 Fine with me – counts +{scoring.POINTS['ok']}" in text
    assert f"♥ Rather yes – counts +{scoring.POINTS['yes']}" in text
    assert "🚫 Joker – rules this option out; once per room" in text
    assert "Swipe: right = Rather yes, up = Fine with me, left = Rather not, down = Joker" in text


def test_once_the_joker_is_used_it_leaves_the_row_and_the_help(app, client):
    room_id = voting_room(app, client)
    option_id = shown_option(vote_page(client, room_id))
    assert client.post(f"/rooms/{room_id}/veto", data={"option_id": option_id}).status_code in (302, 303)
    html = vote_page(client, room_id)
    assert set(button_tags(html)) == {"no", "ok", "yes"}
    _, inner = element(html, "data-rating-help")
    assert "🚫" not in inner
    assert "down = Joker" not in inner
    assert "left = Rather not" in inner


def test_no_swipe_legend_on_the_card_page(app, client):
    room_id = voting_room(app, client)
    assert "data-swipe-legend" not in vote_page(client, room_id)


def test_the_overview_after_the_last_card_is_unchanged(app, client):
    room_id = voting_room(app, client, labels=("Pizza", "Tacos"))
    for _ in range(2):
        rate_shown(client, room_id)
    html = vote_page(client, room_id)
    assert "You have rated all options." in html
    assert "data-rating-row" not in html
    assert "data-rating-help" not in html
    assert ">Rather yes</button>" in re.sub(r">\s+", ">", re.sub(r"\s+<", "<", html))


# --- Saving still works ----------------------------------------------------

def test_pressing_the_icon_buttons_saves_vote_and_veto(app, client):
    room_id = voting_room(app, client)
    first = rate_shown(client, room_id, rating="ok")
    assert [row["rating"] for row in votes(app, room_id)] == ["ok"]
    second = shown_option(vote_page(client, room_id))
    assert second != first
    response = client.post(f"/rooms/{room_id}/veto", data={"option_id": second})
    assert response.status_code in (302, 303)
    assert len(vetoes(app, room_id)) == 1


def test_the_labels_stay_hidden_after_a_restart(app, client):
    room_id = voting_room(app, client)
    rate_shown(client, room_id)
    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": app.config["SECRET_KEY"], "DATABASE": app.config["DATABASE"]}
    )
    browser = restarted.test_client()
    with client.session_transaction() as old, browser.session_transaction() as new:
        new.update(dict(old))
    html = browser.get(f"/rooms/{room_id}/vote").get_data(as_text=True)
    assert 'data-rating-labels="hidden"' in element(html, "data-rating-row")[0]
