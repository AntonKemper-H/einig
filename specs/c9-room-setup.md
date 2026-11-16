# C9 – F27 Room setup: activity, kind and options per person

Branch: `feature-c9-room-setup`
Tests: `tests/test_activities.py` (catalogue and rules), `tests/test_room_setup.py` (schema, setup route, room page, limits, searches with fake Google answers)

Decision: `docs/decisions.md`, D17. Builds on A7 (`option_authors`, merged), C2a (`/suggest`), C4 (`/surprise`) and C5 ("Been there"). The new table is a schema change: Track A (schema owner, D10) reviews it.

## Why
Today a room only knows its title and where options come from; the creator picks "Restaurant / Bar / Café / Cinema" deep inside the search form, and anyone can add as many options as they like. The creator should say up front what the group is planning (brunch, bowling, a museum …) so that suggestions and surprises fit, and how many ideas each person may bring, while rooms without a setup keep working exactly as today.

## What

### Decisions in this spec (please check in the review)
- **One select for activity and kind:** a `<select name="kind">` with one `<optgroup>` per activity (e.g. `Food` → `Breakfast`, `Brunch`, `Restaurant (lunch or dinner)`). The value is `<activity>.<kind>`, e.g. `food.brunch`. No JavaScript is needed to make a second list depend on the first.
- **Only the creator, only while `collecting`.** The setup can be changed as often as needed until the voting starts; then it is fixed.
- **Optional:** a room without a setup works exactly as before (search forms with the category select, no limit). This keeps every existing room and test valid.
- **With a setup, the searches use the kind:** "Places nearby" searches all types of the kind in one call; "Surprise me" mixes the kind's types as its sub-categories. The category select disappears from the search forms of such a room; any posted `category` is ignored.
- **The search stays "once per room"** (C2a/C4): changing the setup after the search does not search again. The page says so (`The places were already suggested. Changing the activity does not search again.`).
- **Options per person:** `Unlimited` or 1–5. Counted are the participant's own options (rows in `option_authors`, A7: typed options and places found by name). Places from "Places nearby" / "Surprise me" have no author and never count. Lowering the limit below what someone already added deletes nothing; they just cannot add more.
- **"Been there" in a set-up room** replaces a place with another place of the same type (C5's fallback when the main category is unknown). Searching other types of the kind is out of scope.
- **Lunch and dinner** are not Google types, so they are not separate kinds (D17).
- **`hide_ideas` and `reveal_places`** are created in the table now (defaults 0 and 1, i.e. today's behaviour) because D17 asks for them, but this spec neither shows nor uses them; A11 does.

### Catalogue (`app/services/activities.py`, no Flask, no database)
`ACTIVITIES` is a module-level dict: activity key → `{"label": …, "kinds": {kind key → {"label": …, "types": [Google place types]}}}`. Starting list:

| Activity (label) | Kind (label) | Google types |
|---|---|---|
| `food` (Food) | `breakfast` (Breakfast) | `breakfast_restaurant`, `cafe`, `bakery` |
| | `brunch` (Brunch) | `brunch_restaurant`, `breakfast_restaurant`, `cafe` |
| | `restaurant` (Restaurant (lunch or dinner)) | the 13 cuisine types of `surprise.SUBCATEGORIES["restaurant"]` |
| `drinks` (Drinks & café) | `bar` (Bar) | `bar`, `pub`, `wine_bar`, `bar_and_grill` |
| | `cafe` (Café) | `cafe`, `coffee_shop`, `tea_house` |
| | `dessert` (Ice cream & dessert) | `ice_cream_shop`, `dessert_shop` |
| `sport` (Sport) | `bowling` (Bowling) | `bowling_alley` |
| | `climbing` (Climbing) | climbing gym type, see note |
| | `swimming` (Swimming) | `swimming_pool` |
| | `fitness` (Fitness) | `gym`, `fitness_center` |
| | `sports_ground` (Sports ground) | `sports_complex`, `sports_club` |
| `culture` (Culture & leisure) | `cinema` (Cinema) | `movie_theater` |
| | `museum` (Museum & gallery) | `museum`, `art_gallery` |
| | `theatre` (Theatre & concerts) | `performing_arts_theater`, `concert_hall` |
| | `amusement` (Amusement park & zoo) | `amusement_park`, `zoo`, `aquarium` |
| | `outdoors` (Park & hiking) | `park`, `hiking_area`, `national_park` |

**Note for the implementer:** check every type against Google's place type table for the Places API (New) ("Table A", the types allowed in `includedTypes`). Drop a type that is not listed and name it in the pull request; drop a kind that has no type left (e.g. `climbing` if Google has no climbing type). The restaurant list is copied, not imported from `surprise.py`, so `activities.py` stays independent; `surprise.SUBCATEGORIES` and `places.CATEGORIES` stay unchanged (reviewed tests check them).

Functions:
- `kind_choices() -> list[tuple[str, list[tuple[str, str]]]]` – for the template: `[(activity label, [(value "activity.kind", kind label), …]), …]` in catalogue order.
- `parse_kind(value: str | None) -> tuple[str, str] | None` – `"food.brunch"` → `("food", "brunch")`; anything not in the catalogue (missing, empty, no dot, unknown activity or kind, extra dots) → `None`.
- `kind_types(activity: str, kind: str) -> list[str]` and `kind_label(activity, kind) -> str` (e.g. `Food – Brunch`).
- `OPTIONS_PER_PERSON_CHOICES = [1, 2, 3, 4, 5]`; `parse_options_per_person(value: str | None) -> tuple[int | None, bool]` – `""` → `(None, True)` (unlimited), `"1"`–`"5"` → `(n, True)`, anything else → `(None, False)`.
- `validate_setup(form) -> tuple[dict, list[str]]` – `{"activity", "kind", "options_per_person"}` and messages `Please choose an activity.` / `Please choose how many options each person can add.`
- `limit_reached(own_option_count: int, options_per_person: int | None) -> bool`.

### Schema (`app/schema.sql`, a new table, so `init-db` adds it to the deployed database)
```
room_setups (
    room_id            TEXT PRIMARY KEY REFERENCES rooms (id) ON DELETE CASCADE,
    activity           TEXT NOT NULL CHECK (trim(activity) <> ''),
    kind               TEXT NOT NULL CHECK (trim(kind) <> ''),
    options_per_person INTEGER CHECK (options_per_person BETWEEN 1 AND 5),  -- NULL = unlimited
    hide_ideas         INTEGER NOT NULL DEFAULT 0 CHECK (hide_ideas IN (0, 1)),    -- used by A11 (F28)
    reveal_places      INTEGER NOT NULL DEFAULT 1 CHECK (reveal_places IN (0, 1))  -- used by A11 (F28)
)
```

### `app/db.py`
New: `get_room_setup(room_id)` (row or `None`), `save_room_setup(room_id, activity, kind, options_per_person) -> bool` (insert or update in one statement, `ON CONFLICT (room_id) DO UPDATE`, only while the room is `collecting`; returns `False` if the room is not collecting any more), `count_own_options(room_id, participant_id) -> int` (rows in `option_authors`, for the `1 of 3 options added` text).

New: `add_manual_option_within_limit(room_id, label, participant_id, options_per_person: int) -> str` – the limit is listed under "Rules for simultaneous actions" (AGENTS.md), so check and insert happen in **one transaction**, like `save_vote`:
1. Lock the room row: `UPDATE rooms SET status = status WHERE id = ? AND status = 'collecting'`; if no row changed → `"not_collecting"`, nothing saved.
2. Count the participant's rows in `option_authors` for this room; at or above `options_per_person` → `"limit"`, nothing saved.
3. Insert option and author row as `add_manual_option` does; a duplicate label (`UNIQUE (room_id, label)`) → `"duplicate"`, nothing saved. Otherwise `"added"`.

`add_manual_option` stays unchanged (rooms without a limit keep using it; its reviewed tests stay valid). The route's own `limit_reached(...)` check before the call stays as a fast path for the message, but the database result decides. **C6** ("save a place by name", not built yet) must save its author row through the same locked check once it exists; its spec takes this over.

### Route `POST /rooms/<room_id>/setup`

| Case | Status | Message | Saved |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined, or joined but not the creator | 403 | `Only the creator can set up the room.` | nothing |
| room not `collecting` (also when it changes in the same moment) | 400 | `The setup can only be changed before voting starts.` | nothing |
| invalid kind or options per person | 400 | the messages above, form shown again with the sent values | nothing |
| valid | 303 redirect to the room page | – | the setup (new or replaced) |

### Room page
- **Creator, collecting:** a section `Set up this room` at the top with the kind select and the options-per-person select (`Unlimited`, `1`–`5`), pre-filled with the saved setup, and the button `Save setup`. Before the first save, the section is open (`<details open>`); afterwards it is collapsed and its summary shows the setup.
- **Everyone joined:** a line with the setup, e.g. `Activity: Food – Brunch · Up to 3 options per person` (without a limit: no second part). Nothing if there is no setup.
- **Search forms (creator, `nearby`/`surprise`, set-up room):** no category select; instead `Searching for: Food – Brunch`. The other fields (radius, rating, price, location) stay.
- **Add form:** when the participant has reached the limit, instead of the form: `You have added 3 of 3 options.`; below the limit and with a limit, the form shows `1 of 3 options added`.

### Changes to existing routes and functions
- `places.validate_search(form, category_required: bool = True)` – with `False`, the category is not checked and not returned. Default unchanged.
- `places.search_nearby(..., included_types: list[str] | None = None)` – if given, sent as `includedTypes` instead of `[category]`. Default unchanged.
- `surprise.surprise_search(..., subcategory_pool: list[str] | None = None)` – if given, sub-categories are chosen from this list instead of `SUBCATEGORIES[category]` (same `SUBCATEGORIES_PER_SEARCH`, same widening). Default unchanged.
- `/suggest` and `/surprise` for a set-up room: validate with `category_required=False`, search with the kind's types, store in `filters` the main category `null` and the kind as `"kind": "food.brunch"` (C5's `read_filters` then gives `None` for the category, as decided above). Without a setup: unchanged.
- `/rooms/<id>/options` (manual add) in a room with a limit: saves through `db.add_manual_option_within_limit(...)`. `"limit"` (from the route's fast check or from the database) → status 400 and `You can add at most 3 options in this room.`; `"duplicate"` and `"not_collecting"` → the existing messages of A4; nothing saved in all three cases. Rooms without a limit: unchanged (`add_manual_option`).

Checks (one line = one test):

`tests/test_activities.py`
- [ ] Every activity has a label and at least one kind; every kind has a label and at least one type; every type matches `^[a-z_]+$`; no kind lists a type twice.
- [ ] `kind_choices` returns every activity with its kinds, in catalogue order, with values `activity.kind`.
- [ ] `parse_kind` accepts every catalogue value and rejects `None`, `""`, `"food"`, `"food."`, `".brunch"`, `"food.pizza"`, `"bowling.food"`, `"food.brunch.x"`.
- [ ] `kind_label("food", "brunch")` is `Food – Brunch`; `kind_types` returns the catalogue list.
- [ ] `parse_options_per_person`: `""` → unlimited; `"1"`–`"5"` → the number; `"0"`, `"6"`, `"-1"`, `"2.5"`, `"abc"`, `None` → invalid.
- [ ] `limit_reached`: never with unlimited; at and above the limit `True`, below `False`.
- [ ] `surprise.SUBCATEGORIES` and `places.CATEGORIES` are unchanged.

`tests/test_room_setup.py` (Google always faked)
- [ ] Schema: a fresh database has `room_setups` with the columns above; `init-db` on a database without it adds it and keeps all rooms; deleting a room deletes its setup.
- [ ] Accepted: the creator saves `food.brunch` with 3 → one row; redirect; every participant's room page shows `Activity: Food – Brunch · Up to 3 options per person`.
- [ ] Accepted: saving again replaces the setup (still one row).
- [ ] Rejected: a guest, a visitor and a participant of another room – 403, nothing saved.
- [ ] Rejected: an unknown or empty kind, an invalid options-per-person value – 400, messages, sent values shown again, nothing saved.
- [ ] Rejected: room `voting` or `closed` – 400, message, setup unchanged.
- [ ] Simultaneous: the route's status check sees `collecting`, but the database already says `voting` (another request started the voting) – `save_room_setup` returns `False`, 400, nothing saved.
- [ ] The creator's setup form is open before the first save and shows the saved values afterwards; guests see no setup form.
- [ ] A room without a setup: room page, search forms and adding options are exactly as before (category select shown, no limit text).
- [ ] Nearby search in a set-up room: no category select on the page; Google is called once with `includedTypes` = the kind's types; a posted `category` is ignored; `filters` stores the kind.
- [ ] Surprise search in a set-up room: the sub-categories come only from the kind's types; at most `SUBCATEGORIES_PER_SEARCH` searches per round.
- [ ] After the search, changing the setup does not search again, and the page says so.
- [ ] Limit: with 2 per person, a guest adds 2 options; the third is rejected with the message and not saved; another guest can still add 2.
- [ ] Simultaneous: the route's fast check sees "below the limit", but the database already holds the limit (another add a moment earlier) – `add_manual_option_within_limit` returns `"limit"`, 400, message, nothing saved, still exactly the limit in `option_authors`.
- [ ] `add_manual_option_within_limit` directly: `"added"`, `"limit"`, `"duplicate"` and `"not_collecting"` each in its case, and nothing saved in the last three.
- [ ] Limit: Google search results do not count (a room with 5 suggested places and a limit of 1: the guest can still add 1).
- [ ] Limit lowered from 3 to 1 after someone added 2: their options stay; they cannot add another one.
- [ ] Limit: the add form shows `1 of 3 options added`, and at the limit the text `You have added 3 of 3 options.` instead of the form.
- [ ] "Been there" in a set-up surprise room still works and searches the same type.
- [ ] Persistence: after an app restart, the setup and the limit still apply.

## Out of scope
- Lunch/dinner or any opening-hours filter, "open at the planned time".
- A setup at room creation on the home page, a group default setup, a group admin (D17); the group form of A9 uses this setup only once A9 is built after C9.
- Showing or using `hide_ideas` or `reveal_places`, hiding options (A11). Saving the setup in C9 leaves both columns unchanged. (A11 only reads the two checkboxes when its form sends a marker field, so the frozen C9 tests that post only kind and limit stay valid.)
- The limit for C6's "save a place by name" (C6 is not built yet; its spec uses `add_manual_option_within_limit`'s locked check).
- Searching again after a setup change, changing C5 to use other types of the kind.
- Changing `surprise.SUBCATEGORIES`, `places.CATEGORIES`, or any existing test.
- JavaScript.

## Done when
- All tests in both test files and all earlier tests pass (`uv run pytest`), output pasted.
- The pull request lists any Google type that was dropped because it is not in Table A.
- On the deployed app with a real key: a "Surprise me" room set to `Sport – Bowling` or `Culture & leisure – Museum & gallery` suggests fitting places.
- Work is on branch `feature-c9-room-setup`, pushed, pull request opened; Track A reviews the new table.
