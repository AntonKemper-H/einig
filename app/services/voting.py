"""Rules for the three-level rating (spec: specs/b2-rating.md) and the joker (specs/b4-joker.md).

Pure functions only: plain Python data in, plain Python data out. The route
looks up the room, the options and the ratings, so nothing here needs Flask
or the database.
"""

import random

# The three levels, in the order the buttons are shown. The keys are what the
# database and the winner algorithm (services/scoring.py) store.
RATING_LABELS = {"yes": "Rather yes", "ok": "Fine with me", "no": "Rather not"}

NOT_STARTED_MESSAGE = "Voting has not started yet."
CLOSED_MESSAGE = "This room is closed. You can no longer vote."
INVALID_RATING_MESSAGE = "Please choose one of the three ratings."
UNKNOWN_OPTION_MESSAGE = "This option does not exist in this room."
JOKER_USED_MESSAGE = "You have already used your joker in this room."


def rating_order(option_ids: list[int], seed: str) -> list[int]:
    """Return the participant's own random order of the options (F4).

    Sorting first makes the result independent of the order the ids come in.
    The seed is the session token as a string: random.Random(str) gives the same
    order in every Python process, while hash(str) changes with each process,
    so a hash-based seed would reshuffle the cards after a restart.
    """
    order = sorted(option_ids)
    random.Random(seed).shuffle(order)
    return order


def next_option_to_rate(order: list[int], rated_option_ids: set[int]) -> int | None:
    """Return the first option in the order that is not rated yet, or None if all are rated."""
    for option_id in order:
        if option_id not in rated_option_ids:
            return option_id
    return None


def has_rated_all(rateable_option_ids: list[int], rated_option_ids: set[int]) -> bool:
    """True if the participant rated every option there is to rate (and there is at least one)."""
    return bool(rateable_option_ids) and set(rateable_option_ids) <= rated_option_ids


def vote_errors(
    room_status: str, rating: str | None, option_id: int | None, rateable_option_ids: list[int]
) -> list[str]:
    """Check a submitted rating. Returns at most one message: the first rule that fails.

    The room status comes first, so a vote in a closed room is always answered
    with "closed", whatever else is wrong with the form.
    """
    if room_status == "collecting":
        return [NOT_STARTED_MESSAGE]
    if room_status != "voting":
        # "closed", and any status a later task might add: no voting outside "voting".
        return [CLOSED_MESSAGE]
    if rating not in RATING_LABELS:
        return [INVALID_RATING_MESSAGE]
    if option_id not in rateable_option_ids:
        return [UNKNOWN_OPTION_MESSAGE]
    return []


def veto_errors(
    room_status: str, option_id: int | None, rateable_option_ids: list[int], own_veto: int | None
) -> list[str]:
    """Check a joker (F10, specs/b4-joker.md). Returns at most one message: the first rule that fails.

    Same order idea as vote_errors: the room status first, so a joker in a closed
    room is always answered with "closed". "Already used" comes before the option
    check, because a used joker is final whatever option is posted.
    """
    if room_status == "collecting":
        return [NOT_STARTED_MESSAGE]
    if room_status != "voting":
        return [CLOSED_MESSAGE]
    if own_veto is not None:
        return [JOKER_USED_MESSAGE]
    if option_id not in rateable_option_ids:
        return [UNKNOWN_OPTION_MESSAGE]
    return []


def parse_option_id(raw_value: str | None) -> int | None:
    """Turn the hidden form field into an option id; anything that is not a whole number gives None."""
    value = (raw_value or "").strip()
    # isascii(): isdigit() alone also accepts characters like "²", which int() rejects.
    if not (value.isascii() and value.isdigit()):
        return None
    return int(value)
