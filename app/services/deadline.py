"""Rules for the deadline (F11, spec: specs/b5-deadline.md).

Pure functions plus one clock (now_utc), so the routes and the tests decide
which moment counts as "now". Times are stored as UTC text in the A1 format
'YYYY-MM-DD HH:MM:SS', which compares correctly as text on SQLite and Postgres.
"""

import math
from datetime import UTC, datetime, timedelta

# The choices on the "Start voting" form, in minutes.
TIME_LIMITS = (15, 30, 60)
INVALID_TIME_LIMIT_MESSAGE = "Please choose one of the time limits."

UTC_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_time_limit(raw: str | None) -> tuple[int | None, list[str]]:
    """Read the form's time limit: (minutes or None, messages).

    Empty means "no time limit". Only the listed choices are accepted, so a
    hand-made request cannot set a 1-minute or a 3-day deadline.
    """
    value = (raw or "").strip()
    if not value:
        return None, []
    allowed = {str(minutes): minutes for minutes in TIME_LIMITS}
    if value in allowed:
        return allowed[value], []
    return None, [INVALID_TIME_LIMIT_MESSAGE]


def now_utc() -> datetime:
    """The current server time in UTC: the only place that reads the clock (AGENTS.md: UTC only)."""
    return datetime.now(UTC)


def format_utc(moment: datetime) -> str:
    """A moment as stored text in UTC, e.g. '2026-11-20 19:00:00'."""
    return moment.astimezone(UTC).strftime(UTC_FORMAT)


def deadline_after(now: datetime, minutes: int) -> str:
    """The deadline `minutes` after `now`, as stored text."""
    return format_utc(now + timedelta(minutes=minutes))


def _parse_utc(deadline: str) -> datetime:
    """Stored UTC text back to an aware datetime."""
    return datetime.strptime(deadline, UTC_FORMAT).replace(tzinfo=UTC)


def is_past(deadline: str | None, now: datetime) -> bool:
    """True from the deadline second on. A room without a deadline never runs out of time."""
    return deadline is not None and now >= _parse_utc(deadline)


def minutes_left(deadline: str | None, now: datetime) -> int | None:
    """Whole minutes left, rounded up (the last seconds still count as 1), 0 once past; None without a deadline."""
    if deadline is None:
        return None
    seconds = (_parse_utc(deadline) - now).total_seconds()
    return max(0, math.ceil(seconds / 60))


def time_left_text(deadline: str | None, now: datetime) -> str | None:
    """'Time left: 12 min' while there is time left, else None.

    Minutes instead of a clock time: they are the same for everyone, whatever
    time zone their phone is in.
    """
    left = minutes_left(deadline, now)
    if not left:
        return None
    return f"Time left: {left} min"
