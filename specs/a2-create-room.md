# A2 – F1 Create a room

Branch: `feature-a2-create-room`
Tests: `tests/test_rooms.py`

## Why
Every decision starts with a room: without F1 nobody can join (A3), add options (A4) or vote (B2), so this is the first feature a user sees. The room id is the only thing that protects a room from strangers, so it must be random and hard to guess, and the creator must be recognised later without an account.

## What
F1 in `docs/concept.md`: the creator sets a title and a mode, the app creates a random room id, stores the room and returns an invite URL.

**Flow (Post/Redirect/Get).**
- `GET /` shows the "create a room" form: `title` (text), `mode` (choice: `manual` / `nearby` / `surprise`, default `manual`) and `nickname` (text, the creator's name in the room).
- `POST /rooms` validates the form. If it is valid, it saves the room and the creator in **one transaction** (both or neither) and redirects (302 or 303) to `GET /rooms/<room_id>`.
- If it is invalid, it shows the form again with status 400, a clear message per problem and the entered values, and saves nothing.
- `GET /rooms/<room_id>` is a minimal room page: the room title and the invite URL (the absolute URL of this page, e.g. `http://localhost/rooms/<room_id>`) as text the creator can copy. An unknown room id shows the normal 404 page.

**Stored data.**
- Room: random id, `title`, `mode`; `status` stays the database default `collecting`.
- Creator: a row in `participants` with the room id, `nickname`, a new random `session_token`, `is_creator = 1`, `has_finished = 0`.
- Ids and tokens come from `secrets.token_urlsafe` (called as `secrets.token_urlsafe(...)`, so tests can replace it): room id `secrets.token_urlsafe(8)` (11 characters, about 64 random bits), session token `secrets.token_urlsafe(32)`.
- Session: the Flask signed session stores the creator's token keyed by room id: `session["participant_tokens"][room_id] = session_token`. Tokens for other rooms in the same browser are kept.
- Title and nickname are cleaned with `.strip()` before checking and saving (the database `trim()` check only strips spaces, see `specs/a1-schema.md`).

**Limits and messages.** Lengths are counted after `.strip()`.

| Input | Rule | Message |
|---|---|---|
| title | not empty | `Please enter a title.` |
| title | at most 80 characters | `The title can be at most 80 characters.` |
| mode | one of `manual`, `nearby`, `surprise` | `Please choose a valid mode.` |
| nickname | not empty | `Please enter a nickname.` |
| nickname | at most 30 characters | `The nickname can be at most 30 characters.` |

Checks (one line = one test):
- [ ] The home page shows the form with the fields `title`, `mode` (all three modes) and `nickname`.
- [ ] Accepted: a valid form redirects to `/rooms/<room_id>`.
- [ ] Accepted: the room is stored with the given title and mode and status `collecting`.
- [ ] Accepted: each of the three modes can be chosen and is stored.
- [ ] Accepted: the creator is stored as the only participant of the room with `is_creator = 1`, `has_finished = 0` and a session token.
- [ ] Accepted: the session holds the creator's token under the room id, and it matches the stored `session_token`.
- [ ] Accepted: creating a second room in the same browser keeps the token of the first room.
- [ ] Accepted: title and nickname are stored without leading/trailing whitespace.
- [ ] Edge case: a title of exactly 80 and a nickname of exactly 30 characters are accepted.
- [ ] Room ids: 20 new rooms get 20 different ids, each at least 10 URL-safe characters and not a number (never sequential).
- [ ] The room page shows the title and the invite URL.
- [ ] Rejected: an unknown room id shows 404.
- [ ] Rejected: empty title – message, status 400, no room, no participant, no session token.
- [ ] Rejected: title of only whitespace (spaces, tabs, line breaks) – message, data unchanged.
- [ ] Rejected: title over 80 characters – message, data unchanged.
- [ ] Rejected: unknown mode (e.g. `blind`) and missing mode – message, data unchanged.
- [ ] Rejected: empty or whitespace-only nickname – message, data unchanged.
- [ ] Rejected: nickname over 30 characters – message, data unchanged.
- [ ] Rejected: a missing field counts as empty; a mode in other letter case (e.g. `MANUAL`) is unknown.
- [ ] Rejected: the form is shown again with the entered title.
- [ ] Rejected: a form with several problems shows every message at once and saves nothing.
- [ ] Edge case: if a generated room id or session token already exists (extremely unlikely), the app shows `Something went wrong while creating the room. Please try again.`, does not crash, and leaves the data unchanged – no room without its creator.
- [ ] Persistence: after an app restart (new app on the same database file), the room page still shows the room and the session token still matches the stored creator.

## Out of scope
- Joining a room as another participant, the join form and nickname uniqueness checks (A3/F2). The room page does not yet tell creator and visitors apart.
- Lobby, participant list, meta refresh, start/close buttons (A5/F7).
- QR code (A6/F22).
- Google search, location, radius, filters for `nearby`/`surprise` (C2/C4): the mode is only stored.
- Deadline (B5/F11).
- Retrying with a new id after a collision; CSRF tokens; rate limiting.
- No changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_rooms.py` and all earlier tests pass (`uv run pytest`), output pasted.
- SQL only in `app/db.py`, validation in `app/services/rooms.py`, thin routes in `app/routes/rooms.py`, Jinja templates for the form and the room page.
- Creating a room works in the browser; a rejected form shows a message and stores nothing.
- Accepted rooms survive an app restart.
- Work is on branch `feature-a2-create-room`, pushed, pull request opened with mkim-nova as reviewer.
