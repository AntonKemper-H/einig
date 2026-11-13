# A4 – F3 Add options manually

Branch: `feature-a4-add-options`
Tests: `tests/test_options.py`

## Why
A group can only decide between things that are on the list, so every participant must be able to add what they have in mind ("Pizza place", "Cinema") before the rating starts. Empty entries and duplicates would make the rating confusing and split votes between two copies of the same idea, so they are rejected.

## What
F3 in `docs/concept.md`: all participants can add options as long as the rating phase has not started. Empty entries and duplicates are rejected.

"Joined" means the same as in A3: the token in the signed session belongs to a participant of this room in the database.

**Flow (Post/Redirect/Get).**
- `GET /rooms/<room_id>` for a joined participant (creator or not) additionally shows:
  - the heading `Options` and every option of the room in the order it was added (its `label`), or `No options yet.` if there are none;
  - while the room status is `collecting`: a form with a text field `label`, posting to `/rooms/<room_id>/options`;
  - while the status is `voting` or `closed`: the text `Options can no longer be added.` instead of the form.
- Visitors who have not joined see neither the option list nor the add form (only the A3 join form).
- `POST /rooms/<room_id>/options`:
  - unknown room id → 404, nothing saved;
  - not joined → status 403 with `Please join the room before adding options.`, nothing saved. A hidden form is not a permission check (AGENTS.md);
  - invalid → the room page again with status 400, the message and the entered text; nothing saved;
  - valid → saves an option (`source = 'manual'`, the cleaned `label`, `place_id` and `category` empty, `is_replaced = 0`) and redirects (302 or 303) to `GET /rooms/<room_id>`.
- The label is cleaned with `.strip()` before checking and saving.
- Duplicates are found in Python, like nicknames in A3: `db.get_option_labels(room_id)` returns the labels of the room, and `app/services/options.py` compares them with `casefold()`, so SQLite and Postgres behave the same.

**Rules and messages** (length counted after `.strip()`; checked in this order, only the first matching message is shown):

| Rule | Message |
|---|---|
| room status is `collecting` | `Options can only be added before voting starts.` |
| label not empty | `Please enter an option.` |
| at most 80 characters | `An option can be at most 80 characters.` |
| not already in this room's list, ignoring upper/lower case (also Ä, É …); the entered spelling is stored | `This option is already in the list.` |
| the database refuses the insert (e.g. two people add the same option at the same moment) | `Something went wrong while adding the option. Please try again.` |

Checks (one line = one test):
- [ ] Joined participant, room `collecting`, no options: the page shows `Options`, `No options yet.` and the add form with `label` posting to `/rooms/<room_id>/options`.
- [ ] Visitor (not joined): no add form and no option list.
- [ ] Accepted: a valid label redirects to the room page.
- [ ] Accepted: the option is stored with `source = 'manual'`, the label, empty `place_id` and `category`, `is_replaced = 0`.
- [ ] Accepted: the label is stored without leading/trailing whitespace.
- [ ] Accepted: after adding, the option appears on the room page; several options appear in the order they were added.
- [ ] Accepted: the creator and a joined participant can both add options, and both see all options.
- [ ] Accepted: the same label in a different room.
- [ ] Edge case: a label of exactly 80 characters (plus surrounding whitespace) is accepted.
- [ ] Edge case: a label with HTML (`<script>…`) is stored as typed and shown escaped, never as a tag.
- [ ] Rejected: empty, missing or whitespace-only label – message, status 400, data unchanged.
- [ ] Rejected: label over 80 characters – message, data unchanged.
- [ ] Rejected: label already in the list, exactly, with other upper/lower case (incl. non-ASCII letters) or with extra whitespace – message, data unchanged.
- [ ] Rejected: the form is shown again with the entered label.
- [ ] Rejected: adding while the room is `voting` or `closed` – message, data unchanged; the page shows `Options can no longer be added.` and no add form.
- [ ] Rejected: a visitor who has not joined (no token, or a token that is not in the database) – status 403, message, data unchanged.
- [ ] Rejected: a participant of another room cannot add to this room – status 403, data unchanged.
- [ ] Rejected: unknown room – 404, nothing saved.
- [ ] Edge case: if the database refuses the insert (duplicate check bypassed, as in a race), the app shows the "Something went wrong" message and does not crash. The test replaces `db.get_option_labels` to simulate the race.
- [ ] Persistence: after an app restart, the options are still stored and shown.

## Out of scope
- Google options, place details, categories (C2/C4) and "Been there" (C5/F13).
- Editing or deleting options; a maximum number of options per room.
- Starting the rating phase (A5 sets `voting`); the rating itself (B2).
- Remembering who added an option (the schema has no column for it).
- Unicode normalisation (NFC/NFD) of labels and nicknames – noted in review of #9, separate follow-up if wanted.
- Switching `app/db.py` to C1's `db.transaction()` / `db.INTEGRITY_ERRORS` (follow-up after C1, as for A2/A3).
- CSRF protection (team decision pending).
- No changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_options.py` and all earlier tests pass (`uv run pytest`), output pasted.
- SQL only in `app/db.py`, rules in `app/services/options.py`, thin route in `app/routes/rooms.py`, Jinja templates.
- Adding works in the browser for creator and joined participants; a rejected option shows a message and stores nothing.
- Options survive an app restart.
- Branch rebased on `main` after A3 is merged, pushed, pull request opened with mkim-nova as reviewer.
