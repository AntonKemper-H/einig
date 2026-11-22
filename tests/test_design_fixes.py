"""Fixes after the design phase went into main with #81 (D21; reviews of #78 and #79)."""

import re
from pathlib import Path

APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"
STAMP = "[data-swipe-card][data-swipe-choice]::before"


def create_room(client, title="Dinner", mode="manual", nickname="Anna"):
    response = client.post("/rooms", data={"title": title, "mode": mode, "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def css_rules():
    css = re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.DOTALL)
    return [(selector.strip(), body) for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_the_swipe_stamp_never_wraps():
    # Review of #79: "RATHER YES" broke onto two lines and was cut at the card edge while dragging,
    # because the stamp sits at left: 50% and so gets only half the card's width.
    stamp_rules = [body for selector, body in css_rules() if STAMP in [s.strip() for s in selector.split(",")]]
    assert stamp_rules, f"no rule for {STAMP}"
    assert any(re.search(r"white-space\s*:\s*nowrap", body) for body in stamp_rules)


def test_side_stamps_sit_on_the_side_that_stays_in_sight():
    # Review of #79: a card dragged right moves half of itself off the screen, so a stamp in the middle
    # is cut. "Rather yes" (drag right) sits at the card's left corner, "Rather not" (drag left) at the right.
    rules = css_rules()
    yes = " ".join(body for selector, body in rules if '[data-swipe-choice="yes"]::before' in selector)
    no = " ".join(body for selector, body in rules if '[data-swipe-choice="no"]::before' in selector)
    assert re.search(r"(^|[;\s])left\s*:", yes) and "translateX" not in yes
    assert re.search(r"(^|[;\s])right\s*:", no) and re.search(r"(^|[;\s])left\s*:\s*auto", no)


def test_find_by_name_is_not_folded_in_a_manual_room(client):
    # E1 (#80): in a manual room the search by name is the only way to add a place, so it must be in sight.
    room_id = create_room(client, mode="manual")
    html = client.get(f"/rooms/{room_id}").get_data(as_text=True)
    find_form = html.index(f'action="/rooms/{room_id}/find"')
    before = html[:find_form]
    assert before.count("<details") - before.count("</details>") == 0, "the find form is inside a <details>"
