"""Tests for the winner algorithm (spec: specs/b1-scoring.md)."""

import ast
import copy
import random
from pathlib import Path

import pytest

from app.services.scoring import POINTS, pick_winner, score_options

A, B, C = 1, 2, 3
SCORING_FILE = Path(__file__).resolve().parents[1] / "app" / "services" / "scoring.py"


# --- Points and scores -------------------------------------------------------


def test_points_are_module_constants():
    assert POINTS == {"yes": 2, "ok": 1, "no": -4}


def test_score_is_sum_of_points():
    votes = {10: {A: "yes", B: "no"}, 11: {A: "ok", B: "yes"}}
    assert score_options([A, B], votes) == {A: 3, B: -2}


def test_unrated_option_counts_as_ok_for_a_voter():
    # D11: P10 rated only A, so B counts as "ok" for P10.
    votes = {10: {A: "yes"}, 11: {A: "no", B: "no"}}
    assert score_options([A, B], votes) == {A: -2, B: -3}


def test_participant_without_ratings_is_not_counted():
    votes = {10: {A: "yes", B: "ok"}, 11: {}}
    assert score_options([A, B], votes) == {A: 2, B: 1}


def test_d11_example():
    votes = {10: {A: "yes", B: "ok"}, 11: {B: "ok"}, 12: {B: "ok"}}
    assert score_options([A, B], votes) == {A: 4, B: 3}
    assert pick_winner([A, B], votes, []) == A


# --- Winner (concept §6.4) ---------------------------------------------------


def test_option_everyone_can_live_with_beats_one_with_a_no():
    votes = {
        10: {A: "yes", B: "ok"},
        11: {A: "yes", B: "ok"},
        12: {A: "yes", B: "ok"},
        13: {A: "no", B: "ok"},
    }
    assert score_options([A, B], votes) == {A: 2, B: 4}
    assert pick_winner([A, B], votes, []) == B


def test_tie_fewer_no_wins():
    # A = 5 x yes + 1 x no = 6, B = 6 x ok = 6. Same score, B has no "no".
    votes = {10 + i: {A: "yes", B: "ok"} for i in range(5)}
    votes[15] = {A: "no", B: "ok"}
    assert score_options([A, B], votes) == {A: 6, B: 6}
    # Seeded rng and both option orders, so neither luck nor "first option wins" can pass.
    for seed in range(20):
        assert pick_winner([A, B], votes, [], rng=random.Random(seed)) == B
        assert pick_winner([B, A], votes, [], rng=random.Random(seed)) == B


def test_full_tie_is_random_but_reproducible_with_seed():
    votes = {10: {A: "yes", B: "yes"}}
    first = pick_winner([A, B], votes, [], rng=random.Random(42))
    for _ in range(5):
        assert pick_winner([A, B], votes, [], rng=random.Random(42)) == first
    winners = {pick_winner([A, B], votes, [], rng=random.Random(seed)) for seed in range(50)}
    assert winners == {A, B}


def test_vetoed_option_is_excluded_even_with_best_score():
    votes = {10: {A: "yes", B: "ok"}, 11: {A: "yes", B: "ok"}}
    assert pick_winner([A, B], votes, [A]) == B


def test_all_vetoed_fewest_vetoes_wins():
    votes = {10: {A: "yes", B: "no"}, 11: {A: "yes", B: "no"}}
    assert pick_winner([A, B], votes, [A, A, B]) == B


def test_all_vetoed_same_veto_count_best_score_wins():
    votes = {10: {A: "yes", B: "no"}, 11: {A: "yes", B: "ok"}}
    assert pick_winner([A, B], votes, [A, B]) == A


def test_only_one_person_voted_their_best_option_wins():
    votes = {10: {A: "ok", B: "yes", C: "no"}}
    assert pick_winner([A, B, C], votes, []) == B


def test_nobody_voted_no_winner():
    assert pick_winner([A, B], {}, []) is None
    assert pick_winner([A, B], {10: {}, 11: {}}, []) is None


def test_room_without_options_no_winner():
    assert pick_winner([], {10: {}}, []) is None


def test_missing_rating_is_never_a_veto():
    # P11 did not rate A; A must still be able to win.
    votes = {10: {A: "yes", B: "ok"}, 11: {B: "ok"}}
    assert pick_winner([A, B], votes, []) == A


# --- Rejected and unusual input ----------------------------------------------


def test_unknown_rating_raises_value_error():
    with pytest.raises(ValueError):
        score_options([A], {10: {A: "maybe"}})
    with pytest.raises(ValueError):
        pick_winner([A], {10: {A: "maybe"}}, [])


def test_rating_for_unknown_option_is_ignored():
    votes = {10: {A: "yes", 99: "no"}}
    assert score_options([A], votes) == {A: 2}
    assert pick_winner([A], votes, []) == A


def test_participant_with_only_unknown_option_ratings_is_not_a_voter():
    # P11 rated only option 99, which is not in the room. If P11 counted as a
    # voter, B would get +1 ("ok") and the scores would be A = 3, B = 2.
    votes = {10: {A: "yes"}, 11: {99: "no"}}
    assert score_options([A, B], votes) == {A: 2, B: 1}


def test_veto_for_unknown_option_is_ignored():
    # The vetoes for 99 must neither exclude anything nor make "every option
    # has a veto" true: A is vetoed, B is not, so B wins.
    votes = {10: {A: "yes", B: "ok"}}
    assert pick_winner([A, B], votes, [A, 99, 99]) == B
    assert pick_winner([A, B], votes, [99]) == A


def test_input_data_is_not_changed():
    option_ids = [A, B]
    votes = {10: {A: "yes"}, 11: {}}
    vetoes = [B]
    before = copy.deepcopy((option_ids, votes, vetoes))
    score_options(option_ids, votes)
    pick_winner(option_ids, votes, vetoes, rng=random.Random(1))
    assert (option_ids, votes, vetoes) == before


def test_scoring_module_has_no_forbidden_imports():
    # Path from this test file, so the test works from any working directory.
    source = SCORING_FILE.read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # scoring.py never needs a relative import, and one could hide app.db.
            assert node.level == 0, f"relative import on line {node.lineno}"
            imported.add(node.module)
            # "from app import db" names the module only through the alias.
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    for name in imported:
        assert name.split(".")[0] not in {"flask", "requests"}, name
        assert name != "app.db" and not name.startswith("app.db."), name
