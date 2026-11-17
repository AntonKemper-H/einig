# A11 – F28 Hidden collecting: everyone sees only their own ideas until voting

Branch: `feature-a11-hidden-collecting`
Tests: `tests/test_hidden_collecting.py`

Decision: `docs/decisions.md`, D17. Built after **C9** (the `room_setups` table with `hide_ideas` and `reveal_places`, and the setup form) and **B6** (room page layout) are merged. Uses A7's `option_authors` to know whose option is whose. No schema change.

## Why
When everyone sees everyone's ideas while collecting, people copy or simply wait for the loudest person's suggestion. Keeping ideas secret until voting makes each person bring their own, and keeping the app's suggestions secret turns "Surprise me" into a real surprise. Rooms that do not choose this must behave exactly as today.

## What

### Decisions in this spec (please check in the review)
- **Two choices in the C9 setup form** (creator only, while collecting, saved with `Save setup`):
  - `Keep everyone's ideas secret until voting` (checkbox, `hide_ideas`). **Checked by default** in the form of a room that has no setup yet.
  - `Show suggested places to everyone before voting` (checkbox, `reveal_places`), only in `nearby` and `surprise` rooms. Checked by default.
- **"Own ideas"** are options with a row in `option_authors` (A7): typed options and places found by name (C6). **"Suggested places"** are Google options without an author (from "Places nearby" / "Surprise me").
- **Who sees what while `collecting`**, for every joined participant, the creator included:

| Option | `hide_ideas = 0` | `hide_ideas = 1` |
|---|---|---|
| own idea | shown | shown |
| someone else's idea | shown | hidden |
| suggested place, `reveal_places = 1` | shown | shown |
| suggested place, `reveal_places = 0` | hidden | hidden |

- **Instead of hidden options** a line with their number: `Others have added 4 ideas.` and/or `5 suggested places are waiting – you will see them when the voting starts.` The number reveals progress, not content.
- **From `voting` on, everything is shown** as today (rating cards, overview, result). Who added an option is never shown, also not after the reveal (D14).
- **"Been there"** (C5) only on visible places, so not in a room with `reveal_places = 0`; the route rejects it there too (`"Been there" is not available while the suggested places are secret.`, status 400, nothing changed).
- **Duplicates:** in a room with `hide_ideas = 1`, adding a label that already exists as someone else's idea is rejected with `Someone already had the same idea – it is already in the room.` (status 400, nothing saved). Adding a label that is the participant's own existing option keeps the normal message. Without `hide_ideas`, messages are unchanged.
- **Deleting (F24):** only visible options can be deleted from the page; the delete route treats an option that is hidden from this participant **exactly like an unknown option**: a 303 redirect to the room page, nothing deleted, no message. A7 answers an unknown, already deleted or replaced option this way, and frozen A7 tests pin it (`test_option_id_that_does_not_exist_is_ignored`, `test_deleting_twice_changes_nothing_the_second_time`, `test_replaced_option_is_ignored`). Any other answer (e.g. a 400) would let someone try ids one by one and learn where hidden ideas are. So in a hidden room the creator cannot delete other people's ideas (D17).
- **Lobby:** unchanged (it shows only the number of options).
- **The creator's search result:** with `reveal_places = 0` the creator does not see the places either, only their number; the search form's "already searched" behaviour (C2a/C4) is unchanged.
- **Changing the choices while collecting** takes effect immediately on the next page view; nothing is deleted.

