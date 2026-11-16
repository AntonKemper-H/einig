# A8 – F25 My rooms on the home page

Branch: `feature-a8-my-rooms`
Tests: `tests/test_my_rooms.py`

Decision: `docs/decisions.md`, D15. No schema change. Builds on A3 (`remember_token` stores `session["participant_tokens"]`, a dict room id → participant token).

## Why
Someone who is in two or three rooms (Friday dinner, Sunday cinema) has no way back to them except the original link. The home page lists every room this browser is in, so people can switch between rooms, and the list must survive closing the browser without ever showing anything about other people's rooms.

## What

### Decisions in this spec (please check in the review)
- **Source of the list:** only the tokens in this browser's signed session cookie. No new table, no account. A token counts only if `db.get_participant(room_id, token)` finds a participant (the room still exists and the token belongs to it).
- **The cookie lasts 180 days:** `PERMANENT_SESSION_LIFETIME = timedelta(days=180)` in `create_app`, and `session.permanent = True` is set in `remember_token`. Before A8 the cookie ended when the browser closed.
- **At most 30 rooms remembered** (`MAX_REMEMBERED_ROOMS = 30` in `app/services/rooms.py`): when a 31st room is remembered, the token of the oldest-remembered room is dropped. Why: browsers refuse cookies over about 4 KB, which would lose every token at once. Rooms are deleted after 7 days anyway, so 30 is plenty.
- **Stale tokens are dropped:** when the home page finds a token whose room or participant no longer exists, it removes it from the cookie.
- **Order:** newest room first (`rooms.created_at`, then room id for a stable order).
- **The link goes to the page for the room's status:** `collecting` → room page (`/rooms/<id>`), `voting` → rating page (`/rooms/<id>/vote`), `closed` → result page (`/rooms/<id>/result`).

### Pure functions (`app/services/rooms.py`, no Flask, no database)
- `remember_room_token(tokens: dict[str, str], room_id: str, token: str) -> dict[str, str]` returns a **new** dict with the room added (or its token replaced) as the newest entry; if this makes more than `MAX_REMEMBERED_ROOMS` entries, the oldest entries are removed. Python dicts keep insertion order, which is the "remembered" order; a replaced room moves to the end.
- `room_link_endpoint(status: str) -> str` returns `"rooms.show_room"`, `"rooms.show_vote"` or `"rooms.show_result"`; an unknown status gives `"rooms.show_room"`.
- `STATUS_LABELS = {"collecting": "Collecting ideas", "voting": "Voting", "closed": "Decided"}`.

### `app/db.py`
- New: `get_my_rooms(tokens: dict[str, str]) -> list[dict]`: for each room id and token, the room's `id`, `title`, `status`, `created_at` and the participant's `nickname` and `is_creator`, only where the token belongs to a participant of that room; sorted newest first. One query per token is fine (at most 30).

### Routes and templates
- `remember_token` (in `app/routes/rooms.py`) uses `remember_room_token` and sets `session.permanent = True`.
- `GET /` (`main.home`): before the create form, a section **"My rooms"**:
  - one entry per room from `get_my_rooms`: title (a link to the page from `room_link_endpoint`), status label, "You are <nickname>", and "Creator" if `is_creator`.
  - if the browser has no rooms: `You are not in any room yet. Create one below or open an invite link.`
  - if tokens were stale, the cookie is written back without them.
- `base.html` gets a header link `My rooms` to `/` on every page.
- The create form stays as it is (also when shown again with errors by `rooms.create_room`, which must then also pass the room list).

Checks (one line = one test), `tests/test_my_rooms.py`:
- [ ] `remember_room_token` adds a room as the newest entry and does not change the dict it was given.
- [ ] `remember_room_token` with an already remembered room replaces its token and moves it to the end.
- [ ] `remember_room_token` keeps at most 30 entries and drops the oldest ones.
- [ ] `room_link_endpoint` gives the right endpoint for each status and the room page for an unknown one.
- [ ] A new browser: the home page shows the "not in any room yet" text and the create form.
- [ ] Accepted: after creating two rooms and joining a third (another creator), the home page lists all three, newest first, with title, status label, own nickname, and "Creator" only for the two own rooms.
- [ ] Each entry links to the room page while collecting, to the rating page while voting, and to the result page when closed.
- [ ] Another browser that has joined none of these rooms sees none of them (no information about other people's rooms).
- [ ] A visitor who only opened a room link without joining does not see that room in the list.
- [ ] Stale token: after a room is deleted from the database, the home page does not list it and the cookie no longer contains its token.
- [ ] A token that belongs to no participant (forged or from another room) is not listed and is removed.
- [ ] Joining a 31st room drops the oldest-remembered room from the list.
- [ ] The session is permanent after creating or joining a room, and the configured lifetime is 180 days.
- [ ] Every page has the "My rooms" link to `/`.
- [ ] The create form shown again with errors still shows the room list.
- [ ] The list shows no votes, no other participants' nicknames and no counts of votes.
- [ ] Persistence: after an app restart, the same browser still sees its rooms.

## Out of scope
- Groups (A9), leaving or hiding a room, deleting a room, search or filter in the list.
- Storing the list in the database or any kind of account or login.
- The cleanup command that deletes rooms after 7 days.
- Changes to `app/schema.sql`, JavaScript, or existing tests.

## Done when
- All tests in `tests/test_my_rooms.py` and all earlier tests pass (`uv run pytest`), output pasted.
- On the deployed app on a phone: create a room, join another one, close the browser, open the app again → both rooms are listed and the links work.
- Work is on branch `feature-a8-my-rooms`, pushed, pull request opened for review.
