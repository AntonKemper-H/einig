"""Rules for closing a room and for the result page (spec: specs/b3-result.md).

Pure functions only: plain Python data in, plain Python data out, so the rules
can be tested without Flask or the database. Choosing the winner itself is
services/scoring.py (B1).
"""

ONLY_CREATOR_MESSAGE = "Only the creator can close the room."
NOT_STARTED_MESSAGE = "Voting has not started yet."


def close_errors(is_creator: bool, room_status: str) -> tuple[int, str] | None:
    """Return (HTTP status, message) if this participant may not close the room now, else None.

    The creator check comes first, so a non-creator always gets the same answer,
    whatever the status. A room that is already closed is not an error: the
    route just shows the existing result (closing is idempotent).
    """
    if not is_creator:
        return 403, ONLY_CREATOR_MESSAGE
    if room_status == "collecting":
        return 400, NOT_STARTED_MESSAGE
    return None


def rating_counts(
    option_ids: list[int], votes: dict[int, dict[int, str]]
) -> dict[int, dict[str, int]]:
    """Count per option how many participants actually pressed "yes", "ok" and "no".

    Only real ratings are counted. An unrated option counts as "ok" inside the
    score (D11), but showing it here would claim that people pressed a button
    they never pressed. Ratings for options not in option_ids are ignored.
    """
    counts = {option_id: {"yes": 0, "ok": 0, "no": 0} for option_id in option_ids}
    for ratings in votes.values():
        for option_id, rating in ratings.items():
            if option_id in counts and rating in counts[option_id]:
                counts[option_id][rating] += 1
    return counts


def veto_counts(option_ids: list[int], vetoed_option_ids: list[int]) -> dict[int, int]:
    """Count per option how many jokers it got (F10). 0 for options without one.

    Jokers on ids that are not in option_ids are ignored. Only numbers leave this
    function, never who used a joker (AGENTS.md: individual votes are private).
    """
    return {option_id: vetoed_option_ids.count(option_id) for option_id in option_ids}


def every_option_vetoed(option_ids: list[int], vetoed_option_ids: list[int]) -> bool:
    """True if there is at least one option and each one got at least one joker.

    Then the winner is the option with the fewest jokers (B1), and the result
    page says so, because otherwise a vetoed winner would look like a mistake.
    """
    vetoed = set(vetoed_option_ids)
    return bool(option_ids) and all(option_id in vetoed for option_id in option_ids)
