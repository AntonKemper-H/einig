# C5 – F13 "Been there": replace a surprise place

Branch: `feature-c5-been-there`
Tests: `tests/test_been_there.py` (the replacement rules and the Google calls, with fake responses) and `tests/test_been_there_route.py` (room page, route, lobby)

Builds on C4 (`specs/c4-surprise-mode.md`): a "Surprise me" room has Google options whose `category` is a sub-category (e.g. `thai_restaurant`), and the room row stores the search centre, `radius_m` and `filters` JSON `{"category", "min_rating", "max_price_level", "requested_radius_m"}`. The tests set up this data directly in the database, so they do not depend on how C4 searches. C5 is built after C4 is merged, because it adds to C4's `app/services/surprise.py`.

## Why
Surprise mode is meant to bring the group somewhere new, so a place someone already knows defeats the purpose. Anyone in the group can say "Been there", and the place is swapped for a new one for everyone, while each swap stays cheap (at most two small Google calls), never shows who pressed it, and never leaves the room half changed.

## What
F13 in `docs/concept.md` ("Button on every card in surprise mode. The place is replaced with a new one for everyone"). `AGENTS.md`, rules for simultaneous actions: "'Been there' (replace option): the first request replaces it; later requests for the same, already replaced option are ignored." and "Adding options: only while the room status is `collecting`."

"Joined" means the same as in A3/A4: the token in the signed session belongs to a participant of this room in the database. "Active option" means an option with `is_replaced = 0`.

### Decisions in this spec (please check in the review)
- **Only while collecting.** Replacing adds an option, and options can only be added while the room is `collecting`. During voting, a swap would change the cards people are rating, and the joker (F10) already covers "not this one".
- **Every joined participant** can press it, not only the creator (F13: "for everyone"). Nobody is told who pressed it, and it is not stored.
- **Only Google options** in a `surprise` room have the button. Manual options are the group's own ideas; whoever does not like them can rate them "Rather not".
- **Same kind first:** the new place is searched in the same sub-category as the replaced one (a Thai place is replaced by another Thai place), so the variety C4 created stays. Only if that finds nothing new, one other sub-category is tried.
- **At most 5 replacements per room** (`MAX_REPLACEMENTS_PER_ROOM`), so one person pressing the button again and again cannot run up the Google bill. This is a cost guard, not a fairness rule: two presses at the same moment may go one over the limit, which is accepted.
- **Nothing new found → the option stays.** The room is only changed when a new place exists (rejected actions leave data unchanged); the group can still add a manual option or use the joker later.

### Replacement rules (pure functions in `app/services/surprise.py`, no Flask, no database)

Constants (module level): `MAX_REPLACEMENTS_PER_ROOM = 5`.

- `read_filters(filters_text: str | None) -> dict` returns `{"category": …, "min_rating": …, "max_price_level": …}` from the room's `filters` JSON. A missing key, a value of the wrong type (`true`/`false` count as wrong, `2.5` is not a price level), `None`, or text that is not valid JSON gives `None` for that key (never an error). `min_rating` is a float (an int like `4` becomes `4.0`), `max_price_level` an int; `category` is kept only if it is a key of `SUBCATEGORIES`.
- `replacement_subcategories(main_category: str | None, replaced_subcategory: str, active_subcategories: list[str], rng) -> list[str]` returns one or two sub-categories to search, in order:
  1. always `replaced_subcategory` first;
  2. then **one** other sub-category of `main_category`, picked with `rng`: preferably one that no active option has (`active_subcategories`); if every other one is already used, any other one. Never the replaced one again.
  3. If `main_category` is `None` or has no other sub-category, only the first.
