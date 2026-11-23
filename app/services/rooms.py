"""Rules for creating a room (spec: specs/a2-create-room.md) and the "My rooms" list (specs/a8-my-rooms.md)."""

import secrets

from app.services import activities

MODES = ["manual", "nearby", "surprise"]
TITLE_MAX_LENGTH = 80
# Browsers refuse cookies over about 4 KB, which would lose every token at once (A8).
MAX_REMEMBERED_ROOMS = 30
STATUS_LABELS = {"collecting": "Collecting ideas", "voting": "Voting", "closed": "Decided"}
STATUS_ENDPOINTS = {
    "collecting": "rooms.show_room",
    "voting": "rooms.show_vote",
    "closed": "rooms.show_result",
}
NICKNAME_MAX_LENGTH = 30


def clean_text(value: str | None) -> str:
    """Remove leading and trailing whitespace; a missing field becomes an empty string.

    The database only rejects text made of spaces, not tabs or line breaks,
    so whitespace must be removed here.
    """
    return (value or "").strip()


def validate_new_room(
    title: str | None, mode: str | None, nickname: str | None, kind: str | None = None
) -> tuple[dict[str, str], list[str]]:
    """Clean the create-room form and check it.

    U2: the optional activity ("drinks.bar") is returned as "kind" (empty if none was chosen).
    With a valid activity an empty title becomes the activity's name, e.g. "Bar".
    Returns the cleaned values and a list of error messages (empty if the form is valid).
    """
    cleaned = {
        "title": clean_text(title),
        "mode": mode or "",
        "nickname": clean_text(nickname),
        "kind": clean_text(kind),
    }
    errors = []

    parsed_kind = activities.parse_kind(cleaned["kind"]) if cleaned["kind"] else None
    if cleaned["kind"] and parsed_kind is None:
        errors.append(activities.KIND_MESSAGE)
    if not cleaned["title"] and parsed_kind is not None:
        cleaned["title"] = activities.kind_name(*parsed_kind)

    if not cleaned["title"]:
        errors.append("Please enter a title.")
    elif len(cleaned["title"]) > TITLE_MAX_LENGTH:
        errors.append(f"The title can be at most {TITLE_MAX_LENGTH} characters.")

    if cleaned["mode"] not in MODES:
        errors.append("Please choose a valid mode.")

    errors.extend(nickname_errors(cleaned["nickname"]))

    return cleaned, errors


def nickname_errors(nickname: str) -> list[str]:
    """Check an already cleaned nickname for being empty or too long (used by create and join)."""
    if not nickname:
        return ["Please enter a nickname."]
    if len(nickname) > NICKNAME_MAX_LENGTH:
        return [f"The nickname can be at most {NICKNAME_MAX_LENGTH} characters."]
    return []


def is_nickname_taken(nickname: str, existing_nicknames: list[str]) -> bool:
    """Return True if the nickname is already used, ignoring upper/lower case.

    Compared in Python with casefold(), because SQLite's lower() only handles
    the letters A-Z ("Ärger" and "ärger" would count as different).
    """
    wanted = nickname.casefold()
    return any(existing.casefold() == wanted for existing in existing_nicknames)


def join_errors(nickname: str, room_status: str, existing_nicknames: list[str]) -> list[str]:
    """Check whether someone may join a room with this cleaned nickname (F2).

    The route looks up the room status and the nicknames already in the room,
    so this function stays free of database code.
    """
    if room_status == "closed":
        return ["This room is closed. You can no longer join."]
    errors = nickname_errors(nickname)
    if not errors and is_nickname_taken(nickname, existing_nicknames):
        errors.append("This nickname is already taken in this room. Please choose another one.")
    return errors


def new_room_id() -> str:
    """Return a random, hard-to-guess room id (11 URL-safe characters, about 64 random bits)."""
    return secrets.token_urlsafe(8)


def new_session_token() -> str:
    """Return a random token that identifies one participant in their browser session."""
    return secrets.token_urlsafe(32)


def remember_room_token(tokens: dict[str, str], room_id: str, token: str) -> dict[str, str]:
    """Return a new dict with this room's token added or replaced; the given dict stays unchanged."""
    remembered = dict(tokens)
    remembered[room_id] = token
    return remembered


def rooms_to_keep(rooms: list[dict]) -> set[str]:
    """Return the ids of the MAX_REMEMBERED_ROOMS rooms this browser joined most recently.

    Each room carries this browser's own participant id in that room. Ids only grow,
    so a higher id was joined later. The order of the cookie cannot be used:
    Flask writes the session cookie with sorted keys.
    """
    newest_first = sorted(rooms, key=lambda room: room["participant_id"], reverse=True)
    return {room["id"] for room in newest_first[:MAX_REMEMBERED_ROOMS]}


def room_link_endpoint(status: str) -> str:
    """The page a room in "My rooms" links to: room page, rating page or result page."""
    return STATUS_ENDPOINTS.get(status, "rooms.show_room")
