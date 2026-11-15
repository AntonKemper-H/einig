# B3 – F6 Close the room and show the result

Branch: `feature-b3-result`
Tests: `tests/test_result.py`

## Why

The group came to decide something, so the app has to end the voting and show one clear winner, plus an anonymous picture of how the options were rated. The winner is worked out once, when the room closes, and stored, so everyone sees the same result and reloading never changes it.

## What

Rules from `docs/concept.md` F6 and §6, `AGENTS.md` (Rules for simultaneous actions, Rejected actions, Identity and access, Individual votes are private, Privacy), `docs/decisions.md` D11 and D12, and the B1 algorithm in `services/scoring.py`.

Pages and forms:

- `POST /rooms/<room_id>/close` – the creator closes the room; on success it redirects (303) to `GET /rooms/<room_id>/result` (Post/Redirect/Get).
- `GET /rooms/<room_id>/result` – the result page.
- The rating page (`/rooms/<room_id>/vote`, B2) shows the creator a "Close the room and show the result" button while the room is `voting`, and everyone a "See the result" link once it is `closed`.

Pure helpers in `app/services/results.py` (type hints, no Flask, no database):

- `close_errors(is_creator, room_status) -> tuple[int, str] | None` – (HTTP status, message) if closing is not allowed, else `None`.
- `rating_counts(option_ids, votes) -> dict[int, dict[str, int]]` – per option, how many participants actually pressed "yes", "ok" and "no" (unrated options are not counted here; they only count as "ok" inside the score, D11).

Database (`app/db.py`):

- `get_vetoed_option_ids(room_id) -> list[int]` – one entry per row in `vetoes` (B4 adds the joker button; B3 already respects vetoes that exist).
- `claim_close(room_id) -> bool` – `UPDATE rooms SET status = 'closed' WHERE id = ? AND status = 'voting'`; `True` if it changed one row.
- `store_result(room_id, winner_option_id)` – stores `winner_option_id` (NULL if there is no winner) and sets `search_center_lat` and `search_center_lng` to NULL (`AGENTS.md`, Privacy: participant coordinates are deleted when a room closes).
- `get_winner_option_id(room_id) -> int | None` – the stored winner.

The close route runs these steps in **one** `db.transaction()`, in this order (SQL stays in `db.py`, the decision stays in `services/scoring.py`):
1. `claim_close`; if it returns `False` (someone else closed the room a moment earlier), nothing is changed and the route redirects to the result page;
2. only then read the votes and vetoes and call `pick_winner(rateable option ids, db.get_votes(room_id), db.get_vetoed_option_ids(room_id), rng=random.Random(room_id))`;
3. `store_result`.
- `save_vote` (B2) changes to return `bool`: in the same transaction it first runs `UPDATE rooms SET status = status WHERE id = ? AND status = 'voting'`, and only if that changed one row does it run the upsert. This locks the room row, so a vote and a close never overlap: a vote that started first finishes before the close reads the votes, and a vote that comes after the close finds the room closed. Works the same on SQLite (one writer at a time) and Postgres (row lock). If it returns `False`, the route shows "This room is closed. You can no longer vote." (400) and nothing is saved.

Must be true (one line = one test):

### Closing (accepted)
- [ ] The creator closes a `voting` room: status becomes `closed`, `winner_option_id` is the option `pick_winner` chooses, and the response redirects (303) to the result page.
- [ ] Closing deletes the search centre (`search_center_lat` and `search_center_lng` become NULL); radius and filters stay.
- [ ] Unrated options count as "ok" for a voter (D11), so the stored winner is the same as B1's on `db.get_votes()`.
- [ ] A vetoed option is not chosen (vetoes inserted directly in the database, B4 adds the button).
- [ ] Nobody rated anything: the room still closes, `winner_option_id` stays NULL.
- [ ] A full tie is decided with `random.Random(room_id)`, so the stored winner is reproducible for the room.
- [ ] Closing again (idempotent): status 303 to the result page, the stored winner is not recalculated, even if votes changed in the database in between.

### Closing (rejected, nothing changes)
- [ ] A joined non-creator: "Only the creator can close the room." (403), room unchanged.
- [ ] A visitor without a token, and a participant of another room: 403, room unchanged.
- [ ] A `collecting` room: "Voting has not started yet." (400), room unchanged.
- [ ] Unknown room: 404 for close and result.
- [ ] If the claim finds the room already closed (simulated: another request closed it between the route's check and the write), the route redirects to the result page and the first stored winner stays.
- [ ] `claim_close` returns `True` once for a `voting` room and `False` the second time, and `False` for a `collecting` room.

### Result page
- [ ] Closed room with a winner: the page names the winner ("The group's choice: Pizza"); a Google option is named "Place from Google Maps" until C2b.
- [ ] For every rateable option the page shows the anonymous counts, e.g. "2× Rather yes · 1× Fine with me · 0× Rather not".
- [ ] Closed room without a winner: "No winner: nobody rated any option."
- [ ] A room that is not closed yet: "The result is shown once the room is closed." and a link to the lobby (status 200), no winner shown.
- [ ] A visitor without a token is redirected (303) to the room page (join form); a participant of another room counts as a visitor.
- [ ] `rating_counts` counts only real ratings: an option nobody rated has 0 / 0 / 0.

### Privacy
- [ ] The result page never shows who rated what: no participant nickname appears on it, only counts.

### Votes after closing
- [ ] After closing, a vote is rejected with "This room is closed. You can no longer vote." (B2 rule, still true).
- [ ] A vote that passes the route's status check but reaches the database after the room was closed (simulated) is not saved, shows the closed message (400), and `save_vote` returns `False`.
- [ ] `save_vote` returns `True` and saves the rating while the room is `voting`.

### Rating page links (B2 page)
- [ ] While `voting`, the creator sees the close button (a form posting to `/rooms/<room_id>/close`); other participants do not.
- [ ] Once `closed`, every participant sees a link to `/rooms/<room_id>/result`.

### Persistence
- [ ] After a restart (a new app object on the same database), the room is still closed, the winner is the same and the result page shows it.

### Code rules
- [ ] `services/results.py` imports neither Flask nor `app.db` nor `requests`.

## Out of scope

- Closing automatically when everyone is done, or when the deadline is reached (B5). Only the creator closes in B3. Open question for the team (see PR): should the room also close when everyone is done?
- The joker button (B4). B3 only reads the `vetoes` table.
- Links from the lobby (A5's `lobby.html`) to the close button and the result page: Track A's file. Proposed follow-up for A5.
- Map and route to the winner (C3), names and photos of Google places (C2b).
- Showing scores, rankings or who is behind a rating.
- Deleting rooms after 7 days (`cleanup` command).
- No changes to `app/schema.sql` (all columns exist).

## Done when

- All tests in `tests/test_result.py` and all earlier tests pass (`uv run pytest`), output pasted.
- The creator can close a room from the rating page, and everyone sees the same winner and the anonymous counts.
- A rejected close shows its message and changes nothing; closing twice shows the same result.
- The closed room and its winner survive an app restart.
- Work is on branch `feature-b3-result`, pushed, pull request opened and reviewed by Track A (review circle).
