"""Tests for B4 – F10 Joker / veto (specs/b4-joker.md)."""

import ast
import re
from pathlib import Path

import pytest

from app import create_app, db
from app.db import get_db
from app.services.results import every_option_vetoed, veto_counts
from app.services.voting import JOKER_USED_MESSAGE, veto_errors

NOT_STARTED_MESSAGE = "Voting has not started yet."
CLOSED_MESSAGE = "This room is closed. You can no longer vote."
UNKNOWN_OPTION_MESSAGE = "This option does not exist in this room."
JOKER_BUTTON = "Use my joker on this option (cannot be undone)"
ALL_VETOED_NOTE = "Every option got a joker, so the option with the fewest jokers won."
LABELS = ["Pizza", "Sushi", "Tacos"]
SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"


# --- Helpers ---------------------------------------------------------------

def create_room(client, title="Dinner on Friday", nickname="Anna"):
    """Create a room as its creator (A2) and return the room id."""
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def join(app, room_id, nickname):
    """Join a room (A3) with a new browser and return that browser."""
    browser = app.test_client()
    response = browser.post(f"/rooms/{room_id}/join", data={"nickname": nickname})
    assert response.status_code in (302, 303)
    return browser


def add_option(client, room_id, label):
    response = client.post(f"/rooms/{room_id}/options", data={"label": label})
    assert response.status_code in (302, 303)


def start(client, room_id):
    response = client.post(f"/rooms/{room_id}/start")
    assert response.status_code in (302, 303)


def vote(client, room_id, option_id, rating):
    return client.post(f"/rooms/{room_id}/vote", data={"option_id": str(option_id), "rating": rating})


def use_joker(client, room_id, option_id):
    return client.post(f"/rooms/{room_id}/veto", data={"option_id": str(option_id)})


def close(client, room_id):
    response = client.post(f"/rooms/{room_id}/close")
    assert response.status_code == 303


def vetoes(app):
    """All vetoes as (room_id, participant_id, option_id), sorted."""
    with app.app_context():
        rows = get_db().execute("SELECT room_id, participant_id, option_id FROM vetoes").fetchall()
    return sorted((row["room_id"], row["participant_id"], row["option_id"]) for row in rows)


def vote_count(app):
    with app.app_context():
        return get_db().execute("SELECT COUNT(*) AS total FROM votes").fetchone()["total"]


def set_room_status(app, room_id, status):
    with app.app_context():
        connection = get_db()
        connection.execute("UPDATE rooms SET status = ? WHERE id = ?", (status, room_id))
        connection.commit()


def token_of(client, room_id):
    with client.session_transaction() as session:
        return session["participant_tokens"][room_id]


def participant_id_of(app, client, room_id):
    with app.app_context():
        return db.get_participant(room_id, token_of(client, room_id))["id"]


