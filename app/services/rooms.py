"""Rules for creating a room (spec: specs/a2-create-room.md)."""

import secrets

MODES = ["manual", "nearby", "surprise"]
TITLE_MAX_LENGTH = 80
NICKNAME_MAX_LENGTH = 30


def clean_text(value: str | None) -> str:
    """Remove leading and trailing whitespace; a missing field becomes an empty string.

    The database only rejects text made of spaces, not tabs or line breaks,
    so whitespace must be removed here.
    """
    return (value or "").strip()


def validate_new_room(
    title: str | None, mode: str | None, nickname: str | None
) -> tuple[dict[str, str], list[str]]:
    """Clean the create-room form and check it.

    Returns the cleaned values and a list of error messages (empty if the form is valid).
    """
    cleaned = {
        "title": clean_text(title),
        "mode": mode or "",
        "nickname": clean_text(nickname),
    }
    errors = []

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
