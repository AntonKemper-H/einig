# B5 – F11 Deadline, and closing when everyone is done

Branch: `feature-b5-deadline`
Tests: `tests/test_deadline.py`

## Why

Without a time limit, a group waits for the slowest person or for the creator to remember to close the room. A short countdown (15, 30 or 60 minutes) keeps the decision quick: when the time is up, the room closes by itself and the result is there for everyone, counting only the people who actually voted. And when everyone has rated every option, there is nothing left to wait for, so the room closes at once (`docs/concept.md` §3 step 6: "The room closes when everyone is done, the deadline is reached, or the creator closes it.", decided by the team in the review of this PR).

## What

Rules from `docs/concept.md` F11 ("Optional countdown (e.g. 15 / 30 / 60 minutes), after which the room closes automatically. Participants who haven't voted are not counted."), `AGENTS.md` (Rules for simultaneous actions: "Deadline: compared with server time (UTC) only. A vote after the deadline is rejected, even if the page was opened earlier."; "Closing a room: idempotent"), `docs/decisions.md` D11 (a participant who rated nothing is not counted) and the time format of `specs/a1-schema.md` (UTC text `YYYY-MM-DD HH:MM:SS`, so times compare correctly as text on SQLite and Postgres).

The column `rooms.deadline` exists since A1, so there is **no schema change**.

### Decisions in this spec (please check in the review)

- **The creator picks the time limit when starting the voting**, not when creating the room: the countdown is about the voting, and nobody can know at creation how long collecting ideas will take. The "Start voting" form gets a choice "No time limit / 15 / 30 / 60 minutes" (default: no time limit, so A5 works exactly as before). D17's B6 later moves this form to the room page; the field moves with it.
- **Closing "automatically" without a background job.** The free Render plan sleeps and has no scheduler, so the room is closed **the next time anyone opens one of its pages** after the deadline (rating page, lobby, result page, room page) or sends a vote. Because the lobby reloads itself every 4 seconds (A5), an open lobby closes the room within seconds of the deadline. The close uses exactly the B3 steps (claim, read votes and vetoes, `pick_winner` with `random.Random(room_id)`, store the result) in one transaction, so it is idempotent and the result is the same whoever triggers it.
- **Votes after the deadline never count**, even if the room is still `voting` in the database at that moment: `save_vote` checks the deadline inside the same room-row lock it already uses (B3). So the stored winner only ever uses votes from before the deadline.
- **Show minutes left, not a clock time:** "Time left: 12 min" on the rating page and in the lobby. A clock time would need the participant's time zone; minutes left are the same for everyone. No JavaScript: the number is computed when the page is rendered (the lobby refreshes itself, the rating page updates on every rating).
- **The creator can still close early** (B3, unchanged). After closing, the deadline does nothing any more.
- **Everyone done closes the room.** "Done" is A5's flag (`has_finished`): a participant has rated every option (B2). When a vote makes the last participant done, the room closes right after that vote, with the same B3 steps, and that vote is answered with a redirect to the result page. A participant who joined but rated nothing is not done, so the room then waits for the deadline or the creator. A room with a single participant (for example the creator trying the app alone) therefore closes right after that person's last rating. Using a joker does not make anyone done (B4). Once the room has closed this way, nobody can change a rating or use a joker any more, the same as after any close. That is fair: everyone knows about the joker and can use it before their last rating (decided by Timonhio in this PR).

### Pages and forms

