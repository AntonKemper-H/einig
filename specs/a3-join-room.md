# A3 – F2 Join without an account

Branch: `feature-a3-join-room`
Tests: `tests/test_join.py` (new file, because `tests/test_rooms.py` is already reviewed)

## Why
A room is only useful if friends can get in: they open the invite link on their own phone, pick a nickname and are part of the decision without creating an account. The browser must recognise them after a reload, and two people must never end up with the same name in one room, otherwise votes and the lobby (A5) become confusing.

## What
F2 in `docs/concept.md`: open the link, enter a nickname, store a session token in the browser so the participant is back in the room after a reload. Several devices can join the same room at once, duplicate nicknames are prevented.

**"Joined" means:** the signed session has a token under `session["participant_tokens"][room_id]` (set up in A2) **and** that token belongs to a participant of this room in the database. A token that is missing from the database (e.g. after `reset-db`) counts as not joined.

**Flow (Post/Redirect/Get).**
- `GET /rooms/<room_id>` (the invite URL from A2):
  - not joined → room title and a join form with `nickname`, posting to `/rooms/<room_id>/join`;
  - joined → room title, `You joined as <nickname>.` and the invite URL (no join form).
  - Unknown room id → 404 (as in A2).
- `POST /rooms/<room_id>/join`:
  - valid → saves a participant (`is_creator = 0`, `has_finished = 0`, new token from `secrets.token_urlsafe(32)`), stores the token in the session next to tokens for other rooms, redirects (302 or 303) to `GET /rooms/<room_id>`;
  - invalid → shows the room page with the join form again, status 400, the message and the entered nickname; saves nothing and stores no token;
  - already joined → saves nothing new and redirects to the room page (pressing "Join" twice never creates a second participant);
  - unknown room id → 404, nothing saved.
- The nickname is cleaned with `.strip()` before checking and saving.

**Rules and messages** (length counted after `.strip()`):

| Rule | Message |
|---|---|
| nickname not empty | `Please enter a nickname.` |
| at most 30 characters (same limit as A2) | `The nickname can be at most 30 characters.` |
| not already used in this room, **ignoring upper/lower case** ("anna" is taken if "Anna" exists); the entered spelling is stored | `This nickname is already taken in this room. Please choose another one.` |
| room is not `closed` (joining while `collecting` or `voting` is allowed) | `This room is closed. You can no longer join.` |
| a generated token already exists, or the database refuses the insert (e.g. two phones pick the same name at the same moment) | `Something went wrong while joining. Please try again.` |

Checks (one line = one test):
- [ ] Not joined: the room page shows the title and a join form with `nickname` posting to `/rooms/<room_id>/join`.
- [ ] Accepted: a valid nickname redirects to the room page.
- [ ] Accepted: the participant is stored in the right room with the stripped nickname, `is_creator = 0`, `has_finished = 0` and a session token.
- [ ] Accepted: the session holds the new token under the room id and it matches the stored token.
- [ ] Accepted: after joining (and on every reload), the room page shows `You joined as <nickname>.` and no join form.
- [ ] Accepted: the creator's room page also shows `You joined as <creator nickname>.` and no join form.
- [ ] Accepted: joining a second room keeps the token of the first room.
- [ ] Accepted: several browsers join the same room one after another; every participant is stored once with a different token.
- [ ] Accepted: the same nickname in a different room.
- [ ] Accepted: joining while the room status is `voting`.
- [ ] Edge case: a nickname of exactly 30 characters (plus surrounding whitespace) is accepted.
- [ ] Edge case: a session token that is not in the database counts as not joined (join form shown).
- [ ] Rejected: empty, missing or whitespace-only nickname – message, status 400, data and session unchanged.
- [ ] Rejected: nickname over 30 characters – message, data unchanged.
- [ ] Rejected: nickname already used in the room, exactly or with other upper/lower case, or with extra whitespace – message, data unchanged.
- [ ] Rejected: the form is shown again with the entered nickname.
- [ ] Rejected: joining a `closed` room – message, data unchanged.
- [ ] Rejected: joining an unknown room – 404, nothing saved.
- [ ] Edge case: posting the join form again when already joined creates no second participant and redirects to the room page.
- [ ] Edge case: a token collision shows the "Something went wrong" message, does not crash and saves nothing.
- [ ] Persistence: after an app restart, the joined participant is still stored and the same browser is still recognised (`You joined as …`).

## Out of scope
- Lobby with participant list, "who is done", meta refresh, start/close buttons (A5/F7).
- QR code (A6/F22).
- Leaving a room, renaming, kicking participants.
- Sharing the location when joining (F8/F12, Track C).
- Switching `app/db.py` to C1's `db.transaction()` / `db.INTEGRITY_ERRORS` (follow-up after C1 is merged, agreed in PR #8).
- CSRF protection (team decision pending, see PR #8).
- No changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_join.py` and all earlier tests pass (`uv run pytest`), output pasted.
- SQL only in `app/db.py`, validation in `app/services/`, thin routes in `app/routes/rooms.py`, Jinja templates.
- Joining works from a second browser; a rejected nickname shows a message and stores nothing.
- Joined participants survive an app restart.
- Branch rebased on `main` after A2 is merged, pushed, pull request opened with mkim-nova as reviewer.
