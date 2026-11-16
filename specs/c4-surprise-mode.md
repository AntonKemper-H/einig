# C4 – F12 Surprise mode: guided randomness

Branch: `feature-c4-surprise-mode`
Tests: `tests/test_surprise.py` (the selection rules and the search rounds, with fake responses) and `tests/test_surprise_search.py` (room page and route)

Builds on C2a (`specs/c2-places-search.md`: one search per room, claim on the room row, only the place id is stored) and C2b (`specs/c2b-place-cards.md`: cards with details loaded fresh). A "Surprise me" room already exists since A2; until now its mode was only stored.

## Why
A "Surprise me" room should bring the group to places they would not have picked themselves: instead of the most popular places of one category, the app mixes several sub-categories (e.g. Italian, Thai, Greek) and picks a varied, partly random selection. Google costs money and can fail, so the searches stay few and small, any failure leaves the room unchanged with a friendly message, and the group can always continue with manual options.

## What
F12 in `docs/concept.md`, "Google Maps integration" in `AGENTS.md` ("Surprise mode may run a few small searches with different place types and mix the results").

"Joined" means the same as in A3/A4: the token in the signed session belongs to a participant of this room in the database.

### Main categories and sub-categories (`app/services/surprise.py`)

`SUBCATEGORIES` maps each main category the group can choose to the Google place types that are mixed (all from Google's "Table A" of place types):

| Main category (form value, shown as) | Sub-categories |
|---|---|
| `restaurant` ("Any restaurant") | `italian_restaurant`, `japanese_restaurant`, `mexican_restaurant`, `indian_restaurant`, `thai_restaurant`, `greek_restaurant`, `vietnamese_restaurant`, `turkish_restaurant`, `chinese_restaurant`, `korean_restaurant`, `spanish_restaurant`, `lebanese_restaurant`, `vegan_restaurant` |
| `bar` ("Any bar") | `bar`, `pub`, `wine_bar`, `bar_and_grill` |
| `cafe` ("Any café") | `cafe`, `coffee_shop`, `tea_house`, `dessert_shop` |

`movie_theater` (C2a) is not offered: it has no sub-categories to mix.

Constants (module level, so they are easy to explain and to change):
- `SUBCATEGORIES_PER_SEARCH = 4` – how many sub-categories are searched per room
- `SURPRISE_OPTION_COUNT = 5` – how many places are saved as options
- `WIDENING_FACTOR = 1.5`, `MAX_WIDENINGS = 3` – F12: "+50 %, at most three times"

### Guided randomness (pure functions in `app/services/surprise.py`, no Flask, no database)

Every function that uses chance takes an `rng` (a `random.Random`), so tests can make it deterministic. The route passes a fresh `random.Random()`.

- `choose_subcategories(category: str, rng) -> list[str]`: `SUBCATEGORIES_PER_SEARCH` different sub-categories of the main category, picked at random (`rng.sample`); all of them (in random order) if the category has no more.
- `widened_radius(radius_m: int) -> int`: `round(radius_m * WIDENING_FACTOR)`, e.g. 1000 → 1500 → 2250 → 3375.
- `pick_varied(results: list[tuple[str, list[str]]], count: int, rng) -> list[tuple[str, str]]` takes one `(sub-category, place ids)` pair per search and returns up to `count` pairs `(place id, sub-category)`:
  - each sub-category's place ids are shuffled with `rng` first (a copy; the input is not changed). Why: Google sorts by popularity, so without shuffling the group would always get the best-known place of each kind, which is the opposite of a surprise;
  - then it takes **one place per sub-category in turn** (round robin, in the order of `results`): the first round takes one place from every sub-category, the second round a second one, and so on, until `count` places are picked or every list is used up. So no two options share a sub-category as long as enough sub-categories found something (F12: "ideally no two options from the same subcategory");
  - a place id that was already picked (Google can list one place under two types) is skipped, and the next place of that sub-category is taken instead;
  - sub-categories with an empty list are skipped.
- `count_distinct(results) -> int`: the number of different place ids over all lists.

### The search rounds (`app/services/surprise.py`)

`surprise_search(api_key, latitude, longitude, radius_m, category, max_price_level, min_rating, rng) -> dict` returns `{"choices": [(place id, sub-category), …], "radius_m": <the radius of the last round>}`, or raises `places.PlacesError`.

1. `choose_subcategories(category, rng)` once; every round searches the same sub-categories.
2. One round = one `places.search_nearby(...)` call per sub-category, in that order, with the sub-category as `category` and the same centre, radius, `max_price_level` and `min_rating` (C2a's call and filters, unchanged: `maxResultCount` 15, field mask, timeout 5 s).
3. If the round found at least `SURPRISE_OPTION_COUNT` different places, stop. Otherwise, if fewer than `MAX_WIDENINGS` widenings were made, set `radius_m = widened_radius(radius_m)` and run another round. After `MAX_WIDENINGS` widenings, stop with what the last round found.
4. `choices = pick_varied(<results of the last round>, SURPRISE_OPTION_COUNT, rng)`. Only the last round counts: it searched the largest circle and found the most places, and the stored radius then matches the options. (It does not always contain every earlier place: with `maxResultCount` 15, a larger circle can push some of them out of the top 15. That does not matter for the result; reworded after review of #27.)
5. **Any `PlacesError` from any call stops everything at once** and is raised (no further calls, no partial result). Why: at most 4 × 4 = 16 calls; after a timeout, waiting for 15 more would take longer than the server allows (gunicorn, 30 s), and a half-finished search would be confusing.

At most `SUBCATEGORIES_PER_SEARCH × (MAX_WIDENINGS + 1) = 16` Google calls per room, usually 4.

### Form rules (`app/services/surprise.py`)

`validate_surprise(form) -> tuple[dict, list[str]]`: the same fields, cleaned values and messages as C2a's `validate_search` (`radius_m`, `latitude`, `longitude`, `min_rating`, `max_price_level`), except that `category` must be one of `SUBCATEGORIES` (`restaurant`, `bar`, `cafe`); anything else (also `movie_theater`) gives `Please choose a category.` (exactly once). All problems at once, as in C2a.

### Room page and route

- `GET /rooms/<room_id>`, for the **creator** of a room with mode `surprise`, status `collecting` and **no Google option yet**, shows a "Surprise me" form posting to `/rooms/<room_id>/surprise`: heading `Surprise us`, `category` with the three main categories, `radius_m`, `min_rating`, `max_price_level` (choices as in C2a), the hidden `latitude`/`longitude` fields, the "Use my location" button and `app/static/js/geolocation.js` (unchanged, same element ids as C2a). Nobody else sees it, and it disappears after a successful search. C2a's form (`/suggest`) is still never shown in a `surprise` room.
- `POST /rooms/<room_id>/surprise`, checked in this order (same messages as C2a wherever the case is the same):

| Case | Status | Message | Saved |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined | 403 | `Please join the room before adding options.` | nothing |
| joined, but not the creator | 403 | `Only the creator can search for places.` | nothing |
| room mode is not `surprise` | 400 | `Surprise places can only be suggested in a "Surprise me" room.` | nothing |
| room status is not `collecting` | 400 | `Options can only be added before voting starts.` | nothing |
| the room already has Google options | 400 | `Places have already been suggested for this room.` | nothing |
| invalid form | 400 | every message; the form is shown again with the entered values (location rounded, as in C2a) | nothing |
| `GOOGLE_MAPS_API_KEY` is not set | 503 | `Place suggestions are not available right now. You can still add options yourself.` | nothing; Google is not called |
| `surprise_search` raises `PlacesError` | 503 | same message as above | nothing |
| no place found, even after widening | 200 | `No places found. Try a larger radius or fewer filters.`; the form is shown again | nothing |
| another search claimed the room first, or the database refuses an insert | 400 | `Places have already been suggested for this room.` | nothing from this request |
| valid and places found | 303 redirect to `GET /rooms/<room_id>` | – | see below |

- Saved on success, in **one transaction**, with C2a's claim on the room row (`… WHERE id = ? AND radius_m IS NULL AND status = 'collecting'`, exactly one row or everything is rolled back):
  - the rounded centre, `radius_m` = **the radius of the last round** (the widened one, if it was widened), and `filters` as JSON text `{"category": <main category>, "min_rating": …, "max_price_level": …, "requested_radius_m": <the radius the creator chose>}`;
  - one option per choice, in the order of `choices`: `source = 'google'`, `place_id`, `label` NULL, `category` = **the sub-category** (e.g. `thai_restaurant`), `is_replaced = 0`.
  - `app/db.py`: C2a's `save_google_search` keeps its signature and behaviour; the shared claim-and-insert code moves into one function that takes `(place id, category)` pairs, used by both C2a and C4 (no copied SQL).
- **Never stored:** names, ratings or anything else from Google except the place id.
- The options are shown as C2b's cards (unchanged).
- **Telling the group about the widening (F12):** in a `surprise` room whose stored `radius_m` is larger than `filters.requested_radius_m`, every participant's room page shows `Only a few places were found nearby, so the search area was widened to <radius>.` with the radius formatted like C2b's distances (`places.format_distance`, e.g. `3.4 km`, `750 m`). Without widening, no such text. Visitors see nothing of it (they see no options either).

Checks (one line = one test):

`tests/test_surprise.py` – rules and search rounds, `requests.post` always replaced by a fake:
- [ ] `SUBCATEGORIES` has exactly the three main categories and the sub-categories in the table; the constants have the values above.
- [ ] `choose_subcategories` returns 4 different sub-categories of the main category; for `bar` and `cafe` it returns all 4; the same seed gives the same choice, and over many seeds more than one choice appears (it is random).
- [ ] `widened_radius`: 1000 → 1500, 1500 → 2250, 2250 → 3375, 500 → 750.
- [ ] `pick_varied` takes one place per sub-category before it takes a second from any of them; with 4 sub-categories of 15 places and `count` 5, exactly one sub-category appears twice.
- [ ] `pick_varied` returns `(place id, sub-category)` pairs, never more than `count`, and fewer if there are not enough places.
- [ ] `pick_varied` skips a place id that was already picked under another sub-category and takes that sub-category's next place instead; a sub-category with an empty list is skipped.
- [ ] `pick_varied` is random but repeatable: the same seed gives the same result, different seeds can give different places from the same lists; the input lists are not changed.
- [ ] `count_distinct` counts each place id once over all lists.
- [ ] `surprise_search` with plenty of places: 4 calls, each with one chosen sub-category as `includedTypes`, the same centre and radius, the filters applied; returns 5 choices from 4 different sub-categories and the unchanged radius.
- [ ] `surprise_search` widens: too few places at 1000 m, enough at 1500 m → 8 calls (4 at 1000, 4 at 1500, same sub-categories), returns radius 1500 and choices from the second round.
- [ ] `surprise_search` widens at most three times: Google finds nothing → 16 calls with radii 1000, 1500, 2250, 3375; returns no choices and radius 3375.
- [ ] `surprise_search` with only 2 places even after widening returns those 2 (no error).
- [ ] `surprise_search` applies `max_price_level` and `min_rating` to every call (C2a filters).
- [ ] `surprise_search`: a timeout in the second call raises `PlacesError`, and Google is not called again; an error status in any call raises `PlacesError`.
- [ ] `validate_surprise` accepts `restaurant`, `bar`, `cafe` with valid fields and returns cleaned, typed values with rounded coordinates.
- [ ] `validate_surprise` rejects `movie_theater`, an unknown and a missing category with `Please choose a category.` (once), and with several problems returns every message (C2a's messages for the other fields).

`tests/test_surprise_search.py` – room page and route, Google always faked:
- [ ] Creator of a `surprise` room sees the "Surprise us" form posting to `/surprise` with all fields, the three main categories (not `movie_theater`), the hidden location fields and the geolocation script, and not C2a's `/suggest` form.
- [ ] A joined non-creator, a visitor, and the creator of a `manual` or `nearby` room do not see the surprise form.
- [ ] Accepted: a valid search redirects to the room page.
- [ ] Accepted: 5 Google options are saved with their sub-category as `category`, empty label, `is_replaced = 0`, from at least 4 different sub-categories of the chosen main category.
- [ ] Accepted: the room stores the rounded centre, the radius and the filters JSON with the main category, the filters and `requested_radius_m`.
- [ ] Accepted: coordinates are rounded on the server even if the browser sends more decimals; Google is called with the configured key and the rounded centre.
- [ ] Accepted: after the search every participant sees one card per option, the surprise form is gone, and no widening text is shown.
- [ ] Accepted with widening: the room stores the widened radius and `requested_radius_m` = the chosen one; creator and guest see `Only a few places were found nearby, so the search area was widened to 1.5 km.`
- [ ] Accepted: manual options can still be added after the search, and earlier manual options are kept.
- [ ] Accepted: nothing but the place id is stored from Google (no name in the database).
- [ ] Rejected: no places found even after widening – message, form shown again, nothing saved.
- [ ] Rejected: Google error – friendly message, status 503, nothing saved, manual add form still shown.
- [ ] Rejected: no API key – same message, status 503, Google not called, nothing saved.
- [ ] Rejected: invalid form (e.g. `movie_theater` and no location) – status 400, every message, entered values shown again, Google not called, nothing saved.
- [ ] Rejected: a second search in the same room – message, Google not called, data unchanged.
- [ ] Rejected: a joined non-creator – status 403, Google not called, nothing saved.
- [ ] Rejected: a visitor, and a participant of another room – status 403, Google not called, nothing saved.
- [ ] Rejected: a `manual` or `nearby` room – message, Google not called, nothing saved.
- [ ] Rejected: a room that is `voting` or `closed` – message, Google not called, nothing saved.
- [ ] Rejected: unknown room – 404, Google not called.
- [ ] Edge case: a second search that passes the "already suggested" check (simulated by making `db.has_google_options` return False) and gets different place ids is rejected by the claim – message, no new options, the room keeps the first search's settings.
- [ ] Security: the API key never appears in any page (form, success, error).
- [ ] Persistence: after an app restart, the options (with sub-categories), the room's search settings and the widening text are still there.

## Out of scope
- Excluding places the group already knows (F12 mentions F13 and F17): a room is searched only once, so it has no known places yet. History (F17) is parked; "Been there" and its replacement place are C5 (F13).
- Showing the sub-category (e.g. "Thai") on the card, or any change to C2b's card macro.
- A "search again / reshuffle" button, deleting options to search again.
- Searching around the group's midpoint (F19), Blind Date (F14), Fate mode (F15).
- Any change to C2a's `/suggest` route, `search_nearby`, `validate_search` or the `nearby` form.
- Changes to `app/schema.sql` (all columns exist), `geolocation.js` or existing tests.
- Deleting the search centre when the room closes (belongs to the task that closes rooms).

## Done when
- All tests in `tests/test_surprise.py`, `tests/test_surprise_search.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test calls Google (fakes for `requests.post`, root `conftest.py` guard for everything else).
- SQL only in `app/db.py`, selection rules and search rounds in `app/services/surprise.py`, thin route in `app/routes/rooms.py`, Jinja template, no new JavaScript.
- With a real key on the deployed app: a "Surprise me" room fills with 5 places of different kinds; with a small radius and strict filters the widening text appears; with a wrong key the friendly message appears and manual options still work.
- Work is on branch `feature-c4-surprise-mode`, pushed, pull request opened with Timonhio as reviewer (review circle: B reviews C).
