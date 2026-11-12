# B1 – F5 Winner algorithm

Branch: `feature-b1-scoring`
Tests: `tests/test_scoring.py`

## Why

The app's promise is to pick the option everyone can live with, not the one most people like. This task builds that decision as pure functions in `app/services/scoring.py`, so it can be tested on its own before the rating (B2) and result (B3) pages exist.

## What

Rules from `docs/concept.md` §6, `AGENTS.md` (Winner algorithm) and `docs/decisions.md` D11.

Input is plain Python data, the same shape the database will deliver:

- `option_ids: list[int]` – all options of the room
- `votes: dict[int, dict[int, str]]` – participant id → {option id → rating}, rating is `"yes"`, `"ok"` or `"no"`
- `vetoed_option_ids: list[int]` – one entry per veto (the same option can appear more than once)
- `rng: random.Random | None` – only used for the last tie-break; tests pass a seeded one

Functions:

- `score_options(option_ids, votes) -> dict[int, int]` – score per option
- `pick_winner(option_ids, votes, vetoed_option_ids, rng=None) -> int | None` – winning option id, or `None` if there is no winner

Must be true (one line = one test):

- [ ] `POINTS == {"yes": 2, "ok": 1, "no": -4}` as a module-level constant.
- [ ] Score = sum of the points of every voter's rating for that option.
- [ ] D11: a participant who rated at least one option is a voter; every option this voter did not rate counts as "ok" (+1).
- [ ] D11: a participant who rated no option is not counted.
- [ ] D11 example: A rated only by P1 ("yes"), B rated "ok" by P1–P3 → A = 4, B = 3, A wins.
- [ ] §6.4: A 3× yes + 1× no, B 4× ok → A = 2, B = 4, B wins.
- [ ] §6.4: same score, A has one "no", B has none → B wins.
- [ ] Full tie → random choice; with the same seeded `rng` the result is always the same, and across seeds each tied option can win.
- [ ] An option with at least one veto is excluded, even if it has the highest score.
- [ ] §6.4: every option has a veto → fewest vetoes wins, then best score.
- [ ] §6.4: only one person voted → their best option wins.
- [ ] §6.4: nobody voted → `None`.
- [ ] A room without options → `None`.
- [ ] A missing rating is never a veto.
- [ ] Rejected: an unknown rating value raises `ValueError`.
- [ ] Ratings for an option id that is not in `option_ids` are ignored.
- [ ] The functions do not change the data passed in.
- [ ] `scoring.py` does not import Flask, `app.db` or `requests`.

(No "survives a restart" line: these functions store nothing.)

**Note for review – the "more yes" tie-break can never decide.** With D11 every voter counts for every option, and every weight is 1. So for n voters an option's score is `n + yes − 5 × no`. Two options with the same score and the same number of "no" therefore always have the same number of "yes", and the order goes straight from "fewer no" to random. The code keeps the "more yes" step because `AGENTS.md` and `concept.md` §6.2 name it (it would matter if fairness weights come back), but no test can reach it, so there is no line for it above. Team: keep it, or drop it from the rules?

## Out of scope

- No database access, routes, templates or forms (B2 rating, B3 result page).
- No veto or deadline handling in the app (B4, B5) – the function only receives the vetoes.
- No fairness weights (§6.3, parked F14–F21): every voter counts the same, no weight parameter.
- No message text for "no winner" – the result page (B3) shows it.

## Done when

- All tests in `tests/test_scoring.py` pass (`uv run pytest`), output pasted.
- `app/services/scoring.py` follows the coding conventions in `AGENTS.md` (type hints, short docstrings, comments on the why).
- Work is on branch `feature-b1-scoring`, pushed, pull request opened and reviewed by Track A (review circle).
