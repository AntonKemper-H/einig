"""Rules for fixed groups (A9, F16, specs/a9-groups.md). No Flask, no database."""

from app.services import rooms as room_rules

GROUP_NAME_MAX_LENGTH = 60
# A browser remembers at most this many groups, so the session cookie stays small
# next to the 30 rooms of A8 (browsers refuse cookies over about 4 KB).
MAX_REMEMBERED_GROUPS = 10


def validate_new_group(name: str | None, nickname: str | None) -> tuple[dict[str, str], list[str]]:
    """Clean the "create a group" form and check it.

    Returns the cleaned values and a list of error messages (empty if the form is valid).
    The nickname follows the same rules as a room nickname (A3).
    """
    cleaned = {"name": room_rules.clean_text(name), "nickname": room_rules.clean_text(nickname)}
    errors = []
    if not cleaned["name"]:
        errors.append("Please enter a group name.")
    elif len(cleaned["name"]) > GROUP_NAME_MAX_LENGTH:
        errors.append(f"The group name can be at most {GROUP_NAME_MAX_LENGTH} characters.")
    errors.extend(room_rules.nickname_errors(cleaned["nickname"]))
    return cleaned, errors


def join_group_errors(nickname: str, taken_nicknames: list[str]) -> list[str]:
    """Check an already cleaned nickname for joining a group: valid and not taken in the group."""
    errors = room_rules.nickname_errors(nickname)
    if not errors and room_rules.is_nickname_taken(nickname, taken_nicknames):
        errors.append("This nickname is already taken in this group.")
    return errors


def remember_group_token(tokens: dict[str, str], group_id: str, token: str) -> dict[str, str]:
    """Return a new dict with this group's token added or replaced; the given dict stays unchanged."""
    remembered = dict(tokens)
    remembered[group_id] = token
    return remembered


def groups_to_keep(groups: list[dict]) -> set[str]:
    """Return the ids of the MAX_REMEMBERED_GROUPS groups this browser joined most recently.

    Each group carries this browser's own member id in that group. Ids only grow, so a
    higher id was joined later. The order of the cookie cannot be used: Flask writes
    the session cookie with sorted keys (the same reason as rooms_to_keep in A8).
    """
    newest_first = sorted(groups, key=lambda group: group["member_id"], reverse=True)
    return {group["id"] for group in newest_first[:MAX_REMEMBERED_GROUPS]}