- Lobby (`/rooms/<room_id>/lobby`, A5), room `collecting`, creator: the "Start voting" form gets `<select name="time_limit">` with the options `""` "No time limit" (selected), `15` "15 minutes", `30` "30 minutes", `60` "60 minutes". Guests do not see the form (as today).
- `POST /rooms/<room_id>/start` (A5) reads `time_limit`. Missing or `""` → no deadline (exactly A5's behaviour). `15`, `30`, `60` → `deadline` = server time (UTC) + that many minutes, stored in the same `UPDATE` that switches the room to `voting`. Anything else → "Please choose one of the time limits." (400, lobby), room stays `collecting`, nothing stored. All other A5 rules and messages stay the same.
- While `voting` with a deadline: the rating page and the lobby show "Time left: N min" (minutes rounded up, so the last seconds still show "1 min"). Without a deadline, no such text.
- After the deadline: the pages show what a closed room shows today (B3): the rating page "This room is closed. You can no longer vote." and the "See the result" link, the result page the winner.

### Pure helpers: `app/services/deadline.py` (no Flask, no database, no `requests`)

- `TIME_LIMITS = (15, 30, 60)` and `INVALID_TIME_LIMIT_MESSAGE = "Please choose one of the time limits."`
- `parse_time_limit(raw: str | None) -> tuple[int | None, list[str]]` – `None` or `""` (after stripping) → `(None, [])`; `"15"`, `"30"`, `"60"` → `(15, [])` etc.; anything else (`"45"`, `"abc"`, `"-15"`, `"15.0"`) → `(None, [INVALID_TIME_LIMIT_MESSAGE])`.
- `now_utc() -> datetime` – the one place that reads the clock (`datetime.now(timezone.utc)`).
- `format_utc(moment: datetime) -> str` – `YYYY-MM-DD HH:MM:SS` in UTC (A1 time format).
- `deadline_after(now: datetime, minutes: int) -> str` – `format_utc(now + minutes)`.
- `is_past(deadline: str | None, now: datetime) -> bool` – `False` without a deadline; `True` from the deadline second on (`now >= deadline`).
- `minutes_left(deadline: str | None, now: datetime) -> int | None` – `None` without a deadline; otherwise the remaining time in whole minutes, rounded up, and `0` once it is past.
- `time_left_text(deadline: str | None, now: datetime) -> str | None` – "Time left: N min" while `minutes_left` is above 0, else `None`.

### Database (`app/db.py`)

- `get_room(room_id)` also returns `deadline` (it does not read that column yet).
- `start_voting(room_id, deadline: str | None = None) -> bool` – the same `UPDATE … SET status = 'voting'` as A5, now also setting `deadline` (NULL if `None`). Callers without the argument keep A5's behaviour.
- `everyone_finished(room_id) -> bool` – `True` if the room has at least one participant and every participant has `has_finished = 1`.
- `save_vote(room_id, participant_id, option_id, rating, now: str | None = None) -> bool` – the room-row lock becomes `UPDATE rooms SET status = status WHERE id = ? AND status = 'voting' AND (deadline IS NULL OR deadline > ?)`, with `now` as the UTC text (`None` → the current server time). If it changes no row, nothing is saved and it returns `False` (B3's rule, unchanged for rooms without a deadline).

### Route helper (`app/routes/rooms.py`)

- The B3 close steps live in one shared function used by the close route, the deadline and "everyone done" (no copy): `claim_close`; only if the claim wins, `pick_winner(...)` with the rateable options, `db.get_votes`, `db.get_vetoed_option_ids`, `rng=random.Random(room_id)`, then `store_result`; all in one `db.transaction()`.
- `close_if_time_is_up(room)` – if the room is `voting`, has a deadline and `deadline.is_past(...)`, it runs the shared close steps and returns the room read again; otherwise it returns the room unchanged.
- After a saved vote (B2's transaction with `save_vote` and `mark_finished` has committed), the vote route checks `db.everyone_finished(room_id)`; if `True`, it runs the shared close steps and redirects (303) to `/rooms/<room_id>/result` instead of the rating page.
- Called right after the room is loaded in: `GET /vote`, `POST /vote`, `GET /lobby`, `GET /result` and `GET /rooms/<room_id>` (the room page), for visitors too (closing is the same whoever triggers it).

### Must be true (one line = one test)

#### Starting with a time limit
- [ ] The creator starts with `time_limit=30`: status `voting`, `deadline` is server time + 30 minutes (within a few seconds), 303 to the lobby.
- [ ] Starting without `time_limit`, or with `""`: status `voting`, `deadline` stays NULL (A5 unchanged).
- [ ] An invalid `time_limit` (`45`, `abc`, `-15`): "Please choose one of the time limits." (400), status stays `collecting`, `deadline` stays NULL.
- [ ] The creator's lobby shows the `time_limit` choice inside the "Start voting" form with the four options; a guest's lobby has no such form.

#### While voting
- [ ] With a deadline about 11.5 minutes away, the rating page and the lobby show "Time left: 12 min".
- [ ] Without a deadline, neither page shows "Time left".
- [ ] A vote before the deadline is saved (303).
- [ ] Opening the pages before the deadline does not close the room.
- [ ] A room without a deadline is never closed by opening its pages.

#### Closing when the time is up
- [ ] Deadline passed, someone opens the rating page: the room is `closed`, `winner_option_id` is what `pick_winner` gives on the stored votes and vetoes, the search centre is deleted, and the page shows the closed message and the result link.
- [ ] The same happens when the first page opened after the deadline is the lobby, the result page (which then names the winner) or the room page, and also when a visitor without a token opens the room page.
- [ ] A participant who rated nothing is not counted: with Anna's votes only, the stored winner is the one `pick_winner` gives for Anna alone.
- [ ] Closing is idempotent: opening a page again after the automatic close does not recalculate the winner, even if the votes changed in the database in between.
- [ ] Two closes at the same moment (simulated: the page still sees `voting` with a past deadline after another request already closed the room): the claim fails, nothing is recalculated, the first stored winner stays.
- [ ] A joker counts in the automatic close: an option with a veto is not chosen (the veto is inserted directly in the database, as B4 is not on `main` yet).
- [ ] A full tie is decided with `random.Random(room_id)`, as in B3, so the stored winner is reproducible for the room.
- [ ] The creator can still close before the deadline (B3); opening a page after the deadline later keeps that first winner.

#### Closing when everyone is done
- [ ] Anna and Ben: after Anna has rated all three options the room is still `voting`; Ben's last rating closes it (`closed`, `winner_option_id` is what `pick_winner` gives, search centre deleted), and that vote is answered with 303 to `/rooms/<room_id>/result`.
- [ ] A participant who has rated only some options keeps the room `voting`, and the vote redirects to the rating page as before.
- [ ] A participant who joined but rated nothing keeps the room `voting` even when everyone else is done.
- [ ] Using a joker does not count as done: with Ben's joker but no ratings from Ben, Anna's last rating does not close the room (the joker row is inserted directly, as B4 is not on `main` yet).
- [ ] The room closed by "everyone done" is not recalculated later: opening pages after the deadline, or the creator pressing close, keeps that winner.
- [ ] `everyone_finished`: `False` while someone is not done, `True` once everyone is, and `False` for a room without participants.

#### Votes after the deadline (rejected, nothing saved)
- [ ] A vote sent after the deadline (room still `voting` in the database): "This room is closed. You can no longer vote." (400), no vote saved, and the room is `closed` afterwards.
- [ ] A vote that passes the route's check (simulated: the route still sees a deadline in the future) but reaches the database after the deadline: not saved, 400 with the closed message, `save_vote` returns `False`.
- [ ] `save_vote` with `now` before the deadline saves and returns `True`; with `now` equal to or after the deadline it saves nothing and returns `False`.

#### Helpers
- [ ] `parse_time_limit` accepts `None`, `""`, `" "`, `"15"`, `"30"`, `"60"` and rejects `"45"`, `"abc"`, `"-15"`, `"15.0"` with the message.
- [ ] `format_utc` and `deadline_after` give `YYYY-MM-DD HH:MM:SS` in UTC (e.g. 2026-11-16 23:50:00 + 15 → `2026-11-17 00:05:00`).
- [ ] `is_past`: `False` without a deadline and one second before, `True` at the deadline second and after.
- [ ] `minutes_left` and `time_left_text`: `None` without a deadline; 11 min 30 s → 12 and "Time left: 12 min"; 10 s → 1; at and after the deadline 0 and `None`.
- [ ] `now_utc` returns an aware datetime in UTC.

#### Persistence
- [ ] After a restart (a new app object on the same database) the deadline is still stored, and once it has passed, opening the rating page closes the room.

#### Code rules
- [ ] `app/services/deadline.py` imports no Flask, `requests` or `app.db`.

## Changes to reviewed tests (need the reviewer's OK, `AGENTS.md`)

"Everyone done" changes what happens after the last rating, so a few reviewed tests that rate everything and then expect the room to still be open need a small change, in its own commit:

- `tests/test_rating.py` (B2): the `room` fixture gets one more participant ("Idle") who never rates, so the room is never "everyone done" and the four tests that rely on a still-open room (`test_all_rated_page_lists_own_ratings_with_buttons`, `test_replaced_option_is_rejected_and_not_shown`, `test_no_page_shows_another_participants_rating`, `test_ratings_survive_a_restart`) keep testing exactly what they tested. No assertion changes.
- `tests/test_swipe_rating.py` (A10, merged in #55 after this spec was approved): `test_overview_has_no_swipe` lets a single creator rate everything and then expects the overview, so it gets the same one-line change (a participant "Idle" who never rates joins first). No assertion changes.
- `tests/test_joker.py` (B4, #44, not on `main` yet): `test_vetoed_option_is_not_chosen` and `test_every_option_vetoed_fewest_jokers_then_best_score` use the jokers **before** the last ratings instead of after. Whichever of B4 and B5 is merged second makes this change. No assertion changes.

## Out of scope

- The joker after the deadline: B4 (#44) is not on `main` yet. Whichever of B4 and B5 is merged second adds the same deadline condition to `save_veto` and the same `close_if_time_is_up` call to the joker route, with a small follow-up test reviewed separately.
- Changing the deadline after starting, or extending it.
- A countdown that updates without reloading (would need JavaScript), and showing clock times.
- A background job or scheduler.
- Changes to `app/schema.sql`, `services/scoring.py`, or to existing tests.

## Done when

- All tests in `tests/test_deadline.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network.
- SQL only in `app/db.py`, rules in `app/services/deadline.py`, thin routes, Jinja templates, no JavaScript.
- Work is on branch `feature-b5-deadline`, pushed, pull request opened with AntonKemper-H as reviewer (D10: A reviews B).
