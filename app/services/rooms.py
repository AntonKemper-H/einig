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

    if not cleaned["nickname"]:
        errors.append("Please enter a nickname.")
    elif len(cleaned["nickname"]) > NICKNAME_MAX_LENGTH:
        errors.append(f"The nickname can be at most {NICKNAME_MAX_LENGTH} characters.")

    return cleaned, errors


def new_room_id() -> str:
    """Return a random, hard-to-guess room id (11 URL-safe characters, about 64 random bits)."""
    return secrets.token_urlsafe(8)


def new_session_token() -> str:
    """Return a random token that identifies one participant in their browser session."""
    return secrets.token_urlsafe(32)