- `pick_replacement(place_ids: list[str], known_place_ids: set[str], rng) -> str | None` returns a random place id (`rng.choice`) from `place_ids` that is **not** in `known_place_ids`, or `None` if there is none. Why random: Google sorts by popularity, and a surprise should not always be the best-known place (as in C4). Why `known_place_ids` contains every place id of the room, also the replaced ones: the place someone has been to must never come back, and the database allows each place only once per room.
- `find_replacement(api_key, latitude, longitude, radius_m, subcategories, max_price_level, min_rating, known_place_ids, rng) -> tuple[str, str] | None` calls `places.search_nearby(...)` (C2a's call, unchanged: field mask, `maxResultCount` 15, timeout 5 s, price and rating filters) for each sub-category in order, with the same centre, radius and filters, and returns `(place id, sub-category)` from the first sub-category where `pick_replacement` finds a new place; later sub-categories are then not searched. `None` if none does. **A `PlacesError` from any call is raised at once** (no further calls).

At most 2 Google calls per press, usually 1.

### Room page

`GET /rooms/<room_id>` for a **joined** participant of a `surprise` room with status `collecting`:
- Shows only **active** options (also in every other room, see `app/db.py` below), so a replaced place disappears for everyone.
- Every Google option's card gets a small form posting to `/rooms/<room_id>/options/<option id>/been-there` with one submit button `Been there`. Manual options get none.
- No button in `manual` or `nearby` rooms, in rooms that are `voting` or `closed`, and for visitors (they see no options at all, as before).
- If `filters` cannot be read or has no main category, the button is still shown (the replacement then only searches the same sub-category).

### Route `POST /rooms/<room_id>/options/<option_id>/been-there`

`<option_id>` is an integer in the URL (`<int:option_id>`): anything else is Flask's 404. Checked in this order:

| Case | Status | Message | Saved |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined (visitor, or participant of another room) | 403 | `Please join the room before adding options.` | nothing |
| option id is not an option of this room | 400 | `This option does not exist in this room.` | nothing |
| room mode is not `surprise` | 400 | `"Been there" is only available in a "Surprise me" room.` | nothing |
| room status is not `collecting` | 400 | `Options can only be added before voting starts.` | nothing |
| option is a manual option | 400 | `Only places from Google Maps can be replaced.` | nothing |
| option is already replaced | 303 redirect to `GET /rooms/<room_id>` (**ignored**, no message) | – | nothing; Google is not called |
| the room already has `MAX_REPLACEMENTS_PER_ROOM` replaced options | 400 | `This room has already replaced 5 places. You can still add options yourself.` | nothing; Google is not called |
| `GOOGLE_MAPS_API_KEY` is not set, or the room has no stored centre or radius | 503 | `Place suggestions are not available right now. You can still add options yourself.` | nothing; Google is not called |
| `find_replacement` raises `PlacesError` | 503 | same message as above | nothing |
| no new place found | 200 | `No other place was found nearby, so this place stays. You can still add options yourself.` | nothing |
| another request replaced this option first, or the room stopped collecting meanwhile (the claim below changes no row) | 303 redirect to `GET /rooms/<room_id>` (**ignored**) | – | nothing from this request |
| the database refuses the new option (e.g. another option of this room was replaced by the same new place a moment earlier) | 400 | `Something went wrong while adding the option. Please try again.` | nothing from this request |
| valid and a new place found | 303 redirect to `GET /rooms/<room_id>` | – | see below |

Error pages are the normal room page with the message shown above the options (`role="alert"`), as in A4/C2a.

The Google call uses: the room's stored `search_center_lat`/`search_center_lng` and `radius_m` (the widened one, if C4 widened), `min_rating` and `max_price_level` from `read_filters(room["filters"])`, the sub-categories from `replacement_subcategories(<main category from filters>, <option's category>, <categories of the room's active Google options>, rng)`, and `known_place_ids` = every place id of the room (active and replaced). The route passes a fresh `random.Random()`.

Saved on success, in **one transaction** (`app/db.py`, `replace_option(room_id, option_id, place_id, category) -> bool`):
1. The claim: `UPDATE options SET is_replaced = 1 WHERE id = ? AND room_id = ? AND is_replaced = 0 AND <the room's status is 'collecting'>`. If this changes **not exactly one row**, nothing is saved and the function returns `False` (the route then redirects: the first request won).
2. Insert the new option: `source = 'google'`, `place_id`, `label` NULL, `category` = the sub-category it was found in, `is_replaced = 0`.
3. If the insert is refused (`UNIQUE (room_id, place_id)`), everything is rolled back, so the old option is active again, and the route shows the "Something went wrong" message.

The new option has a higher id, so its card appears **at the end** of the list. **Never stored:** names or anything else from Google except the place id; who pressed the button.

### `app/db.py`
- `get_options(room_id)` returns only active options (`is_replaced = 0`). This changes the room page, the lobby's option count and the "at least 2 options" check before voting (A5) in every room mode; before C5 no option was ever replaced, so nothing else changes.
- New: `get_option(room_id, option_id)` (the option of this room or `None`, with `id`, `source`, `place_id`, `category`, `is_replaced`), `count_replaced_options(room_id)`, `get_room_place_ids(room_id)` (every place id, active and replaced), `replace_option(...)` as above.
- `has_google_options` and `room_has_google_place` stay unchanged (a replaced option still counts as "Google already searched here", and its photo may still be cached in a browser).

Checks (one line = one test):

`tests/test_been_there.py` – rules and Google calls, `requests.post` always replaced by a fake:
- [ ] `MAX_REPLACEMENTS_PER_ROOM` is 5.
- [ ] `read_filters` reads C4's filters JSON with all values; with `null` values it gives `None`; with missing keys, wrong types, an unknown main category, `None` or invalid JSON it gives `None` for those keys and never raises; an int `min_rating` becomes a float.
- [ ] `replacement_subcategories` returns the replaced sub-category first and one other sub-category of the main category second, never the replaced one twice.
- [ ] `replacement_subcategories` prefers a sub-category no active option has: when only one is unused, that one is always second.
- [ ] `replacement_subcategories` falls back to any other sub-category when every other one is used, and returns only the replaced sub-category when the main category is `None`.
- [ ] `replacement_subcategories` is random but repeatable: the same seed gives the same result, and over many seeds more than one second sub-category appears.
- [ ] `pick_replacement` never returns a known place id, returns `None` when every place is known or the list is empty, and over many seeds returns more than one different place (it is random, not always Google's first).
- [ ] `find_replacement` with a new place in the first sub-category: exactly 1 Google call with that sub-category as `includedTypes`, the given centre and radius; returns `(place id, sub-category)` with a place id that is not known.
- [ ] `find_replacement` when the first sub-category has only known places: a second call with the second sub-category, and the result comes from there.
- [ ] `find_replacement` returns `None` after at most 2 calls when nothing new is found.
- [ ] `find_replacement` applies `max_price_level` and `min_rating` (C2a filters) to every call.
- [ ] `find_replacement`: a timeout in the first call raises `PlacesError` and Google is not called again; an error status raises `PlacesError`.

`tests/test_been_there_route.py` – room page and route, Google always faked, rooms with C4's data set up in the database:
- [ ] Creator and guest of a collecting `surprise` room see one `Been there` form per Google option, posting to that option's URL, and none for a manual option.
- [ ] No `Been there` form in a `nearby` room with Google options, in a `manual` room, in a `voting` or `closed` surprise room, and nothing for a visitor.
- [ ] Accepted (guest presses it): redirect to the room page; the old option has `is_replaced = 1`, one new active Google option exists with a new place id, the same sub-category, empty label; the number of active options is unchanged.
- [ ] Accepted: Google is called once with the stored centre, the stored (widened) radius, the stored filters and the old option's sub-category; with the configured key.
- [ ] Accepted: after the swap, every participant's room page shows the same number of cards as before and no form for the replaced option; the new option has a `Been there` form.
- [ ] Accepted: the replaced place id is never chosen again, even when Google lists it first, and no place id of another option of the room is chosen.
- [ ] Accepted: when the same sub-category has nothing new, the new option comes from another sub-category of the main category that no active option has.
- [ ] Accepted: the lobby still shows the same number of options, and the creator can start the voting; a replaced option is not on the rating page.
- [ ] Accepted: nothing but the place id is stored from Google, and nothing about who pressed the button.
- [ ] Ignored: pressing it again for an already replaced option redirects, Google is not called, the data is unchanged.
- [ ] Ignored: a request whose claim finds the option already replaced (simulated by making `db.get_option` report it as active while it is already replaced) redirects, and nothing from this request is saved.
- [ ] Rejected: no new place found – status 200, message, the option stays active, nothing saved.
- [ ] Rejected: Google error – status 503, friendly message, nothing saved, the cards and the manual add form are still shown.
- [ ] Rejected: no API key – status 503, same message, Google not called, nothing saved.
- [ ] Rejected: the limit of 5 replaced options – message, Google not called, nothing saved.
- [ ] Rejected: a manual option – message, Google not called, nothing saved.
- [ ] Rejected: an option of another room, an unknown option id – message (400), nothing saved; a non-number id – 404.
- [ ] Rejected: a `nearby` room's Google option – message, Google not called, nothing saved.
- [ ] Rejected: a room that is `voting` or `closed` – message, Google not called, nothing saved.
- [ ] Rejected: a visitor, and a participant of another room – status 403, Google not called, nothing saved.
- [ ] Rejected: unknown room – 404, Google not called.
- [ ] Edge case: the database refuses the new option (simulated: the new place id is already an option of this room, by making `db.get_room_place_ids` hide it) – message, everything rolled back: the old option is active again and no option was added.
- [ ] Security: the API key never appears in any page (success, error).
- [ ] Persistence: after an app restart, the replaced option is still hidden and the new one is still shown.

## Out of scope
- Marking the place as known in a group's history (F13 "if there is a fixed group", F17): fixed groups are parked.
- "Been there" in `nearby` or `manual` rooms, during voting, or on the rating page; undoing a replacement; showing replaced options anywhere.
- Showing the sub-category on the card, or any change to C2b's card macro, `build_card` or `load_cards`.
- Showing who pressed the button, or a message to the group that a place was replaced.
- Any change to C2a's `/suggest`, C4's `/surprise` route, `search_nearby`, `pick_varied` or the search forms.
- Changes to `app/schema.sql` (`is_replaced` exists since A1), JavaScript, or existing tests.

## Done when
- All tests in `tests/test_been_there.py`, `tests/test_been_there_route.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test calls Google (fakes for `requests.post`, root `conftest.py` guard for everything else).
- SQL only in `app/db.py`, replacement rules in `app/services/surprise.py`, thin route in `app/routes/rooms.py`, Jinja template, no new JavaScript.
- With a real key on the deployed app: in a "Surprise me" room, "Been there" on a card replaces it with a new place of the same kind for everyone, and with a wrong key the friendly message appears and the place stays.
- Work is on branch `feature-c5-been-there`, pushed, pull request opened with Timonhio as reviewer (review circle: B reviews C).
