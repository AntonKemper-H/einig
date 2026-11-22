# E3 – Remove a room from my list, and delete a room (creator)

Branch: `feature-e3-remove-and-delete-rooms` (cut from `main` after E2 is merged)
Tests: `tests/test_remove_delete_rooms.py`

Builds on A8/F25 ("My rooms" on the home page, `main.load_my_rooms`, `db.get_my_rooms`) and on the room cascades in `schema.sql` (`ON DELETE CASCADE` from `rooms` to participants, options, votes, vetoes, option authors, `group_rooms` and `room_setups`). No schema change.

**Scope note:** these two features (call them F31 "Remove from my list" and F32 "Delete room") are not in `docs/concept.md` and not in the "Build now" list of `AGENTS.md`. Before implementation the team adds a short decision (D22) to `docs/decisions.md` and extends the scope line in `AGENTS.md`. This spec only describes the work.

## Why
"My rooms" only grows. Old, finished or mistaken rooms stay in the list forever, and a creator who made a room by accident cannot get rid of it. Two different needs:
1. **Tidy my list:** I no longer want to see this room, but the others still do.
2. **Delete for everyone:** I created this room and want it gone.

## What

### F31 – Remove from my list (everyone in the room)
- Every tile of "My rooms" gets a **Remove** button (at least 44 px high). It is a GET form that opens a confirmation page (`GET /rooms/<id>/forget`, changes nothing, redirects home if there is nothing to remove). The removal itself is the POST below. The explanation is shown once below the list and on the confirmation page, not on every tile (review of #85).
- `POST /rooms/<room_id>/forget` removes this room's token from `session["participant_tokens"]` and redirects (Post/Redirect/Get) to the home page. Nothing in the database changes: the participant, their ratings and vetoes stay, the room stays for everyone else, and the result is still computed with their votes.
- It also works for a room that no longer exists (idempotent): the token is removed if present, no error.
- Opening the room link again later lets the person join as a new participant; their old identity (and, for a creator, the creator role) is not recovered, because the cookie token is the only proof of identity. The button text and a line under it say so: `Removes the room from your list on this device. You cannot get back into it as the same person.`
- **Creator, room not closed:** the creator may remove too, but the room then has no one who can start the voting or close it. The list (once) and the confirmation page show the extra line `You are the creator: nobody else can start or close this room.` (Decision to check in the review: warn, do not forbid. The creator who wants the room gone uses F32 instead.)

### F32 – Delete room (creator only)
- Only the **creator** of a room, in **any status** (collecting, voting, closed), can delete it. Creator = the participant of the browser's session token with `is_creator = 1`, as everywhere else.
- Two steps, no JavaScript:
  1. `GET /rooms/<room_id>/delete` shows a confirmation page: the room title, the number of participants, and `This deletes the room for everyone: all options, ratings and the result. This cannot be undone.` with two buttons: **Delete room** (POST) and **Cancel** (link back to the room).
  2. `POST /rooms/<room_id>/delete` deletes the room and redirects to the home page with the flash/notice `Room "<title>" was deleted.`
- The room tiles in "My rooms" show a **Delete** link (to the confirmation page) only where `is_creator` is true. The room page of the creator also gets this link (small, at the bottom, so it is not pressed by accident).
- The database call is one `DELETE FROM rooms WHERE id = ?` in `db.py` (`delete_room(room_id) -> bool`); the cascades remove everything that belongs to the room, including its row in `group_rooms` (so the room also disappears from the group page; the group itself and its members stay).
- **Rejected, data unchanged:**
  - not joined (no token for this room, or a token that matches no participant) → 403, nothing deleted;
  - joined but not the creator → 403 with the message `Only the creator can delete this room.`, nothing deleted; the confirmation page (GET) is refused the same way;
  - room does not exist (or was deleted a moment ago by another request) → the POST changes nothing and redirects to the home page; the GET shows the normal 404 page. Deleting twice is therefore harmless.
- **Other participants:** their cookies still hold the old token. `load_my_rooms` already drops tokens of deleted rooms, so the room vanishes from their list on the next visit of the home page; opening the old link shows the 404 page (`404.html` already mentions deleted rooms).
- Waiting/lobby/vote pages that are refreshing (`meta refresh`) at the moment of deletion simply end on the 404 page. No special handling.

### Not in scope
- Removing or deleting **groups** (F16). Same idea, but a group has members and a history of rooms; it needs its own decision.
- Restoring a deleted room, "trash", or soft delete.
- Deleting several rooms at once.
- Any change to the winner algorithm, voting rules or the close logic.

## Acceptance tests (written first, reviewed by the team before implementation)

**Remove (F31)**
- Accepted: after `POST /rooms/<id>/forget` the home page no longer lists the room; the room, participant and votes still exist in the database; the creator of the room still sees it in their own browser.
- Rejected / unchanged: a forget for a room the browser never joined changes nothing and does not raise an error.
- Idempotent: forgetting twice, and forgetting a deleted room, both redirect to the home page.
- Persistence: after the remove, opening the room link as the same browser gives the join page (new participant), not the old identity.
- Creator warning line appears for a creator's not-closed room and not for others.

**Delete (F32)**
- Accepted: the creator's `POST /rooms/<id>/delete` in each status (collecting, voting, closed) removes the room and, with it, its participants, options, votes, vetoes, authors, setup and `group_rooms` row (count rows before and after).
- The group of a deleted group room still exists with its members.
- Rejected: a non-creator participant gets 403 and the room, options and votes are unchanged; a browser without a token gets 403 and nothing changes; the same for the confirmation page.
- Confirmation page for the creator shows the title and the warning text; reloading it deletes nothing (only the POST deletes).
- Idempotent: a second POST for the same room redirects to the home page without an error.
- After deletion another participant's home page no longer lists the room (and their cookie token is cleaned), and the old room link gives 404.
- Two requests for the same delete at the same moment: one deletes, the other changes nothing.
- A delete and a simultaneous vote never leave orphan rows (the vote either happened before and is deleted with the room, or is rejected because the room is gone).

## Files expected to change
`app/db.py` (`delete_room`), `app/routes/rooms.py` (`forget_room`, `delete_room_page`, `delete_room`), `app/routes/main.py` (only if the notice needs it), `app/templates/home.html` (buttons), `app/templates/room.html` (creator's delete link), `app/templates/delete_room.html` (new), `app/static/css/` (small button styles), `tests/test_remove_delete_rooms.py` (new), `docs/decisions.md` and `AGENTS.md` (D22 and scope line, after team approval).
