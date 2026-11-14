"""Rules for adding options manually (spec: specs/a4-add-options.md)."""

LABEL_MAX_LENGTH = 80


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
        return ["Options can only be added before voting starts."]
    if not label:
        return ["Please enter an option."]
    if len(label) > LABEL_MAX_LENGTH:
        return [f"An option can be at most {LABEL_MAX_LENGTH} characters."]
    if is_label_taken(label, existing_labels):
        return ["This option is already in the list."]
    return []
