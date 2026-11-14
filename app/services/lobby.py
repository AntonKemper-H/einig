"""Rules for the lobby and for starting the voting (spec: specs/a5-lobby.md)."""

# A decision needs at least two things to choose from.
MIN_OPTIONS_TO_START = 2

STATUS_TEXTS = {
    "collecting": "Collecting options.",
    "voting": "Voting has started.",
    "closed": "This room is closed.",
}

ALREADY_STARTED_MESSAGE = "Voting has already started."


def status_text(room_status: str) -> str:
    """Return the sentence the lobby shows for this room status ("" for an unknown one).

    The fallback keeps the lobby working if a later task adds a new status.
    """
    return STATUS_TEXTS.get(room_status, "")


def start_errors(room_status: str, option_count: int) -> list[str]:
    """Check whether the creator may start the voting now (F7, A5).

    Returns at most one message: the first rule that fails. The route checks
    first that the person is the creator, so this function only looks at the room.
    """
    if room_status == "voting":
        return [ALREADY_STARTED_MESSAGE]
    if room_status == "closed":
        return ["This room is closed."]
    if option_count < MIN_OPTIONS_TO_START:
        return [f"Add at least {MIN_OPTIONS_TO_START} options before starting the voting."]
    return []
