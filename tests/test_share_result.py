"""Tests for B7 – F29 Share and save the result (specs/b7-share-result.md)."""

import ast
import html as html_lib
import re
import zoneinfo
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

from app import db
from app.db import get_db
from app.services import places, share
from typed_option import add_typed_option

INVALID_TIME = "Please enter a valid date and time."
NO_RESULT = "There is no result to add to the calendar yet."
SHARE_FILE = Path(__file__).resolve().parents[1] / "app" / "services" / "share.py"
DETAILS_URL = "https://places.googleapis.com/v1/places/"
FAKE_KEY = "fake-key-for-tests-0123456789"


# --- Fake Google (only for the Google winner) ------------------------------

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
        if url == DETAILS_URL + "place-a":
            return FakeResponse(body={"displayName": {"text": "Pizza Roma"}, "rating": 4.5})
        return FakeResponse(status_code=404, body={"error": {}})


@pytest.fixture(autouse=True)
def google(app, monkeypatch):
    app.config["GOOGLE_MAPS_API_KEY"] = FAKE_KEY
    fake = FakeGet()
    monkeypatch.setattr(places.requests, "get", fake)
    return fake


# --- Helpers ---------------------------------------------------------------

def create_room(client, nickname="Zorbia", title="Dinner on Friday"):
    response = client.post("/rooms", data={"title": title, "mode": "manual", "nickname": nickname})
    assert response.status_code in (302, 303)
    return response.headers["Location"].rsplit("/rooms/", 1)[1]


def add_option(client, room_id, label):
    assert add_typed_option(client, room_id, label).status_code in (302, 303)


def option_ids(app, room_id):
    with app.app_context():
        return {row["label"] or row["place_id"]: row["id"] for row in db.get_options(room_id)}


def closed_manual_room(app, client):
    """Zorbia (creator) and Quentix; options Pizza and Sushi; Pizza wins; room closed."""
    room_id = create_room(client)
    guest = app.test_client()
    assert guest.post(f"/rooms/{room_id}/join", data={"nickname": "Quentix"}).status_code in (302, 303)
    add_option(client, room_id, "Pizza")
    add_option(client, room_id, "Sushi")
    assert client.post(f"/rooms/{room_id}/start").status_code == 303
    ids = option_ids(app, room_id)
    client.post(f"/rooms/{room_id}/vote", data={"option_id": ids["Pizza"], "rating": "yes"})
    assert client.post(f"/rooms/{room_id}/close").status_code == 303
    return room_id


def closed_google_room(app, client):
    """One Google option (place-a, "Pizza Roma") that wins; room closed."""
    room_id = create_room(client)
    with app.app_context():
        connection = get_db()
        connection.execute(
            "INSERT INTO options (room_id, source, place_id, category) VALUES (?, 'google', 'place-a', 'restaurant')",
            (room_id,),
        )
        connection.commit()
    add_option(client, room_id, "Sushi")
    assert client.post(f"/rooms/{room_id}/start").status_code == 303
    ids = option_ids(app, room_id)
    client.post(f"/rooms/{room_id}/vote", data={"option_id": ids["place-a"], "rating": "yes"})
    client.post(f"/rooms/{room_id}/vote", data={"option_id": ids["Sushi"], "rating": "no"})
    with app.app_context():
        assert get_db().execute("SELECT status FROM rooms WHERE id = ?", (room_id,)).fetchone()["status"] == "closed"
    return room_id


def result_html(client, room_id):
    response = client.get(f"/rooms/{room_id}/result")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def whatsapp_href(page_html):
    match = re.search(r'href="(https://wa\.me/\?text=[^"]*)"', page_html)
    assert match, "WhatsApp link missing"
    return html_lib.unescape(match.group(1))


def whatsapp_text(page_html):
    return unquote(whatsapp_href(page_html).split("?text=", 1)[1])


def calendar_form(page_html, room_id):
    match = re.search(rf'<form[^>]*action="/rooms/{room_id}/calendar\.ics"[^>]*>.*?</form>', page_html, flags=re.DOTALL)
    return match.group(0) if match else None


def download(client, room_id, **params):
    return client.get(f"/rooms/{room_id}/calendar.ics", query_string=params)


def dump(app):
    with app.app_context():
        return list(get_db().iterdump())


# --- Result page -----------------------------------------------------------

def test_result_page_has_whatsapp_link_and_calendar_form(app, client):
    room_id = closed_manual_room(app, client)
    page_html = result_html(client, room_id)
    assert whatsapp_text(page_html) == "Dinner on Friday: we're going to Pizza!"
    assert "%20" in whatsapp_href(page_html)
    form = calendar_form(page_html, room_id)
    assert form, "calendar form missing"
    assert re.search(r'method="get"', form, flags=re.IGNORECASE)
    for name, kind in (("date", "date"), ("time", "time")):
        field = re.search(rf'<input[^>]*name="{name}"[^>]*>', form)
        assert field, name
        assert f'type="{kind}"' in field.group(0)
        assert "required" in field.group(0)
        assert "value=" not in field.group(0)


