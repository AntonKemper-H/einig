"""Winner algorithm (spec: specs/b1-scoring.md).

Pure functions only: plain Python data in, plain Python data out. No Flask,
no database, no network, so the rules can be tested on their own.
"""

import random

# Points per rating. A "no" weighs much more than a "yes", because the goal is
# the option everyone can live with, not the one most people like.
POINTS = {"yes": 2, "ok": 1, "no": -4}

# D11: an option a voter did not rate counts as this rating.
UNRATED = "ok"


def _voters(option_ids: list[int], votes: dict[int, dict[int, str]]) -> list[dict[int, str]]:
    """Return the ratings of everyone who counts as a voter, limited to known options.

    Raises ValueError for a rating that is not in POINTS.
    """
    known = set(option_ids)
    voters = []
    for ratings in votes.values():
        for rating in ratings.values():
            if rating not in POINTS:
                raise ValueError(f"Unknown rating: {rating!r}")
        # Ratings for options that are not in the room are ignored. Someone who
        # rated only such options has rated nothing here, so is not a voter (D11).
        known_ratings = {option_id: rating for option_id, rating in ratings.items() if option_id in known}
        if known_ratings:
            voters.append(known_ratings)
    return voters


def _rating(voter: dict[int, str], option_id: int) -> str:
    """The voter's rating for an option; a missing rating counts as "ok" (D11), never as a veto."""
    return voter.get(option_id, UNRATED)


def score_options(option_ids: list[int], votes: dict[int, dict[int, str]]) -> dict[int, int]:
    """Return the score of every option: the sum of the points of every voter's rating."""
    voters = _voters(option_ids, votes)
    # Every voter's weight is 1 (fairness weights are parked, concept §6.3).
    return {
        option_id: sum(POINTS[_rating(voter, option_id)] for voter in voters)
        for option_id in option_ids
    }


def pick_winner(
    option_ids: list[int],
    votes: dict[int, dict[int, str]],
    vetoed_option_ids: list[int],
    rng: random.Random | None = None,
) -> int | None:
    """Return the id of the winning option, or None if there is no winner.

    Order: options without a veto first (if every option has one, fewest vetoes),
    then best score, fewer "no", more "yes", and finally a random choice.
    """
    voters = _voters(option_ids, votes)
    if not option_ids or not voters:
        return None

    scores = score_options(option_ids, votes)
    # Vetoes for options that are not in the room are simply never counted.
    veto_counts = {option_id: vetoed_option_ids.count(option_id) for option_id in option_ids}
    no_counts = {
        option_id: sum(_rating(voter, option_id) == "no" for voter in voters) for option_id in option_ids
    }
    yes_counts = {
        option_id: sum(_rating(voter, option_id) == "yes" for voter in voters) for option_id in option_ids
    }

    # Fewest vetoes covers both cases: if some option has none, every vetoed
    # option ranks below it (= excluded); if all have one, fewest vetoes wins.
    def rank(option_id: int) -> tuple[int, int, int, int]:
        """Higher is better; compared element by element."""
        return (-veto_counts[option_id], scores[option_id], -no_counts[option_id], yes_counts[option_id])

    best_rank = max(rank(option_id) for option_id in option_ids)
    tied = [option_id for option_id in option_ids if rank(option_id) == best_rank]
    # The "more yes" step stays in rank() because AGENTS.md and concept §6.2 name it,
    # even though with weight 1 it cannot decide on its own (see the spec note).
    if len(tied) == 1:
        return tied[0]
    # Sort so the random choice does not depend on the order of option_ids.
    return (rng or random.Random()).choice(sorted(tied))