### Code
- A pure function in `app/services/options.py`: `visible_options(options: list, participant_id: int, hide_ideas: bool, reveal_places: bool) -> tuple[list, int, int]` – the options this participant may see (in the original order), the number of hidden ideas and the number of hidden suggested places. Each option has `added_by` (participant id or `None`) as `db.get_options` returns it since A7.
- **The filter sits in `render_room_page(...)`** in `app/routes/rooms.py`, right where it loads `db.get_options(...)`, while the room is `collecting` and the room has a setup; otherwise all options as today. Every page that shows the room goes through it: `show_room` and every rejected action that shows the room page again with status 400 (add option, limit reached, duplicate, "Been there", delete, search errors). Filtering only in `show_room` would leak hidden options through those error pages. The Place Details calls are made only for **visible** Google options (hidden places cost nothing).
- C9's setup form, validation and `save_room_setup` are extended with the two values. The form sends a hidden marker field `privacy_choices=1`. **Only when the marker is present**, `validate_setup` reads the two checkboxes (present → 1, missing → 0; `reveal_places` is stored as 1 in a `manual` room). Without the marker (e.g. C9's frozen tests that post only kind and limit), both stored values stay as they are (defaults 0 and 1 for a new setup), so those tests keep their meaning.
- Add-option route, C6 save route, C5 been-there route and A7 delete route get the checks above. SQL only in `app/db.py`.

Checks (one line = one test), `tests/test_hidden_collecting.py`:
- [ ] `visible_options` follows the table above for all four combinations; the two counts are right; the order is kept.
- [ ] The setup form of a room without setup shows both checkboxes checked; the places checkbox is missing in a `manual` room.
- [ ] Accepted: saving the setup with the marker and `hide_ideas` stores 1; with the marker and without the field stores 0; without the marker both stored values stay unchanged; only the creator, only while collecting (C9's checks).
- [ ] `hide_ideas = 1`: creator and guest each add an idea; each sees only their own and `Others have added 1 idea.` (`1 idea`, `2 ideas`).
- [ ] `hide_ideas = 1`: a visitor (not joined) still sees no options at all.
- [ ] `hide_ideas = 0` with a setup, and rooms without a setup: everyone sees every option (as `test_options.py`).
- [ ] `reveal_places = 0`: after a "Surprise me" search, nobody (creator included) sees the places, only `5 suggested places are waiting …`; no Place Details call is made for them on the room page.
- [ ] `reveal_places = 1`: everyone sees the suggested places and the `Been there` button.
- [ ] Rejected: "Been there" on a secret place – 400, message, nothing changed, Google not called.
- [ ] Rejected: a guest types the same label as the creator's hidden idea – 400, `Someone already had the same idea – it is already in the room.`, nothing saved, the creator's idea is still not shown to the guest.
- [ ] Ignored: deleting someone else's hidden idea (also by the creator) – 303 to the room page, nothing deleted, the same response as for an option id that does not exist.
- [ ] Accepted: deleting one's own idea in a hidden room works.
- [ ] No leak through error pages: in a room with `hide_ideas = 1` and `reveal_places = 0`, a guest's rejected action (adding an option over the limit, an empty label, "Been there" on a secret place, an empty name in "Find on Google Maps" (C6)) shows the room page with 400, and that page contains none of the creator's hidden ideas and none of the secret places, only the counts.
- [ ] After `Start voting`, every participant's rating page shows all options (own, others', suggested places).
- [ ] The result page and the overview never show who added an option.
- [ ] The lobby shows the full number of options in a hidden room.
- [ ] Turning `hide_ideas` off while collecting shows everyone's options on the next page view; nothing is deleted.
- [ ] Persistence: after an app restart, the choices still apply.
- [ ] All earlier tests pass unchanged.

## Out of scope
- Hiding options from the lobby count, hiding the number of participants.
- Revealing options before voting by any other means (e.g. "reveal now" button), anonymous suggestions per person after the vote.
- Changing who may delete in rooms without hidden ideas (F24 stays as in A7).
- Schema changes (C9 created the columns), JavaScript, changes to existing tests.

## Done when
- All tests in `tests/test_hidden_collecting.py` and all earlier tests pass (`uv run pytest`), output pasted.
- On two phones: in a "Surprise me" room with both choices secret, each phone sees only its own idea and the counts; after starting the voting, all options appear on the rating cards.
- Work is on branch `feature-a11-hidden-collecting`, pushed, pull request opened for review.