def test_google_winner_share_text_has_name_and_route(app, client):
    room_id = closed_google_room(app, client)
    text = whatsapp_text(result_html(client, room_id))
    route = places.route_url("place-a", "Pizza Roma")
    assert text == f"Dinner on Friday: we're going to Pizza Roma! Route: {route}"


def test_no_share_buttons_without_a_closed_result(app, client):
    room_id = create_room(client)
    add_option(client, room_id, "Pizza")
    add_option(client, room_id, "Sushi")
    assert client.post(f"/rooms/{room_id}/start").status_code == 303
    voting = result_html(client, room_id)
    assert "wa.me" not in voting
    assert calendar_form(voting, room_id) is None
    assert client.post(f"/rooms/{room_id}/close").status_code == 303  # nobody rated: no winner
    no_winner = result_html(client, room_id)
    assert "No winner" in no_winner
    assert "wa.me" not in no_winner
    assert calendar_form(no_winner, room_id) is None


# --- Calendar file ---------------------------------------------------------

def test_calendar_file_for_a_valid_date_and_time(app, client):
    room_id = closed_manual_room(app, client)
    response = download(client, room_id, date="2026-11-20", time="19:00")
    assert response.status_code == 200
    assert response.content_type.startswith("text/calendar")
    assert "charset=utf-8" in response.content_type.lower()
    disposition = response.headers["Content-Disposition"]
    assert "attachment" in disposition and "einig.ics" in disposition
    body = response.get_data(as_text=True)
    for line in (
        "SUMMARY:Dinner on Friday: Pizza",
        "LOCATION:Pizza",
        "DTSTART:20261120T190000Z",
        "DTEND:20261120T210000Z",
    ):
        assert line + "\r\n" in body, line


def test_calendar_file_uses_lisbon_summer_time(app, client):
    room_id = closed_manual_room(app, client)
    body = download(client, room_id, date="2026-07-01", time="19:00").get_data(as_text=True)
    assert "DTSTART:20260701T180000Z\r\n" in body


def test_calendar_file_for_a_google_winner(app, client):
    room_id = closed_google_room(app, client)
    body = download(client, room_id, date="2026-11-20", time="19:00").get_data(as_text=True)
    unfolded = body.replace("\r\n ", "")
    assert "SUMMARY:Dinner on Friday: Pizza Roma\r\n" in unfolded
    assert "URL:" + places.route_url("place-a", "Pizza Roma") + "\r\n" in unfolded


@pytest.mark.parametrize(
    "params",
    [
        {"date": "2026-02-30", "time": "19:00"},
        {"date": "2026-11-20", "time": "25:00"},
        {"date": "2026-11-20", "time": "19"},
        {"date": "abc", "time": "19:00"},
        {"date": "", "time": ""},
        {},
    ],
)
def test_invalid_date_or_time_is_rejected(app, client, params):
    room_id = closed_manual_room(app, client)
    response = download(client, room_id, **params)
    assert response.status_code == 400
    assert not response.content_type.startswith("text/calendar")
    assert INVALID_TIME in response.get_data(as_text=True)


def test_no_file_without_a_closed_result(app, client):
    room_id = create_room(client)
    add_option(client, room_id, "Pizza")
    add_option(client, room_id, "Sushi")
    assert client.post(f"/rooms/{room_id}/start").status_code == 303
    response = download(client, room_id, date="2026-11-20", time="19:00")
    assert response.status_code == 400
    assert NO_RESULT in response.get_data(as_text=True)
    assert client.post(f"/rooms/{room_id}/close").status_code == 303  # no winner
    response = download(client, room_id, date="2026-11-20", time="19:00")
    assert response.status_code == 400
    assert NO_RESULT in response.get_data(as_text=True)
    assert not response.content_type.startswith("text/calendar")


def test_visitors_and_unknown_rooms(app, client):
    room_id = closed_manual_room(app, client)
    visitor = app.test_client()
    other = app.test_client()
    create_room(other, nickname="Zoe", title="Other room")
    for browser in (visitor, other):
        response = download(browser, room_id, date="2026-11-20", time="19:00")
        assert response.status_code == 303
        assert response.headers["Location"].endswith(f"/rooms/{room_id}")
    assert download(client, "no-such-room", date="2026-11-20", time="19:00").status_code == 404


def test_download_stores_nothing(app, client):
    room_id = closed_manual_room(app, client)
    before = dump(app)
    assert download(client, room_id, date="2026-11-20", time="19:00").status_code == 200
    assert dump(app) == before


# --- Privacy ---------------------------------------------------------------

