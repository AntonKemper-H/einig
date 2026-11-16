# B5 – F11 Deadline

Branch: `feature-b5-deadline`
Tests: `tests/test_deadline.py`

## Why

Without a time limit, a group waits for the slowest person or for the creator to remember to close the room. A short countdown (15, 30 or 60 minutes) keeps the decision quick: when the time is up, the room closes by itself and the result is there for everyone, counting only the people who actually voted.

## What

Rules from `docs/concept.md` F11 ("Optional countdown (e.g. 15 / 30 / 60 minutes), after which the room closes automatically. Participants who haven't voted are not counted."), `AGENTS.md` (Rules for simultaneous actions: "Deadline: compared with server time (UTC) only. A vote after the deadline is rejected, even if the page was opened earlier."; "Closing a room: idempotent"), `docs/decisions.md` D11 (a participant who rated nothing is not counted) and the time format of `specs/a1-schema.md` (UTC text `YYYY-MM-DD HH:MM:SS`, so times compare correctly as text on SQLite and Postgres).

The column `rooms.deadline` exists since A1, so there is **no schema change**.

### Decisions in this spec (please check in the review)

- **The creator picks the time limit when starting the voting**, not when creating the room: the countdown is about the voting, and nobody can know at creation how long collecting ideas will take. The "Start voting" form gets a choice "No time limit / 15 / 30 / 60 minutes" (default: no time limit, so A5 works exactly as before). D17's B6 later moves this form to the room page; the field moves with it.
- **Closing "automatically" without a background job.** The free Render plan sleeps and has no scheduler, so the room is closed **the next time anyone opens one of its pages** after the deadline (rating page, lobby, result page, room page) or sends a vote. Because the lobby reloads itself every 4 seconds (A5), an open lobby closes the room within seconds of the deadline. The close uses exactly the B3 steps (claim, read votes and vetoes, `pick_winner` with `random.Random(room_id)`, store the result) in one transaction, so it is idempotent and the result is the same whoever triggers it.
- **Votes after the deadline never count**, even if the room is still `voting` in the database at that moment: `save_vote` checks the deadline inside the same room-row lock it already uses (B3). So the stored winner only ever uses votes from before the deadline.
- **Show minutes left, not a clock time:** "Time left: 12 min" on the rating page and in the lobby. A clock time would need the participant's time zone; minutes left are the same for everyone. No JavaScript: the number is computed when the page is rendered (the lobby refreshes itself, the rating page updates on every rating).
- **The creator can still close early** (B3, unchanged). After closing, the deadline does nothing any more.

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
- `save_vote(room_id, participant_id, option_id, rating, now: str | None = None) -> bool` – the room-row lock becomes `UPDATE rooms SET status = status WHERE id = ? AND status = 'voting' AND (deadline IS NULL OR deadline > ?)`, with `now` as the UTC text (`None` → the current server time). If it changes no row, nothing is saved and it returns `False` (B3's rule, unchanged for rooms without a deadline).

### Route helper (`app/routes/rooms.py`)

- `close_if_time_is_up(room)` – if the room is `voting`, has a deadline and `deadline.is_past(...)`, it runs B3's close steps in one `db.transaction()` (`claim_close`; if the claim wins: `pick_winner(...)` with the rateable options, `db.get_votes`, `db.get_vetoed_option_ids`, `rng=random.Random(room_id)`; `store_result`) and returns the room read again; otherwise it returns the room unchanged. B3's close route and this helper share the same code for these steps (no copy).
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

## Out of scope

- Closing automatically when everyone is done (concept §3 step 6; open question from B3, see the PR).
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
