# A7 – F24 Delete an option

Branch: `feature-a7-delete-option`
Tests: `tests/test_delete_option.py`

## Why
A typo or a joke entry stays in the room until the end, and everyone has to rate it. The person who added an option, or the room creator, should be able to remove it before the voting starts, without ever being able to throw away other people's ratings.

## What
F24 in `docs/decisions.md` D14 (proposed in PR #37), and the domain rule in `AGENTS.md`: deleting an option is allowed only while the room is `collecting`, by the participant who added it or by the creator; deleting an option that is already gone changes nothing.

"Joined" means the same as in A3–A5: the token in the signed session belongs to a participant of this room in the database.

**Who added an option: a new table, not a new column.** D14 suggests a column `options.added_by`. A reviewed test (`tests/test_been_there_route.py`, C5) checks the exact column list of `options`, and reviewed tests must not be edited. So the author is stored in a new table instead:

```sql
CREATE TABLE IF NOT EXISTS option_authors (
    option_id      INTEGER NOT NULL,
    room_id        TEXT NOT NULL,
    participant_id INTEGER NOT NULL,
    PRIMARY KEY (option_id),
    FOREIGN KEY (option_id, room_id) REFERENCES options (id, room_id) ON DELETE CASCADE,
    FOREIGN KEY (participant_id, room_id) REFERENCES participants (id, room_id) ON DELETE CASCADE
);
```

- One row per manually added option: who added it. Both foreign keys include `room_id`, so the author is always a participant of the option's room. Deleting the option deletes its row.
- Options from "Places nearby" (F8) and "Surprise me" (F12, F13) have no row: the search adds them for the group, so only the creator can delete them (D14).
- **Deployed database:** Render runs `init-db` on every start, and `CREATE TABLE IF NOT EXISTS` adds the new table to the existing Postgres database without touching other data. No `ALTER TABLE` and no `reset-db` needed. Manual options saved before A7 have no row, so only the creator can delete them.
- `db.add_manual_option` saves the option and its author row in one `db.transaction()` (both or neither), reading the new id with `RETURNING id`.

**Room page (`GET /rooms/<room_id>`).** While the room is `collecting`, a joined participant sees a `Delete` button (a small form, `POST`) next to every option they may delete: for the creator every option, for anyone else only the options they added. In `voting` and `closed` nobody sees one. Who added an option is never shown to anyone; it is only used for this check.

**Delete: `POST /rooms/<room_id>/options/<option_id>/delete`** (`option_id` is a number; anything else is 404 from the URL rule). Checked in this order:

| Case | Response |
|---|---|
| unknown room | 404 |
| not joined (no token, or a token that is not a participant of this room) | 403, room page with `Please join the room before deleting options.` |
| the option is not an active option of this room (already deleted, replaced with "Been there", or the id belongs to another room) | ignored: redirect (303) to the room page, nothing changed |
| room status is not `collecting` | 400, room page with `Options can only be deleted before voting starts.` |
| the participant is neither the creator nor the person who added the option | 403, room page with `Only the person who added this option or the creator can delete it.` |
| the database finds the room no longer `collecting` (start at the same moment) | 400 with `Options can only be deleted before voting starts.` |
| the database finds the option already gone (two presses at the same moment) | ignored: 303 to the room page |
| valid | the option is deleted, redirect (303) to the room page |

Messages are shown in the existing option message list on the room page. Rules live in `app/services/options.py` (no Flask, no database), SQL in `app/db.py`.

`db.delete_option(room_id, option_id)` deletes only if the option is still active and the room is still `collecting`, in one statement (`DELETE … WHERE id = ? AND room_id = ? AND is_replaced = 0 AND EXISTS (… rooms.status = 'collecting')`), inside `db.transaction()`, and returns whether a row was deleted. If not, the route looks the option up again: still there and active means the room stopped collecting (400); gone means another request deleted it first (303).

Checks (one line = one test):
- [ ] Accepted: a participant deletes an option they added – redirect to the room page, the option is gone from the database and the page.
- [ ] Accepted: the creator deletes an option another participant added.
- [ ] Accepted: the creator deletes a Google option (no author).
- [ ] Accepted: the creator deletes an option they added themselves.
- [ ] Accepted: after deleting, the same label can be added again.
- [ ] Accepted: deleting leaves no row in `option_authors`, and other options are unchanged.
- [ ] Accepted: the lobby counts one option less; with only one option left, starting the voting is rejected (A5's rule).
- [ ] Saved: adding an option stores who added it (`option_authors` row with the participant's id and the room).
- [ ] Page: a participant sees a `Delete` form for their own option and none for options of others or Google options.
- [ ] Page: the creator sees a `Delete` form for every option.
- [ ] Page: in `voting` and `closed` nobody sees a `Delete` form.
- [ ] Page: who added an option is not shown to other participants.
- [ ] Rejected: a participant who is neither author nor creator – 403, message, option unchanged.
- [ ] Rejected: a participant who is not the creator deletes a Google option – 403, option unchanged.
- [ ] Rejected: a manual option saved before A7 (no author row) – only the creator can delete it.
- [ ] Rejected: room is `voting` or `closed` – 400, message, option unchanged (also for the creator).
- [ ] Rejected: a visitor (no token, or a token of another room's participant) – 403, message, option unchanged.
- [ ] Rejected: unknown room – 404.
- [ ] Rejected: an option id of another room – that option is unchanged, even for the creator of this room.
- [ ] Rejected: a non-numeric option id – 404; `GET` on the delete URL – 405.
- [ ] Ignored: deleting the same option twice – the second request redirects to the room page and changes nothing.
- [ ] Ignored: an option replaced with "Been there" – nothing changes.
- [ ] Edge case: if the database finds the room already `voting` (status check bypassed, as in a race), the delete shows `Options can only be deleted before voting starts.`, does not crash and the option stays. The test replaces `db.get_room` to simulate the race.
- [ ] Migration: `init-db` on a database without `option_authors` creates it and keeps all existing rooms and options.
- [ ] Persistence: after an app restart, a deleted option stays deleted and the author can still delete their other option.

## Out of scope
- A confirmation page before deleting (decided: the button deletes directly; a manual option can be typed again).
- Deleting during `voting` or `closed`, and undo.
- Editing an option's label.
- Showing who added an option, anywhere.
- Finding a place by name (F23, C6, Track C).
- Changing the `options` table or any existing test.

## Done when
- All tests in `tests/test_delete_option.py` and all earlier tests pass (`uv run pytest`), output pasted.
- SQL only in `app/db.py`, rules in `app/services/options.py`, thin route in `app/routes/rooms.py`, Jinja template.
- In the browser: the author and the creator can delete, nobody else sees the button, and nothing can be deleted after the voting starts.
- After the deploy, the room page works on Render and an option can be deleted (the new table was created by `init-db`).
- `docs/decisions.md` D14 and `docs/plan.md` A7 name the `option_authors` table instead of `options.added_by` (once PR #37 is merged).
- Work is on branch `feature-a7-delete-option`, pushed, pull request opened with mkim-nova as reviewer.
