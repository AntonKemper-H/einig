# B4 – F10 Joker / veto

Branch: `feature-b4-joker`
Tests: `tests/test_joker.py`

## Why

Rating alone can let the group pick a place that one person really cannot go to (an allergy, a place they hate, too far). The joker gives every participant one strong "not this one" per room, so nobody is outvoted on something that matters a lot to them, while the group still decides everything else together.

## What

Rules from `docs/concept.md` F10, `AGENTS.md` (Winner algorithm, Rules for simultaneous actions: "Veto: at most one per participant and room (unique constraint). A second attempt is rejected with a message.", Rejected actions, Identity and access, Individual votes are private) and `docs/decisions.md` D11 ("a missing rating is never a veto").

The winner algorithm already respects vetoes (B1, `pick_winner(..., vetoed_option_ids, ...)`), and closing already reads them (B3, `db.get_vetoed_option_ids`). B4 adds the way to **use** the joker and shows its effect.

### Decisions in this spec (please check in the review)

- **One joker per participant and room, final.** It cannot be taken back or moved to another option. `AGENTS.md` says a second attempt is rejected, and a joker that can be moved around invites tactics late in the voting. The button says so: "Use my joker on this option (cannot be undone)". No JavaScript confirm dialog (not allowed).
- **Only while the room is `voting`.** Before voting starts there is nothing to veto yet; after closing the result is fixed.
- **The joker is not a rating.** Using it does not rate the option, and the option stays on the rating page so the participant can still rate it (that rating only matters if every option gets a joker, because then the score decides between the fewest-joker options). A participant who used a joker but rated nothing is not a voter (D11), but their joker still counts.
- **Privacy:** nobody sees who used a joker on what. The rating page shows a participant only their own joker; the result page shows only an anonymous count per option.
- **Same lock as voting.** Saving a joker first locks the room row (`UPDATE rooms SET status = status WHERE id = ? AND status = 'voting'`, as `save_vote` does in B3), so a joker and a close never overlap: a joker that comes after the close is not saved.

### Pages and forms

- `POST /rooms/<room_id>/veto` with a hidden `option_id` – use the joker; on success redirect (303) to `GET /rooms/<room_id>/vote` (Post/Redirect/Get).
- Rating page (`/rooms/<room_id>/vote`, B2), while `voting`:
  - Joker not used yet: every shown option card (the single next card, and every card in the overview) has its own small form posting to `/rooms/<room_id>/veto` with that card's `option_id` and the button "Use my joker on this option (cannot be undone)". It is a separate form below the rating buttons, its button has **no** `name="rating"`, and it is not inside the rating form (so the A10 swipe, which looks for `button[name="rating"]`, never presses it).
  - Joker used: no joker form anywhere on the page, and the text "You used your joker on: <option label>".
- Result page (`/rooms/<room_id>/result`, B3), closed room:
  - Each option with at least one joker shows "excluded by N× joker" next to its counts (anonymous number only).
  - If every rateable option got at least one joker and there is a winner: "Every option got a joker, so the option with the fewest jokers won."

### Pure helpers (no Flask, no database)

In `app/services/voting.py`:
- `JOKER_USED_MESSAGE = "You have already used your joker in this room."`
- `veto_errors(room_status, option_id, rateable_option_ids, own_veto) -> list[str]` – at most one message, the first rule that fails, in this order: `collecting` → "Voting has not started yet."; any other status that is not `voting` → "This room is closed. You can no longer vote."; `own_veto` is not `None` → `JOKER_USED_MESSAGE`; `option_id` not in `rateable_option_ids` → "This option does not exist in this room."; otherwise `[]`.

In `app/services/results.py`:
- `veto_counts(option_ids, vetoed_option_ids) -> dict[int, int]` – per option in `option_ids`, how many jokers it got (0 if none); jokers on other ids are ignored.
- `every_option_vetoed(option_ids, vetoed_option_ids) -> bool` – `True` if there is at least one option and each of them has at least one joker.

### Database (`app/db.py`)

- `get_own_veto(room_id, participant_id) -> int | None` – the option id this participant used their joker on, or `None`.
- `save_veto(room_id, participant_id, option_id) -> bool` – call inside `db.transaction()`. First the room-row lock above; if it changes no row (room not `voting` any more), return `False` and insert nothing. Otherwise insert the veto and return `True`. The `bool` comes from `cursor.rowcount` of the `UPDATE`. A second veto by the same participant breaks `UNIQUE (participant_id, room_id)` and raises one of `db.INTEGRITY_ERRORS`; the route turns that into `JOKER_USED_MESSAGE` (two presses at the same moment end with exactly one joker).

No schema change: the `vetoes` table exists since A1.

### Must be true (one line = one test)

#### Using the joker (accepted)
- [ ] A participant uses the joker on an option while `voting`: one row in `vetoes` (room, participant, option), response 303 to `/rooms/<room_id>/vote`.
- [ ] Afterwards the rating page shows "You used your joker on: Pizza" and no form posting to `/veto`.
- [ ] Using the joker does not rate: the participant's ratings are unchanged and the option is still shown to rate (or with its rating in the overview).
- [ ] Two participants can each use their joker, also on the same option (two rows).
- [ ] Using the joker does not change the "done" flag (`has_finished`, shown in the lobby); only rating every option does (B2).

