# B7 – F29 Share and save the result

Branch: `feature-b7-share-result`
Tests: `tests/test_share_result.py`

Decision: `docs/decisions.md`, D18 (approved by AntonKemper-H and mkim-nova in #45). Started after B5 was merged, as mkim-nova asked in #45.

## Why

After the vote the group has a winner, but the app stops there: someone still has to copy the name into the group chat and put the date into a calendar. Two buttons on the result page close that gap and turn "we decided" into "we are actually going".

## What

Rules from D18, `AGENTS.md` (Individual votes are private, Google Maps integration: only `place_id` stored and the key never in HTML, Post/Redirect/Get, Rejected actions, no JavaScript) and the review notes on #45 (AntonKemper-H: the calendar is a GET, invalid input is rejected, no misleading default time; mkim-nova: a calendar file without a time zone ends up an hour off).

### Decisions in this spec (please check in the review)

- **WhatsApp:** a normal link `https://wa.me/?text=<message>`. WhatsApp opens (app on the phone, WhatsApp Web on a laptop) and the person picks the chat; the app sends nothing itself. No API, no key.
- **Calendar as a GET form:** `GET /rooms/<room_id>/calendar.ics?date=YYYY-MM-DD&time=HH:MM` answers with the `.ics` file itself. Nothing is stored, so a GET is right (a POST that answers with a file would break Post/Redirect/Get) and reloading it is harmless.
- **No default date or time:** the two fields (`<input type="date" name="date" required>`, `<input type="time" name="time" required>`) start empty. The server runs in UTC, so "today, next full hour" would be an hour off in summer (review of #45).
- **Time zone (this changes D18's "floating time" line, in this PR):** the entered time is read as **Europe/Lisbon** time (the group meets in one city, and ours is Lisbon) and written to the file in **UTC** (`DTSTART:20261120T190000Z`). Every calendar app shows the right time, also across summer time. `zoneinfo` is in the standard library, so no new dependency. If the server has no time-zone data (`ZoneInfoNotFoundError`), the file falls back to floating local time (`DTSTART:20261120T190000`, no `Z`), which still shows 19:00 on a phone in Lisbon.
- **Privacy:** the message and the file contain only the room title, the winner's name and, for a Google winner, the route link. No nicknames, no counts, no jokers, and never the invite link.
- **Google terms:** the winner's name comes fresh from Place Details, as on the result page (C3, C2c); nothing is written to the database. A manual winner has no route link.

### Result page (`GET /rooms/<room_id>/result`, B3)

Only when the room is `closed` and has a winner, below the winner:
- A link "Share in WhatsApp" to `share.whatsapp_url(share.share_text(title, winner_name, route_url))`, `target="_blank" rel="noopener noreferrer"`.
- A form `method="get"` with `action="/rooms/<room_id>/calendar.ics"`, the fields `date` and `time` (both `required`, no `value`) and the button "Add to calendar".

Without a winner, or while the room is not closed, neither is shown.

### Calendar file (`GET /rooms/<room_id>/calendar.ics`)

- Unknown room → 404. A visitor without a token (or a participant of another room) → 303 to the room page, like the result page.
- Room not `closed`, or no winner → the result page with "There is no result to add to the calendar yet." (400), no file.
- Missing or invalid `date` or `time` (e.g. `2026-02-30`, `25:00`, `19`, `abc`, empty) → the result page with "Please enter a valid date and time." (400), no file.
- Otherwise 200 with `Content-Type: text/calendar; charset=utf-8` and `Content-Disposition: attachment; filename="einig.ics"`, body from `share.build_ics(...)`.

### Pure helpers: `app/services/share.py` (no Flask, no database, no `requests`)

- `MEETING_TIMEZONE = "Europe/Lisbon"`, `EVENT_DURATION = timedelta(hours=2)`, `INVALID_MEETING_TIME_MESSAGE = "Please enter a valid date and time."`, `NO_RESULT_MESSAGE = "There is no result to add to the calendar yet."`
- `share_text(room_title, winner_name, route_url) -> str` – `"<title>: we're going to <winner>!"`, plus `" Route: <route_url>"` when `route_url` is not `None`.
- `whatsapp_url(text) -> str` – `"https://wa.me/?text="` + the text percent-encoded (`urllib.parse.quote(text, safe="")`).
- The module imports `from zoneinfo import ZoneInfo` (so a test can simulate missing time-zone data by replacing `share.ZoneInfo`).
- `parse_meeting_time(date_raw, time_raw) -> tuple[datetime | None, list[str]]` – strict `YYYY-MM-DD` and `HH:MM` (as browsers send them), read as Europe/Lisbon time; returns an aware datetime, or `(None, [INVALID_MEETING_TIME_MESSAGE])` for anything else. Without time-zone data: a naive datetime (the floating fallback).
- `ics_escape(text) -> str` – RFC 5545 text escaping: `\` → `\\`, `;` → `\;`, `,` → `\,`, newline → `\n`.
- `fold_line(line) -> str` – lines longer than 75 octets (UTF-8) are folded: CRLF plus one space before each continuation, never splitting a multi-byte character.
- `build_ics(room_id, room_title, winner_name, start, route_url, now) -> str` – one `VCALENDAR` (`VERSION:2.0`, `PRODID:-//Einig//EN`) with one `VEVENT`: `UID:<room_id>@einig`, `DTSTAMP` (`now` in UTC, `...Z`), `DTSTART` and `DTEND` (`start` + 2 hours) in UTC with `Z` (or floating for a naive `start`), `SUMMARY:<title>: <winner>`, `LOCATION:<winner>`, and for a Google winner `URL:<route_url>` and `DESCRIPTION:Route: <route_url>`. All text values escaped, every line folded, every line ending in CRLF.

### Must be true (one line = one test)

#### Result page
- [ ] Closed room with a manual winner: the page has the WhatsApp link with the text "Dinner on Friday: we're going to Pizza!" (percent-encoded in the link, no "Route:") and the calendar form (`method="get"`, action `/rooms/<id>/calendar.ics`, `date` and `time` both `required`, no `value`).
- [ ] Closed room with a Google winner: the WhatsApp text has the real name and " Route: " with the C3 route link.
- [ ] No WhatsApp link and no calendar form while the room is not closed, and in a closed room without a winner.

#### Calendar file
- [ ] Valid date and time: 200, `text/calendar`, attachment `einig.ics`, and the body has `SUMMARY:Dinner on Friday: Pizza`, `LOCATION:Pizza`, `DTSTART:20261120T190000Z` and `DTEND:20261120T210000Z` for 2026-11-20 19:00.
- [ ] Summer time: 2026-07-01 19:00 Lisbon gives `DTSTART:20260701T180000Z`.
- [ ] Google winner: the file has the real name and `URL:` with the route link.
- [ ] Invalid date or time (`2026-02-30`, `25:00`, `19`, `abc`, empty, missing): the result page with "Please enter a valid date and time." (400), no `text/calendar`.
- [ ] Room still voting, and closed room without a winner: "There is no result to add to the calendar yet." (400), no file.
- [ ] A visitor and a participant of another room: 303 to the room page; unknown room: 404.
- [ ] Nothing is stored: the database is the same before and after a download.

#### Privacy
- [ ] Neither the WhatsApp text nor the calendar file contains a nickname or the invite link (`/rooms/<id>`).

#### Helpers
- [ ] `share_text` with and without a route; `whatsapp_url` percent-encodes spaces, `!`, `&`, `?`, `#`, `/`, `:` and non-ASCII characters.
- [ ] `parse_meeting_time` accepts `2026-11-20` + `19:00` (aware, Europe/Lisbon) and rejects the invalid examples above, plus `9:30` and `2026-1-5` (browsers always send two digits).
- [ ] Without time-zone data (simulated `ZoneInfoNotFoundError`): `parse_meeting_time` returns a naive datetime and `build_ics` writes `DTSTART:20261120T190000` without `Z`.
- [ ] `ics_escape` escapes backslash, semicolon, comma and newline.
- [ ] `fold_line` keeps short lines, folds a long line at 75 octets with CRLF + space, and never splits a multi-byte character (e.g. "é").
- [ ] `build_ics`: every line ends in CRLF, starts with `BEGIN:VCALENDAR` and ends with `END:VCALENDAR`, has `UID:<room_id>@einig` and `DTSTAMP` in UTC, and escapes a room title with a comma and a semicolon.

#### Code rules
- [ ] `app/services/share.py` imports no Flask, `requests` or `app.db`.

## Docs changed in this PR

- `docs/decisions.md`, D18, the "Time zone" line: from floating local time to "Europe/Lisbon time written in UTC, floating only as a fallback", as decided in the review of #45.

## Out of scope

- Sending messages from the app, or any WhatsApp/Google Calendar API.
- Sharing before the room is closed, or sharing the invite link.
- Storing the meeting date or time, reminders, or several dates to choose from.
- Other share targets (e-mail, Telegram): the WhatsApp text can be copied anywhere.
- Changes to `app/schema.sql` or to existing tests.

## Done when

- All tests in `tests/test_share_result.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network.
- Checked once by hand on the deployed app: the WhatsApp link opens WhatsApp with the text, and the `.ics` file opens in a phone calendar at the right time.
- Work is on branch `feature-b7-share-result`, pushed, pull request opened with AntonKemper-H as reviewer (D10: A reviews B).
