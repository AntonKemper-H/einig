# A1 – Database schema

Branch: `feature-a1-schema`
Tests: `tests/test_schema.py`

## Why
Every Sprint 1–4 feature (F1–F13, F22) stores rooms, participants, options, votes and vetoes, so the tables must exist and agree before the three tracks build on them. The database itself enforces the rules for simultaneous actions from `AGENTS.md`, so two phones pressing a button at the same moment can never create a second vote, a second veto or a duplicate nickname.

## What
Tables in `app/schema.sql`, based on `docs/concept.md` §7, reduced to what F1–F13 + F22 need.

**rooms** – one decision (F1, F7, F8, F11, F12)
- `id` TEXT primary key (random token from the app, never sequential)
- `title` TEXT, not empty
- `mode` TEXT, one of `manual` / `nearby` / `surprise` (`blind`, `fate` are parked F14/F15)
- `status` TEXT, one of `collecting` / `voting` / `closed`, default `collecting`
- `deadline` TEXT, optional, UTC time in the time format below (F11)
- `search_center_lat` REAL, optional, between -90 and 90; `search_center_lng` REAL, optional, between -180 and 180; `radius_m` INTEGER, optional, greater than 0 (F8, F12)
- `filters` TEXT, optional, JSON (category, price level, minimum rating …) (F8, F12)
- `winner_option_id` INTEGER, optional, stored when the room closes so closing again returns the same result (no foreign key, see Out of scope)
- `created_at` TEXT, set automatically (for the 7-day cleanup)

**participants** – one person in one room (F2, F7)
- `id` INTEGER primary key; `room_id` → rooms
- `nickname` TEXT, not empty; `session_token` TEXT, unique across all rooms
- `is_creator` 0/1, default 0 (creator-only actions); `has_finished` 0/1, default 0 (lobby "who is done")

**options** – one thing to choose (F3, F8, F12, F13)
- `id` INTEGER primary key; `room_id` → rooms
- `source` TEXT, one of `manual` / `google`
- `label` TEXT for manual options; `place_id` TEXT for Google options. Exactly one of the two is filled and it is not empty: a Google option stores **only** the `place_id` (Google terms).
- `category` TEXT, optional (sub-category, so surprise mode can mix cuisines)
- `is_replaced` 0/1, default 0 ("Been there", F13)

**votes** – one rating (F4)
- `id`; `room_id`; `participant_id`; `option_id`; `rating` one of `yes` / `ok` / `no`
- Participant and option must both belong to `room_id` (checked by the database).

**vetoes** – the joker (F10)
- `id`; `room_id`; `participant_id`; `option_id`
- Participant and option must both belong to `room_id`.

**Time format (review #5, point 3).** Every time (`created_at`, `deadline`) is UTC text in the form `YYYY-MM-DD HH:MM:SS`, e.g. `2026-11-13 10:38:29` – the same format SQLite's `CURRENT_TIMESTAMP` writes. Only then do times compare correctly as text. In Python: `datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")`.

**Empty text (review #5, point 2).** The database only rejects text that is empty after removing spaces (SQLite's `trim()` strips spaces only). Text made of tabs or line breaks passes the database, so A2–A4 must clean input in Python with `.strip()` before saving.

**Schema version.** `app_info.schema_version` is `1` after this task. `init-db` updates it without deleting anything. How later column changes reach an existing database is decided in C1.

Checks (one line = one test):
- [ ] After `init-db` the tables `rooms`, `participants`, `options`, `votes`, `vetoes` exist.
- [ ] Accepted: a complete valid room (creator, manual option, Google option, vote, veto) can be stored and read back.
- [ ] A new room gets status `collecting` and a `created_at` time automatically.
- [ ] Rejected: room with an unknown `mode` – data unchanged.
- [ ] Rejected: room with an unknown `status` – data unchanged.
- [ ] Rejected: room with an empty title – data unchanged.
- [ ] Rejected: second participant with the same nickname in the same room – data unchanged.
- [ ] Accepted: the same nickname in a different room.
- [ ] Rejected: two participants with the same `session_token` – data unchanged.
- [ ] Rejected: participant with an empty nickname – data unchanged.
- [ ] Rejected: participant in a room that does not exist (foreign key) – data unchanged.
- [ ] Rejected: option with an unknown `source` – data unchanged.
- [ ] Rejected: manual option without label; Google option without `place_id`; Google option that also stores a name in `label` – data unchanged.
- [ ] Rejected: the same manual label twice in one room; the same `place_id` twice in one room – data unchanged.
- [ ] Rejected: vote with a rating other than `yes` / `ok` / `no` – data unchanged.
- [ ] Rejected: a second plain insert of a vote for the same participant and option – data unchanged.
- [ ] Accepted: voting again with "insert or replace on conflict" (upsert) leaves exactly one vote with the new rating.
- [ ] Rejected: vote for an option from another room – data unchanged.
- [ ] Rejected: vote by a participant from another room – data unchanged.
- [ ] Rejected: a second veto by the same participant in the same room, even on a different option – data unchanged.
- [ ] Rejected: veto on an option from another room – data unchanged.
- [ ] Edge case: deleting a room also deletes its participants, options, votes and vetoes (needed by the 7-day cleanup).
- [ ] Persistence: `init-db` on an existing database keeps all rows in the new tables.
- [ ] `reset-db` answered with "y" leaves all new tables empty (and still usable).

Added after review #5 (tests in `tests/test_schema_review_fixes.py`, because reviewed tests are never edited):
- [ ] Rejected: Google option with an empty or space-only `place_id` – data unchanged.
- [ ] Rejected: room with `radius_m` of 0 or below – data unchanged.
- [ ] Rejected: room with `search_center_lat` outside -90…90 or `search_center_lng` outside -180…180 – data unchanged.
- [ ] Accepted: room with a valid search center and radius.
- [ ] After `init-db`, `schema_version` is `1`, also on an existing database that still says `0`, and other rows are kept.

## Out of scope
- No routes, templates or services; no query helpers in `app/db.py` unless a test needs one (A2+ add them).
- Parked tables/columns: groups, group members, place history, fairness weights, participant locations (F16–F19), `blind`/`fate` modes.
- No name, photo, rating or address of Google places in the database – only `place_id`.
- No Postgres version of the schema (task C1). SQL stays portable where easy; known SQLite-only bits (`INTEGER PRIMARY KEY` auto-numbering, `INSERT OR IGNORE`) are translated in C1.
- No foreign key on `rooms.winner_option_id`: rooms and options would point at each other, which Postgres cannot create in one pass. The app sets it only to an option of the same room.
- Case-insensitive nickname / label uniqueness ("Anna" vs "anna"): the app normalises input in A3/A4; the database compares exactly.
- Scoring rules (D11: unrated options count as "ok") – not stored, computed in `services/scoring.py`.

## Done when
- All tests in `tests/test_schema.py`, `tests/test_schema_review_fixes.py` and all earlier tests pass (`uv run pytest`), output pasted.
- `uv run flask --app app init-db` on an existing database creates the new tables and keeps all data.
- Work is on branch `feature-a1-schema`, pushed, pull request opened with mkim-nova as reviewer.
