"""Rules for adding (specs/a4-add-options.md) and deleting options (specs/a7-delete-option.md)."""

LABEL_MAX_LENGTH = 80

NOT_COLLECTING_MESSAGE = "Options can only be added before voting starts."
DUPLICATE_MESSAGE = "This option is already in the list."

DELETE_NOT_COLLECTING_MESSAGE = "Options can only be deleted before voting starts."
DELETE_NOT_ALLOWED_MESSAGE = "Only the person who added this option or the creator can delete it."


def is_label_taken(label: str, existing_labels: list[str]) -> bool:
    """Return True if the label is already in the list, ignoring upper/lower case.

    Compared in Python with casefold(), like nicknames, because SQLite's
    lower() only handles the letters A-Z.
    """
    wanted = label.casefold()
    return any(existing.casefold() == wanted for existing in existing_labels)


def option_errors(label: str, room_status: str, existing_labels: list[str]) -> list[str]:
    """Check whether this cleaned label may be added to the room (F3).

    Returns at most one message: the first rule that fails. The route looks up
    the room status and the existing labels, so this function needs no database.
    """
    if room_status != "collecting":
        return [NOT_COLLECTING_MESSAGE]
    if not label:
        return ["Please enter an option."]
    if len(label) > LABEL_MAX_LENGTH:
        return [f"An option can be at most {LABEL_MAX_LENGTH} characters."]
    if is_label_taken(label, existing_labels):
        return [DUPLICATE_MESSAGE]
    return []


def may_delete(is_creator: bool, participant_id: int, added_by: int | None) -> bool:
    """F24: the creator may delete every option, anyone else only the options they added.

    Search results have no author (added_by is None), so only the creator may delete them.
    """
    return is_creator or (added_by is not None and added_by == participant_id)


def delete_error(
    room_status: str, is_creator: bool, participant_id: int, added_by: int | None
) -> tuple[str, int] | None:
    """Check whether this participant may delete this option now.

    Returns the message and the HTTP status code of the first rule that fails, or None.
    """
    if room_status != "collecting":
        return DELETE_NOT_COLLECTING_MESSAGE, 400
    if not may_delete(is_creator, participant_id, added_by):
        return DELETE_NOT_ALLOWED_MESSAGE, 403
    return None