def winner_of(app, room_id):
    with app.app_context():
        return get_db().execute(
            "SELECT winner_option_id FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()["winner_option_id"]


def page(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def forms(html):
    """Every <form …>…</form> block of a page."""
    return re.findall(r"<form\b[^>]*>.*?</form>", html, flags=re.DOTALL)


def joker_forms(html, room_id):
    return [form for form in forms(html) if f'action="/rooms/{room_id}/veto"' in form]


def hidden_option_id(form):
    match = re.search(r'name="option_id"\s+value="(\d+)"|value="(\d+)"\s+name="option_id"', form)
    assert match, form
    return int(match.group(1) or match.group(2))


def option_line(html, label):
    """The text of the result page from this option's label up to the next option's label."""
    start_at = html.index(label)
    ends = [html.find(other, start_at + len(label)) for other in LABELS if other != label]
    ends = [end for end in ends if end != -1]
    return html[start_at:min(ends)] if ends else html[start_at:]


@pytest.fixture
def room(app, client):
    """A voting room: Anna (creator, `client`) and Ben (`guest`), options Pizza, Sushi, Tacos."""
    room_id = create_room(client)
    guest = join(app, room_id, "Ben")
    for label in LABELS:
        add_option(client, room_id, label)
    start(client, room_id)
    with app.app_context():
        option_ids = {row["label"]: row["id"] for row in db.get_options(room_id)}
    return {"id": room_id, "guest": guest, "options": option_ids}


# --- Using the joker (accepted) --------------------------------------------

def test_joker_is_saved_and_redirects(app, client, room):
    pizza = room["options"]["Pizza"]
    response = use_joker(client, room["id"], pizza)
    assert response.status_code == 303
    assert response.headers["Location"].endswith(f"/rooms/{room['id']}/vote")
    assert vetoes(app) == [(room["id"], participant_id_of(app, client, room["id"]), pizza)]


def test_rating_page_shows_the_used_joker(client, room):
    use_joker(client, room["id"], room["options"]["Pizza"])
    html = page(client, f"/rooms/{room['id']}/vote")
    assert "You used your joker on: Pizza" in html
    assert joker_forms(html, room["id"]) == []
    assert JOKER_BUTTON not in html


def test_joker_is_not_a_rating(app, client, room):
    html = page(client, f"/rooms/{room['id']}/vote")
    shown = hidden_option_id(joker_forms(html, room["id"])[0])
    use_joker(client, room["id"], shown)
    assert vote_count(app) == 0
    after = page(client, f"/rooms/{room['id']}/vote")
    rating_forms = [form for form in forms(after) if 'name="rating"' in form]
    assert [hidden_option_id(form) for form in rating_forms] == [shown]


def test_two_participants_can_use_their_jokers_on_the_same_option(app, client, room):
    pizza = room["options"]["Pizza"]
    assert use_joker(client, room["id"], pizza).status_code == 303
    assert use_joker(room["guest"], room["id"], pizza).status_code == 303
    assert [option for _, _, option in vetoes(app)] == [pizza, pizza]


# --- Using the joker (rejected) --------------------------------------------

@pytest.mark.parametrize("second", ["Pizza", "Sushi"])
def test_second_joker_is_rejected(app, client, room, second):
    pizza = room["options"]["Pizza"]
    use_joker(client, room["id"], pizza)
    response = use_joker(client, room["id"], room["options"][second])
    assert response.status_code == 400
    assert JOKER_USED_MESSAGE in response.get_data(as_text=True)
    assert [option for _, _, option in vetoes(app)] == [pizza]


def test_two_presses_at_once_keep_one_joker(app, client, room, monkeypatch):
    pizza = room["options"]["Pizza"]
    use_joker(client, room["id"], pizza)
    # The route's check runs a moment before the first joker is committed.
    monkeypatch.setattr(db, "get_own_veto", lambda room_id, participant_id: None)
    response = use_joker(client, room["id"], room["options"]["Sushi"])
    assert response.status_code == 400
    assert JOKER_USED_MESSAGE in response.get_data(as_text=True)
    assert [option for _, _, option in vetoes(app)] == [pizza]


def test_joker_in_collecting_room_is_rejected(app, client):
    room_id = create_room(client)
    add_option(client, room_id, "Pizza")
    with app.app_context():
        pizza = db.get_options(room_id)[0]["id"]
    response = use_joker(client, room_id, pizza)
    assert response.status_code == 400
    assert NOT_STARTED_MESSAGE in response.get_data(as_text=True)
    assert vetoes(app) == []


def test_joker_in_closed_room_is_rejected(app, client, room):
    close(client, room["id"])
    response = use_joker(room["guest"], room["id"], room["options"]["Pizza"])
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert vetoes(app) == []


def test_joker_reaching_the_database_after_closing_is_not_saved(app, client, room, monkeypatch):
    close(client, room["id"])
    real_get_room = db.get_room

    def room_still_voting(room_id):
        row = dict(real_get_room(room_id))
        row["status"] = "voting"
        return row

    monkeypatch.setattr(db, "get_room", room_still_voting)
    response = use_joker(room["guest"], room["id"], room["options"]["Pizza"])
    assert response.status_code == 400
    assert CLOSED_MESSAGE in response.get_data(as_text=True)
    assert vetoes(app) == []


def test_save_veto_returns_whether_it_saved(app, client, room):
    participant = participant_id_of(app, client, room["id"])
    pizza = room["options"]["Pizza"]
    set_room_status(app, room["id"], "closed")
    with app.app_context(), db.transaction():
        assert db.save_veto(room["id"], participant, pizza) is False
    assert vetoes(app) == []
    set_room_status(app, room["id"], "voting")
    with app.app_context(), db.transaction():
        assert db.save_veto(room["id"], participant, pizza) is True
    assert vetoes(app) == [(room["id"], participant, pizza)]


def test_joker_on_an_option_that_is_not_rateable_is_rejected(app, client, room):
    other_room = create_room(app.test_client(), title="Other room", nickname="Zoe")
    with app.app_context():
        connection = get_db()
        foreign = connection.execute(
            "INSERT INTO options (room_id, source, label) VALUES (?, 'manual', 'Elsewhere') RETURNING id",
            (other_room,),
        ).fetchone()["id"]
        connection.execute("UPDATE options SET is_replaced = 1 WHERE id = ?", (room["options"]["Tacos"],))
        connection.commit()
    for option_id in (999999, foreign, room["options"]["Tacos"], "abc"):
        response = use_joker(client, room["id"], option_id)
        assert response.status_code == 400, option_id
        assert UNKNOWN_OPTION_MESSAGE in response.get_data(as_text=True)
    assert vetoes(app) == []


def test_visitor_and_other_room_participant_cannot_use_a_joker(app, room):
    visitor = app.test_client()
    other = app.test_client()
    create_room(other, title="Other room", nickname="Zoe")
    for browser in (visitor, other):
        response = use_joker(browser, room["id"], room["options"]["Pizza"])
        assert response.status_code == 403
    assert vetoes(app) == []


def test_unknown_room_is_404(client):
    assert use_joker(client, "no-such-room", 1).status_code == 404


# --- Rating page -----------------------------------------------------------

def test_next_card_has_a_separate_joker_form(client, room):
    html = page(client, f"/rooms/{room['id']}/vote")
    jokers = joker_forms(html, room["id"])
    assert len(jokers) == 1
    rating_forms = [form for form in forms(html) if 'name="rating"' in form]
    assert len(rating_forms) == 1
    assert hidden_option_id(jokers[0]) == hidden_option_id(rating_forms[0])
    assert JOKER_BUTTON in jokers[0]
    assert 'name="rating"' not in jokers[0]
    assert "/veto" not in rating_forms[0]


def test_overview_has_a_joker_form_per_card(client, room):
    for option_id in room["options"].values():
        vote(client, room["id"], option_id, "ok")
    html = page(client, f"/rooms/{room['id']}/vote")
    assert "You have rated all options." in html
    jokers = joker_forms(html, room["id"])
    assert sorted(hidden_option_id(form) for form in jokers) == sorted(room["options"].values())


def test_rating_page_does_not_show_other_peoples_jokers(client, room):
    use_joker(room["guest"], room["id"], room["options"]["Pizza"])
    html = page(client, f"/rooms/{room['id']}/vote")
    assert "You used your joker" not in html
    assert len(joker_forms(html, room["id"])) == 1


@pytest.mark.parametrize("status", ["collecting", "closed"])
def test_no_joker_form_outside_voting(app, client, room, status):
    set_room_status(app, room["id"], status)
    html = page(client, f"/rooms/{room['id']}/vote")
    assert joker_forms(html, room["id"]) == []
    assert JOKER_BUTTON not in html


# --- Effect on the result --------------------------------------------------

def test_vetoed_option_is_not_chosen(app, client, room):
    pizza, sushi, tacos = (room["options"][label] for label in LABELS)
    for browser in (client, room["guest"]):
        vote(browser, room["id"], pizza, "yes")
        vote(browser, room["id"], sushi, "ok")
        vote(browser, room["id"], tacos, "no")
    use_joker(room["guest"], room["id"], pizza)
    close(client, room["id"])
    assert winner_of(app, room["id"]) == sushi


def test_every_option_vetoed_fewest_jokers_then_best_score(app, client, room):
    pizza, sushi, tacos = (room["options"][label] for label in LABELS)
    cara = join(app, room["id"], "Cara")
    dan = join(app, room["id"], "Dan")
    browsers = (client, room["guest"], cara, dan)
    for browser in browsers:
        vote(browser, room["id"], pizza, "yes")
        vote(browser, room["id"], sushi, "no")
        vote(browser, room["id"], tacos, "ok")
    # Pizza: 2 jokers, Sushi: 1, Tacos: 1. Sushi and Tacos tie on jokers; Tacos scores better.
    for browser, option_id in zip(browsers, (pizza, pizza, sushi, tacos)):
        assert use_joker(browser, room["id"], option_id).status_code == 303
    close(client, room["id"])
    assert winner_of(app, room["id"]) == tacos


def test_joker_of_a_participant_who_rated_nothing_still_counts(app, client, room):
    pizza = room["options"]["Pizza"]
    vote(client, room["id"], pizza, "yes")
    use_joker(room["guest"], room["id"], pizza)
    close(client, room["id"])
    winner = winner_of(app, room["id"])
    assert winner is not None
    assert winner != pizza


# --- Result page -----------------------------------------------------------

def test_result_page_shows_anonymous_joker_counts(app, client, room):
    pizza, sushi = room["options"]["Pizza"], room["options"]["Sushi"]
    cara = join(app, room["id"], "Cara")
    vote(client, room["id"], sushi, "yes")
    use_joker(client, room["id"], pizza)
    use_joker(room["guest"], room["id"], pizza)
    use_joker(cara, room["id"], sushi)
    close(client, room["id"])
    html = page(client, f"/rooms/{room['id']}/result")
    counts = html.split("How the options were rated", 1)[1]
    assert "excluded by 2× joker" in option_line(counts, "Pizza")
    assert "excluded by 1× joker" in option_line(counts, "Sushi")
    assert "excluded" not in option_line(counts, "Tacos")
    assert ALL_VETOED_NOTE not in html


def test_result_page_notes_when_every_option_got_a_joker(app, client, room):
    cara = join(app, room["id"], "Cara")
    vote(client, room["id"], room["options"]["Tacos"], "yes")
    for browser, label in zip((client, room["guest"], cara), LABELS):
        use_joker(browser, room["id"], room["options"][label])
    close(client, room["id"])
    html = page(client, f"/rooms/{room['id']}/result")
    assert ALL_VETOED_NOTE in html
    assert "The group's choice: Tacos" in html


def test_result_page_shows_no_nicknames_with_jokers(app):
    creator = app.test_client()
    room_id = create_room(creator, nickname="Zorbia")
    guest = join(app, room_id, "Quentix")
    for label in LABELS:
        add_option(creator, room_id, label)
    start(creator, room_id)
    with app.app_context():
        pizza = db.get_options(room_id)[0]["id"]
    vote(creator, room_id, pizza, "yes")
    use_joker(guest, room_id, pizza)
    close(creator, room_id)
    html = page(creator, f"/rooms/{room_id}/result")
    assert "excluded by 1× joker" in html
    assert "Zorbia" not in html
    assert "Quentix" not in html


# --- Helpers ---------------------------------------------------------------

def test_veto_errors_order():
    rateable = [1, 2]
    assert veto_errors("collecting", 99, rateable, 1) == [NOT_STARTED_MESSAGE]
    assert veto_errors("closed", 99, rateable, 1) == [CLOSED_MESSAGE]
    assert veto_errors("voting", 99, rateable, 1) == [JOKER_USED_MESSAGE]
    assert veto_errors("voting", 99, rateable, None) == [UNKNOWN_OPTION_MESSAGE]
    assert veto_errors("voting", None, rateable, None) == [UNKNOWN_OPTION_MESSAGE]
    assert veto_errors("voting", 2, rateable, None) == []


def test_veto_counts():
    assert veto_counts([1, 2, 3], [1, 1, 3, 99]) == {1: 2, 2: 0, 3: 1}
    assert veto_counts([], [1]) == {}


def test_every_option_vetoed():
    assert every_option_vetoed([1, 2], [1, 2, 2]) is True
    assert every_option_vetoed([1, 2], [1, 1]) is False
    assert every_option_vetoed([], []) is False


def test_get_own_veto(app, client, room):
    participant = participant_id_of(app, client, room["id"])
    with app.app_context():
        assert db.get_own_veto(room["id"], participant) is None
    use_joker(client, room["id"], room["options"]["Sushi"])
    with app.app_context():
        assert db.get_own_veto(room["id"], participant) == room["options"]["Sushi"]


# --- Persistence -----------------------------------------------------------

def test_joker_survives_a_restart(app, client, room):
    use_joker(client, room["id"], room["options"]["Pizza"])
    restarted = create_app(
        {"TESTING": True, "SECRET_KEY": "test-only-not-a-real-key", "DATABASE": app.config["DATABASE"]}
    )
    browser = restarted.test_client()
    with browser.session_transaction() as session:
        session["participant_tokens"] = {room["id"]: token_of(client, room["id"])}
    assert "You used your joker on: Pizza" in page(browser, f"/rooms/{room['id']}/vote")
    response = use_joker(browser, room["id"], room["options"]["Sushi"])
    assert response.status_code == 400
    assert JOKER_USED_MESSAGE in response.get_data(as_text=True)


# --- Code rules ------------------------------------------------------------

@pytest.mark.parametrize("module", ["voting.py", "results.py"])
def test_services_have_no_forbidden_imports(module):
    source = (SERVICES / module).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import on line {node.lineno}"
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    for name in imported:
        assert name.split(".")[0] not in {"flask", "requests"}, name
        assert name != "app.db" and not name.startswith("app.db."), name