def test_share_text_and_file_reveal_no_names_and_no_invite_link(app, client):
    room_id = closed_manual_room(app, client)
    text = whatsapp_text(result_html(client, room_id))
    body = download(client, room_id, date="2026-11-20", time="19:00").get_data(as_text=True)
    for content in (text, body):
        assert "Zorbia" not in content
        assert "Quentix" not in content
        assert "/rooms/" not in content


# --- Helpers ---------------------------------------------------------------

def test_share_text_and_whatsapp_url():
    assert share.share_text("Dinner", "Pizza", None) == "Dinner: we're going to Pizza!"
    assert share.share_text("Dinner", "Pizza", "https://maps.example/x") == (
        "Dinner: we're going to Pizza! Route: https://maps.example/x"
    )
    url = share.whatsapp_url("A b! & c? #d é https://x/y")
    assert url.startswith("https://wa.me/?text=")
    encoded = url.split("?text=", 1)[1]
    for raw in (" ", "!", "&", "?", "#", "é", "/", ":"):
        assert raw not in encoded, raw
    assert unquote(encoded) == "A b! & c? #d é https://x/y"


def test_parse_meeting_time():
    moment, errors = share.parse_meeting_time("2026-11-20", "19:00")
    assert errors == []
    assert moment.tzinfo is not None
    assert moment.utcoffset().total_seconds() == 0
    assert moment.astimezone(UTC) == datetime(2026, 11, 20, 19, 0, tzinfo=UTC)
    summer, _ = share.parse_meeting_time("2026-07-01", "19:00")
    assert summer.astimezone(UTC) == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
    for date_raw, time_raw in (
        ("2026-02-30", "19:00"),
        ("2026-11-20", "25:00"),
        ("2026-11-20", "19"),
        ("abc", "19:00"),
        ("20.11.2026", "19:00"),
        ("2026-11-20", "9:30"),
        ("2026-1-5", "19:00"),
        ("", ""),
        (None, None),
    ):
        assert share.parse_meeting_time(date_raw, time_raw) == (None, [INVALID_TIME]), (date_raw, time_raw)


def test_floating_time_without_time_zone_data(monkeypatch):
    def no_data(key):
        raise zoneinfo.ZoneInfoNotFoundError(key)

    monkeypatch.setattr(share, "ZoneInfo", no_data)
    moment, errors = share.parse_meeting_time("2026-11-20", "19:00")
    assert errors == []
    assert moment.tzinfo is None
    body = share.build_ics("r1", "Dinner", "Pizza", moment, None, datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    assert "DTSTART:20261120T190000\r\n" in body
    assert "DTEND:20261120T210000\r\n" in body


def test_ics_escape():
    assert share.ics_escape("a\\b;c,d\ne") == "a\\\\b\\;c\\,d\\ne"
    assert share.ics_escape("plain") == "plain"


def test_fold_line():
    assert share.fold_line("SUMMARY:short") == "SUMMARY:short"
    long_line = "DESCRIPTION:" + "x" * 100
    folded = share.fold_line(long_line)
    parts = folded.split("\r\n")
    assert all(len(part.encode("utf-8")) <= 75 for part in parts)
    assert all(part.startswith(" ") for part in parts[1:])
    assert "".join(part[1:] if i else part for i, part in enumerate(parts)) == long_line
    accents = "SUMMARY:" + "é" * 60
    folded = share.fold_line(accents)
    pieces = folded.split("\r\n")
    assert all(len(piece.encode("utf-8")) <= 75 for piece in pieces)
    assert "".join(piece[1:] if i else piece for i, piece in enumerate(pieces)) == accents


def test_build_ics():
    start, _ = share.parse_meeting_time("2026-11-20", "19:00")
    now = datetime(2026, 11, 19, 12, 30, 5, tzinfo=UTC)
    body = share.build_ics("room123", "Dinner, drinks; fun", "Pizza", start, "https://maps.example/x", now)
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert body.endswith("END:VCALENDAR\r\n")
    assert "\n" not in body.replace("\r\n", "")
    for line in (
        "VERSION:2.0",
        "PRODID:-//Einig//EN",
        "BEGIN:VEVENT",
        "UID:room123@einig",
        "DTSTAMP:20261119T123005Z",
        "DTSTART:20261120T190000Z",
        "DTEND:20261120T210000Z",
        "SUMMARY:Dinner\\, drinks\\; fun: Pizza",
        "LOCATION:Pizza",
        "URL:https://maps.example/x",
        "DESCRIPTION:Route: https://maps.example/x",
        "END:VEVENT",
    ):
        assert line + "\r\n" in body, line
    manual = share.build_ics("room123", "Dinner", "Pizza", start, None, now)
    assert "URL:" not in manual and "DESCRIPTION:" not in manual


# --- Code rules ------------------------------------------------------------

def test_share_module_has_no_forbidden_imports():
    source = SHARE_FILE.read_text(encoding="utf-8")
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
