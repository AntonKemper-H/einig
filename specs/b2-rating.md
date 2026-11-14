# B2 – F4 Three-level rating

Branch: `feature-b2-rating`
Tests: `tests/test_rating.py`

## Why

The app only works if every participant can rate every option quickly on a phone, without seeing how the others voted. This task lets a participant rate the room's options one card at a time on three levels and saves the ratings in the shape the winner algorithm (B1, `services/scoring.py`) already expects. The result page follows in B3.

## What

Rules from `docs/concept.md` F4, `AGENTS.md` (Rules for simultaneous actions, Rejected actions, Identity and access, Individual votes are private, Mobile and PWA) and `docs/decisions.md` D11.

Pages and form:

- `GET /rooms/<room_id>/vote` – the rating page for the participant whose token is in the session.
- `POST /rooms/<room_id>/vote` – form fields `option_id` (a hidden field on each card) and `rating` (the value of the pressed button) (`"yes"`, `"ok"` or `"no"`); on success it redirects (303) to `GET /rooms/<room_id>/vote` (Post/Redirect/Get).
- Button labels: `"yes"` → "Rather yes", `"ok"` → "Fine with me", `"no"` → "Rather not".
- Options to rate are the room's options with `is_replaced = 0` (F13 marks replaced ones later).

Pure helpers in `app/services/voting.py` (type hints, no Flask, no database):

- `RATING_LABELS = {"yes": "Rather yes", "ok": "Fine with me", "no": "Rather not"}`
- `rating_order(option_ids, seed) -> list[int]` – the participant's own random order
- `next_option_to_rate(order, rated_option_ids) -> int | None` – first option in the order that is not rated yet
- `vote_errors(room_status, rating, option_id, rateable_option_ids) -> list[str]` – messages for a rejected vote (empty list = accepted)

Must be true (one line = one test):

### Accepted
- [ ] While the room status is `voting`, a participant's rating is saved as one row in `votes` (room, participant, option, rating), and the response redirects to the rating page.
- [ ] Rating the same option again replaces the earlier rating: still one row, with the new value (`AGENTS.md`, simultaneous actions).
- [ ] The rating page shows exactly one option card (the next unrated option) with the three buttons "Rather yes", "Fine with me", "Rather not".
- [ ] After a rating, the page shows the next unrated option in the participant's order.
- [ ] When every option is rated, the page says "You have rated all options." and lists every option with the participant's own rating ("Your rating: …") and the buttons to change it.
- [ ] When the participant has rated every option, `participants.has_finished` becomes 1 (the lobby, A5, shows who is done). Changing a rating afterwards keeps it at 1.
- [ ] `db.get_votes(room_id)` returns the saved ratings in the shape `score_options` / `pick_winner` take (`{participant_id: {option_id: rating}}`), so B3 can call B1 without converting.

### Random order (F4)
- [ ] `rating_order` returns every option id exactly once.
- [ ] The same seed always gives the same order, so a reload does not reshuffle the cards.
- [ ] Different seeds give different orders (with 6 options, more than one order appears across 50 seeds), so the first card is not the same for everyone.
- [ ] On the page, the order is stable for a participant across reloads; the seed is the participant's session token, which nobody else knows.
- [ ] `next_option_to_rate` returns the first unrated option in the order, and `None` when all are rated.

### Rejected (message shown, saved data unchanged)
- [ ] Room status `collecting`: "Voting has not started yet." (status 400 for POST; the GET page shows the message instead of a card), no row saved.
- [ ] Room status `closed`: "This room is closed. You can no longer vote." (status 400 for POST; shown on the GET page), no row saved, an earlier rating is not changed.
- [ ] A rating that is not `yes` / `ok` / `no`, or no rating at all: "Please choose one of the three ratings." (400), no row saved.
- [ ] An option id that is not a rateable option of this room (another room's option, a replaced option, an unknown id, not a number, missing): "This option does not exist in this room." (400), no row saved, no crash.
- [ ] A visitor without a participant token for this room: POST is rejected with status 403 and nothing is saved; GET redirects (303) to the room page, where the join form is.
- [ ] A token of a participant of *another* room counts as no token here (403, nothing saved).
- [ ] Unknown room: 404 for GET and POST.

### Privacy
- [ ] A participant's rating page never shows another participant's rating: after P1 rates, P2's page contains no "Your rating" for that option, and no page shows rating counts.

### Persistence
- [ ] After a restart (a new app object on the same database), saved ratings and `has_finished` are still there, and the rating page continues with the next unrated option.

### Code rules
- [ ] `services/voting.py` imports neither Flask nor `app.db` nor `requests`.
- [ ] `db.save_vote(room_id, participant_id, option_id, rating)` inserts or updates in one statement (`INSERT … ON CONFLICT (participant_id, option_id) DO UPDATE SET rating = excluded.rating`, works on SQLite and Postgres). So if another request saved a row for the same option a moment earlier, it updates that row instead of failing: two simultaneous clicks end in one row.

## Out of scope

- **Starting the rating phase** (switching the room from `collecting` to `voting`). No task in `docs/plan.md` owns it yet; the tests set the status directly in the database, like `tests/test_join.py` does. Open question for the team (see PR).
- Adding options (A4): the tests insert options directly in the database.
- Linking the room page or lobby to the rating page (A5).
- The result page and closing the room (B3), the joker / veto (B4), the deadline (B5).
- Swipe gestures or any JavaScript (`AGENTS.md`: buttons, no JS).
- Google place names and photos on the cards (C2): the card shows the manual `label`; a Google option shows a placeholder text until C2.

## Done when

- All tests in `tests/test_rating.py` and all earlier tests pass (`uv run pytest`), output pasted.
- On a phone-sized screen, a participant can rate every option of a room in `voting` status and sees "You have rated all options." at the end.
- A rejected vote shows its message and changes nothing.
- Accepted ratings survive an app restart.
- Work is on branch `feature-b2-rating`, pushed, pull request opened and reviewed by Track A (review circle).
