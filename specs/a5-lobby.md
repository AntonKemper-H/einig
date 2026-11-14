# A5 – F7 Lobby with room status

Branch: `feature-a5-lobby`
Tests: `tests/test_lobby.py`

## Why
Everyone in a room needs to see, without asking around, who has joined, who has finished rating and whether the vote has started or is over. The creator also needs one place to end the collecting phase and start the vote, which B2 (rating) depends on.

## What
F7 in `docs/concept.md`: the page polls the room status every 3–5 seconds and shows who has joined, who is done and whether the room is closed. `AGENTS.md`: live updates use `<meta http-equiv="refresh" content="4">`, no JavaScript; creator-only actions check the creator flag on the server.

Plus, decided by Track A (proposed in the review of PR #11, B2): the creator starts the rating phase here (`POST /api/rooms/{id}/start` in `docs/concept.md` §8, here `/rooms/<room_id>/start`).

"Joined" means the same as in A3/A4: the token in the signed session belongs to a participant of this room in the database.

**Pages and flow (Post/Redirect/Get).**
- `GET /rooms/<room_id>/lobby` (the lobby):
  - unknown room → 404;
  - not joined → redirect (302 or 303) to `GET /rooms/<room_id>`, where the join form is;
  - joined (creator or not) → the lobby page.
- The lobby is a page of its own because a refreshing page would wipe text someone is typing; the room page with the join and add-option forms (A3/A4) does **not** refresh.
- The lobby shows:
  - the heading `Lobby` and the room title;
  - the room status as text: `collecting` → `Collecting options.`, `voting` → `Voting has started.`, `closed` → `This room is closed.`;
  - every participant's nickname in the order they joined; the creator marked `(creator)`, everyone with `has_finished = 1` marked `done`. Nicknames are escaped;
  - `<n> of <m> done`, counted over all participants;
  - the number of options, e.g. `3 options`;
  - while `collecting`: for the creator a form with a `Start voting` button posting to `/rooms/<room_id>/start`; for everyone else `Waiting for the creator to start the voting.`;
  - while `voting`: a link to the rating page `/rooms/<room_id>/vote` (built in B2);
  - a link back to the room page (`/rooms/<room_id>`).
- While the room is not `closed`, the lobby contains `<meta http-equiv="refresh" content="4; url=/rooms/<room_id>/lobby">`. The `url=` matters: a rejected start is rendered as the response to `POST /rooms/<room_id>/start`, and a plain refresh would repeat that URL as a GET. When the room is `closed` there is nothing left to wait for, so no refresh.
- `base.html` gets an empty `{% block head %}` so a page can add the refresh tag.
- The room page (`GET /rooms/<room_id>`) for a joined participant shows a link to the lobby. It never contains a meta refresh.
- The room page for a visitor of a `closed` room shows `This room is closed. You can no longer join.` instead of the join form (left open in A3).

**Start voting: `POST /rooms/<room_id>/start`.**
- unknown room → 404;
- not joined, or joined but not the creator → status 403 with `Only the creator can start the voting.`, nothing changed. Hiding the button is not a permission check (`AGENTS.md`);
- invalid → the lobby again with status 400 and the message; the room status is unchanged;
- valid → sets the room status from `collecting` to `voting` and redirects (302 or 303) to the lobby.

**Rules and messages** (checked in this order, only the first matching message is shown; rules live in `app/services/lobby.py`):

| Rule | Message |
|---|---|
| room status is not `voting` | `Voting has already started.` |
| room status is not `closed` | `This room is closed.` |
| the room has at least 2 options | `Add at least 2 options before starting the voting.` |
| the database finds the room no longer `collecting` (two clicks at the same moment) | `Voting has already started.` |

`db.start_voting(room_id)` changes the status only if it is still `collecting` (`UPDATE … WHERE id = ? AND status = 'collecting'`) and returns whether a row was changed, so two simultaneous starts change the room once and the second gets the message. It runs inside C1's `db.transaction()`.

Checks (one line = one test):
- [ ] Lobby: a joined participant gets the lobby page with `Lobby`, the room title and a link back to the room page.
- [ ] Lobby: shows every participant's nickname in the order they joined, the creator marked `(creator)`.
- [ ] Lobby: participants with `has_finished = 1` are marked `done`, others are not; it shows `<n> of <m> done`.
- [ ] Lobby: shows the number of options.
- [ ] Lobby: shows the status text for `collecting`, `voting` and `closed`.
- [ ] Lobby: contains the meta refresh with `content="4; url=/rooms/<room_id>/lobby"` while `collecting` and `voting`, and none when `closed`.
- [ ] Lobby: while `collecting`, the creator sees the `Start voting` form; another participant sees no form and `Waiting for the creator to start the voting.`
- [ ] Lobby: while `voting`, the page links to `/rooms/<room_id>/vote` and shows no `Start voting` form.
- [ ] Lobby: a nickname with HTML is shown escaped, never as a tag.
- [ ] Lobby: a visitor who has not joined is redirected to the room page; a token of another room's participant counts as not joined.
- [ ] Lobby: unknown room – 404.
- [ ] Room page: a joined participant sees a link to the lobby; the room page has no meta refresh.
- [ ] Room page: a visitor of a `closed` room sees `This room is closed. You can no longer join.` and no join form; in `collecting` and `voting` the join form is still there.
- [ ] Accepted: the creator starts the voting with 2 options – status `voting`, redirect to the lobby.
- [ ] Accepted: after starting, options can no longer be added (A4's rule, now reachable through the app).
- [ ] Rejected: fewer than 2 options (0 or 1) – status 400, message, status unchanged.
- [ ] Rejected: starting when the status is `voting` or `closed` – status 400, message, status unchanged.
- [ ] Rejected: a participant who is not the creator – status 403, message, status unchanged.
- [ ] Rejected: a visitor (no token, or a token that is not in the database) – status 403, status unchanged.
- [ ] Rejected: unknown room – 404.
- [ ] Rejected: the rejected start page refreshes to the lobby URL, not to `/start`.
- [ ] Edge case: if the database finds the room already started (status check bypassed, as in a race), the second start shows `Voting has already started.`, does not crash and the room stays `voting`. The test replaces `db.get_room` to simulate the race.
- [ ] Review #15: while `collecting`, the creator with fewer than 2 options sees `Add at least 2 options before starting the voting.` on the lobby page itself (next to the button), so it survives the refresh; nobody else sees it, and a rejected start shows the message only once.
- [ ] Review #15: an unknown room status gives an empty status text instead of an error, so the lobby still loads.
- [ ] Persistence: after an app restart, the lobby still shows the participants, `done` marks and the `voting` status.

## Out of scope
- The rating page itself and setting `has_finished` (B2). The tests set `has_finished` and the status directly in the database. The link to `/rooms/<room_id>/vote` only works once B2 is merged.
- Closing the room and the result page (B3), the deadline (B5), the QR code (A6).
- Showing who rated what or any counts per option – never (`AGENTS.md`, votes are private).
- A database guarantee that no option is added in the same moment the creator starts the voting (A4 checks the status first, then inserts). Same class as the accepted races in A3/A4.
- JavaScript polling or WebSockets (F21).
- No changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_lobby.py` and all earlier tests pass (`uv run pytest`), output pasted.
- SQL only in `app/db.py`, rules in `app/services/lobby.py` (type hints, no Flask, no database), thin routes in `app/routes/rooms.py`, Jinja templates.
- In the browser, the lobby updates by itself when someone joins; the creator can start the voting; anyone else cannot.
- The lobby survives an app restart.
- `docs/plan.md` says that A5 includes starting the voting.
- Work is on branch `feature-a5-lobby`, pushed, pull request opened with mkim-nova as reviewer.
