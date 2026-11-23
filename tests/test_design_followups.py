"""Small design follow-ups after the handy test (D21): clearer limit label, no idle header pill on home."""

import re
from pathlib import Path

import pytest

APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "app.css"
LIMIT_LABEL = "Places each person may add"
LIMIT_HINT = "Suggested places don't count."


def create_room(client, mode="manual"):
    response = client.post("/rooms", data={"title": "Dinner", "mode": mode, "nickname": "Anna"})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def setup_form(client, room_id):
    html = client.get(f"/rooms/{room_id}").get_data(as_text=True)
    start = html.index(f'action="/rooms/{room_id}/setup"')
    return html[start:html.index("</form>", start)]


def css_rules():
    css = re.sub(r"/\*.*?\*/", "", APP_CSS.read_text(), flags=re.DOTALL)
    return [(selector.strip(), body) for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


@pytest.mark.parametrize("mode", ["manual", "nearby", "surprise"])
def test_the_limit_says_what_it_counts(client, mode):
    # The limit only counts places a person adds themselves (search results never count, db.count_own_options).
    form = setup_form(client, create_room(client, mode))
    assert re.search(rf"<label>\s*{LIMIT_LABEL}", form)
    assert "Options per person" not in form
    assert 'name="options_per_person"' in form


def test_rooms_with_suggested_places_explain_that_they_do_not_count(client):
    assert LIMIT_HINT in setup_form(client, create_room(client, "nearby"))
    assert LIMIT_HINT in setup_form(client, create_room(client, "surprise"))
    assert LIMIT_HINT not in setup_form(client, create_room(client, "manual"))


def test_the_header_pill_is_hidden_on_the_home_page_only():
    # On the home page "My rooms" leads to the same page; the link stays in the HTML (A8), only out of sight.
    hiding = [
        selector for selector, body in css_rules()
        if ".home-page" in selector and "site-header" in selector
        and re.search(r"visibility\s*:\s*hidden|display\s*:\s*none", body)
    ]
    assert hiding
    assert all(".home-page" in selector for selector in hiding)
