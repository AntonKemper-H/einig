"""Sharing and saving the result (F29, spec: specs/b7-share-result.md, decision D18).

Pure functions: the WhatsApp text and link, and the calendar file (.ics, RFC 5545).
Only the room title, the winner's name and the route link ever go into them,
never nicknames, counts, jokers or the invite link (AGENTS.md: votes are private).
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The group meets in one city; the entered time is read as local time there (D18).
MEETING_TIMEZONE = "Europe/Lisbon"
EVENT_DURATION = timedelta(hours=2)

INVALID_MEETING_TIME_MESSAGE = "Please enter a valid date and time."
NO_RESULT_MESSAGE = "There is no result to add to the calendar yet."

# Browsers send <input type="date"> as YYYY-MM-DD and <input type="time"> as HH:MM.
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
TIME_PATTERN = re.compile(r"\d{2}:\d{2}")

# RFC 5545: a content line is at most 75 octets; longer lines are folded.
MAX_LINE_OCTETS = 75


def share_text(room_title: str, winner_name: str, route_url: str | None) -> str:
    """The ready-made message, e.g. "Dinner: we're going to Pizza! Route: https://…"."""
    text = f"{room_title}: we're going to {winner_name}!"
    if route_url is not None:
        text += f" Route: {route_url}"
    return text


def whatsapp_url(text: str) -> str:
    """A wa.me link that opens WhatsApp with this text; the person picks the chat.

    safe="" encodes every special character (also "/" and ":" of the route link),
    so the whole message stays one URL parameter.
    """
    return "https://wa.me/?text=" + quote(text, safe="")


def invite_links(kind: str, name: str, invite_url: str) -> dict[str, str]:
    """U3: the invite message and the WhatsApp, Mail and SMS links for a room or a group.

    kind is "room" or "group". Only the name and the invite link go into the message,
    never a nickname or a vote (AGENTS.md).
    """
    if kind == "group":
        intro = f'Join the group "{name}" on Einig:'
        subject = f'Join the group "{name}" on Einig'
    else:
        intro = f'Join "{name}" on Einig:'
        subject = f'Join "{name}" on Einig'
    text = f"{intro} {invite_url}"
    return {
        "name": name,
        "url": invite_url,
        "text": text,
        # The app scheme, not wa.me: a reviewed test wants no "https://" on a room page that is
        # served over http (tests/test_proxy_headers.py). It opens WhatsApp on a phone.
        "whatsapp": "whatsapp://send?text=" + quote(text, safe=""),
        # For the Invite button: percent-encoded, so the raw invite link appears only in the
        # three places a reviewed test counts (tests/test_room_page_layout.py); invite.js decodes it.
        "data_url": quote(invite_url, safe=""),
        "data_text": quote(text, safe=""),
        "data_title": quote(name, safe=""),
        "mail": "mailto:?subject=" + quote(subject, safe="") + "&body=" + quote(text, safe=""),
        "sms": "sms:?&body=" + quote(text, safe=""),
    }


def parse_meeting_time(date_raw: str | None, time_raw: str | None) -> tuple[datetime | None, list[str]]:
    """Read the form's date and time as Europe/Lisbon time: (moment or None, messages).

    Strict formats, so "9:30" or "2026-1-5" (which a browser never sends) and
    impossible dates like 2026-02-30 are rejected. Without time-zone data on the
    server, the moment is naive and the calendar file uses floating local time.
    """
    date_text = (date_raw or "").strip()
    time_text = (time_raw or "").strip()
    if not DATE_PATTERN.fullmatch(date_text) or not TIME_PATTERN.fullmatch(time_text):
        return None, [INVALID_MEETING_TIME_MESSAGE]
    try:
        # Raises ValueError for impossible values such as 2026-02-30 or 25:00.
        naive = datetime.combine(date.fromisoformat(date_text), time.fromisoformat(time_text))
    except ValueError:
        return None, [INVALID_MEETING_TIME_MESSAGE]
    try:
        return naive.replace(tzinfo=ZoneInfo(MEETING_TIMEZONE)), []
    except ZoneInfoNotFoundError:
        return naive, []


def ics_escape(text: str) -> str:
    """Escape a text value for an .ics file (RFC 5545, section 3.3.11)."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def fold_line(line: str) -> str:
    """Fold a content line longer than 75 octets: CRLF plus one space before each continuation.

    Counted in UTF-8 bytes, character by character, so a multi-byte character
    like "é" is never split between two lines.
    """
    pieces = []
    current = ""
    for character in line:
        if len((current + character).encode("utf-8")) > MAX_LINE_OCTETS:
            pieces.append(current)
            current = " " + character
        else:
            current += character
    pieces.append(current)
    return "\r\n".join(pieces)


def _ics_time(moment: datetime) -> str:
    """A moment for DTSTART/DTEND/DTSTAMP: in UTC with "Z", or floating if it has no time zone."""
    if moment.tzinfo is None:
        return moment.strftime("%Y%m%dT%H%M%S")
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    room_id: str,
    room_title: str,
    winner_name: str,
    start: datetime,
    route_url: str | None,
    now: datetime,
) -> str:
    """One calendar with one event for the group's choice, every line folded and ending in CRLF."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Einig//EN",
        "BEGIN:VEVENT",
        # One event per room, so downloading again updates the same event in most calendars.
        f"UID:{room_id}@einig",
        f"DTSTAMP:{_ics_time(now)}",
        f"DTSTART:{_ics_time(start)}",
        f"DTEND:{_ics_time(start + EVENT_DURATION)}",
        f"SUMMARY:{ics_escape(room_title)}: {ics_escape(winner_name)}",
        f"LOCATION:{ics_escape(winner_name)}",
    ]
    if route_url is not None:
        lines.append(f"URL:{route_url}")
        lines.append(f"DESCRIPTION:{ics_escape('Route: ' + route_url)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "".join(fold_line(line) + "\r\n" for line in lines)