#### Using the joker (rejected, nothing changes)
- [ ] A second joker by the same participant, on the same or another option: "You have already used your joker in this room." (400), still exactly one row, on the first option.
- [ ] Two presses at the same moment (simulated: the route's check sees no joker yet, the database already has one): the `UNIQUE` constraint keeps one row, the response is 400 with `JOKER_USED_MESSAGE`, no crash.
- [ ] In a `collecting` room: "Voting has not started yet." (400), no row.
- [ ] In a `closed` room: "This room is closed. You can no longer vote." (400), no row.
- [ ] A joker that passes the route's status check but reaches the database after the room was closed (simulated): not saved, closed message (400), `save_veto` returns `False`.
- [ ] Unknown option id, an option of another room, a replaced option ("Been there", `is_replaced = 1`), and a non-number `option_id`: "This option does not exist in this room." (400), no row.
- [ ] A visitor without a token and a participant of another room: 403, no row.
- [ ] Unknown room: 404.

#### Rating page
- [ ] Joker not used: the single next card has a joker form posting to `/rooms/<room_id>/veto` with that card's `option_id`; the joker button has no `name="rating"` and sits outside the rating form.
- [ ] Joker not used, overview (everything rated): every card has its own joker form with its own `option_id`.
- [ ] The rating page never shows other participants' jokers: after Ben uses his joker, Anna's page shows her joker form as unused and no "You used your joker" text.
- [ ] No joker form while the room is `collecting` or `closed`.

#### Effect on the result (closing, B3)
- [ ] An option with a joker is not chosen, even with the best score: the stored winner is the best option without a joker.
- [ ] Every option has a joker: the option with the fewest jokers wins; among equal numbers, the best score.
- [ ] A participant who only used a joker and rated nothing: their joker still excludes the option (and they are not a voter, D11).

#### Result page
- [ ] A vetoed option shows "excluded by 1× joker" (with two jokers "excluded by 2× joker"); an option without a joker shows no "excluded" text.
- [ ] Every option vetoed: the page shows "Every option got a joker, so the option with the fewest jokers won." It is not shown when at least one option has no joker.
- [ ] Every option vetoed but nobody rated anything: there is no winner, so the page shows "No winner: nobody rated any option." and **not** the joker note.
- [ ] No nickname appears on the result page, also with jokers (only counts).

#### Helpers
- [ ] `veto_errors` returns the messages in the order above (status first, then "already used", then unknown option), and `[]` for a valid joker.
- [ ] `veto_counts` counts per option, gives 0 for options without a joker and ignores ids that are not in the list.
- [ ] `every_option_vetoed` is `True` only if every option has a joker, and `False` for an empty list.
- [ ] `get_own_veto` returns the option id after a joker and `None` before.

#### Persistence
- [ ] After a restart (a new app object on the same database), the joker is still there: the rating page still says "You used your joker on: …" and a second joker is still rejected.

#### Code rules
- [ ] `app/services/voting.py` and `app/services/results.py` still import no Flask, `requests` or `app.db`.

## Follow-up with B5 (deadline, `specs/b5-deadline.md`)

B5 was merged first, so B4 adds what B5's spec asks of "whichever is merged second". Tests: `tests/test_joker_deadline.py`.

- `save_veto(room_id, participant_id, option_id, now: str | None = None) -> bool`: the room-row lock gets the same deadline condition as `save_vote` (`AND (deadline IS NULL OR deadline > ?)`, `now` as UTC text, `None` → server time). After the deadline it saves nothing and returns `False`.
- The joker route calls `close_if_time_is_up` right after loading the room, like the other routes of B5.

Must be true (one line = one test):
- [ ] A joker before the deadline is saved (303).
- [ ] A joker sent after the deadline (room still `voting` in the database): "This room is closed. You can no longer vote." (400), no joker saved, and the room is `closed` afterwards.
- [ ] A joker that passes the route's check (simulated: the route still sees a deadline in the future) but reaches the database after the deadline: not saved, 400 with the closed message.
- [ ] `save_veto` with `now` before the deadline saves and returns `True`; with `now` equal to or after the deadline it saves nothing and returns `False`.

The two B4 tests that used the jokers after the last ratings (`test_vetoed_option_is_not_chosen`, `test_every_option_vetoed_fewest_jokers_then_best_score`) now use them before, because B5 closes the room after the last rating. No assertion changes; this needs the reviewer's OK (`AGENTS.md`).

## Out of scope

- Taking a joker back or moving it (decided above: final).
- More than one joker per person, or jokers that depend on the group size.
- Showing anyone who used a joker, or a joker count anywhere before the room is closed (lobby, rating page of others).
- The deadline (B5) and closing automatically.
- Changes to `app/schema.sql`, to `services/scoring.py`, or to existing tests.
- Any JavaScript (also no confirm dialog).

## Done when

- All tests in `tests/test_joker.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network.
- SQL only in `app/db.py`, rules in `app/services/`, thin route, Jinja templates, no JavaScript.
- Work is on branch `feature-b4-joker`, pushed, pull request opened with AntonKemper-H as reviewer (D10: A reviews B).
