# C6 – F23 Find a place by name

Branch: `feature-c6-find-place-by-name`
Tests: `tests/test_place_by_name.py` (the Google call and the form rules, with fake responses) and `tests/test_place_by_name_route.py` (room page, the two routes, interactions with C2a/C4/C5)

F23 is not in `docs/concept.md`; `docs/decisions.md` D14 describes it (merged with PR #37). **Built only after these tests are reviewed.** PR #38 (A7) is merged, so the table `option_authors` that C6 writes into (decision 9) exists on `main`.

## Why
A typed option ("Luigi's") gets no card: no photo, rating, map or route. With F23 a participant types the name, picks the right place from a short list, and it becomes a normal Google option with a C2b card, while the cost per search stays small and nothing but the place id is ever stored.

## What
D14 (F23) in `docs/decisions.md`. `AGENTS.md`: "Adding options: only while the room status is `collecting`", "Google Maps integration" (field mask, store only `place_id`, timeout 5 s, friendly message on any error, tests never call Google), "Identity and access", "Rejected actions".

"Joined" means the same as in A3/A4: the token in the signed session belongs to a participant of this room in the database.

### Decisions in this spec (please check in the review)

1. **Two steps, plain forms, no JavaScript.** Step 1 (`POST /rooms/<room_id>/find`) runs one Text Search and **shows the matches in its own response (status 200), without a redirect.** Why: after a redirect the names and addresses would have to be stored somewhere to be shown again, and D14 allows keeping only the ids (in the session). Step 1 writes nothing to the database, so a reload cannot add anything twice, which is what Post/Redirect/Get protects (`AGENTS.md`). A reload only asks the browser to send the search again (one more Google call, counted by the limit in 2). Step 2 (`POST /rooms/<room_id>/find/add`) saves and then redirects (Post/Redirect/Get). **Please confirm this reading of "every POST handler redirects" in the review.**
2. **Limit: at most 10 name searches per participant and room** (`MAX_NAME_SEARCHES = 10`), counted in the signed session next to the remembered matches. No schema change is needed. It is a **soft guard** against accidental repeats (reloads of the result page, double taps, a long session), not a hard barrier: someone who throws away the cookie also loses their place in the room and has to join again, and an old copy of a signed cookie would still be accepted. The real cost guards stay the field mask (Pro, D14), the 5 results and the budget alert (D6). A search counts when Google is called (also when Google fails or finds nothing). *Alternative considered:* no limit at all (one search costs a fraction of a cent, a demo group makes a few dozen); a counter in the database would need a schema change (Track A). **Please decide in the review: soft limit 10, another number, or none.**
3. **Request parameters, checked in Google's documentation of Text Search (New) on 2026-11-16** (https://developers.google.com/maps/documentation/places/web-service/text-search):
   - `POST https://places.googleapis.com/v1/places:searchText`, headers `Content-Type: application/json`, `X-Goog-Api-Key`, `X-Goog-FieldMask`.
   - `pageSize: 5` ("accepts 1 to 20"; it "replaces the deprecated `maxResultCount` field", so `maxResultCount` is **not** sent).
   - `locationBias.circle.center.latitude/longitude` and `locationBias.circle.radius` in metres ("between 0.0 and 50000.0 inclusive"). A **bias**, not a restriction: a place further away can still be found, which is right for a name the participant already knows. `locationBias` and `locationRestriction` cannot be combined; we send only the bias.
   - Radius: always `NAME_SEARCH_BIAS_RADIUS_M = 5000`, also when the room's own search radius is smaller, because the participant names a place they mean and a 500 m bias would push it down needlessly. **Please check in the review.**
   - Billing (usage-and-billing page): "You are then billed at the highest SKU applicable to your request." `places.displayName` and `places.formattedAddress` are Pro fields, so every search is **Text Search Pro**, as D14 says.
4. **Remembered matches in the session.** After step 1 the session holds, for this room only, the ids of the matches just shown (at most 5) and the search count. A new search replaces the ids; a successful save removes them (the count stays). Step 2 accepts only an id from this list. **Missing or outdated matches** – no list for this room (another browser, cookie lost, already saved), an id from an older search, a made-up id, or session content that is not a list of texts – are all rejected the same way: `This search result has expired. Please search again.` (400), nothing saved, Google is not called. There is **no time limit**: a place id stays valid, and the room status and the duplicate check are checked again at the save anyway.
5. **Location.** If the room has a search centre (`search_center_lat`/`search_center_lng`, from C2a or C4), it is the bias, and location fields sent by the browser are ignored. Otherwise the browser's `latitude`/`longitude` fields are used if both are valid (`places.parse_location`, rounded to 3 decimals); missing or invalid fields mean **search without a location** (no error: the location is only a hint). The participant's location is used for this one call only and **never stored**; the room's centre is never written by C6.
   "Use my location" (button, hidden fields, `geolocation.js` unchanged) is shown in the find form only when the room has no centre **and** the C2a/C4 search form is not on the same page: `geolocation.js` finds its fields by id, and two forms with the same ids would break it. So the creator of a `nearby`/`surprise` room searches by name without location until the room's search has run (then the centre is the bias).
6. **Already an option.** A place that is already an option of the room, **active or replaced** (C5: the group has been there), is rejected at step 2 with `This place is already an option.` (400). The match list in step 1 shows all matches; marking duplicates there is not needed.
7. **What is saved:** `source = 'google'`, `place_id`, `label` NULL, `category` **NULL**, `is_replaced = 0`. The NULL category is how C2a/C4/C5 tell a picked place from a place their search found (see "Interactions" below). No column is added to `options`.
8. **When nothing can be found** (no key, Google error, no matches, limit reached): a friendly message, and the manual add form (A4) is shown **pre-filled with the typed name**, so one tap adds it as a manual option. The manual add form is also pre-filled when matches are shown ("Not in the list?"). The A4 route itself is unchanged.
9. **The participant who picks a place is its author** (agreement in the A7 spec, PR #38). In the same transaction as the option, C6 writes one row into A7's table `option_authors` (`option_id`, `room_id`, the participant's id). So, as with a manual option, the person who picked it and the creator can delete it (F24). The author is never shown to anyone. C6 does not change the table or A7's code; if the option is not saved, no author row is saved either.

### Interactions with C2a, C4 and C5 (please check in the review)

These are not new features, but without them F23 would break existing flows. They change two functions in `app/db.py`, what the room page shows and **one check in the C5 route**; the C2a and C4 routes are not changed.
- **The nearby/surprise search must still be possible after a name search.** C2a/C4 use `db.has_google_options` to decide "this room has already been searched". A picked place is a Google option, so a guest picking "Luigi's" would block the creator's search. → Since A7 (review of #38), `has_google_options` is true if the room's search was claimed (`rooms.radius_m IS NOT NULL`) **or** the room has a Google option. The `radius_m` part stays unchanged; the option part counts only options **with a category** (`source = 'google' AND category IS NOT NULL`). C2a, C4 and C5 always store a category, C6 never does. So a picked place does not block the search, and a room whose search has run stays searched, even after A7 deleted all its Google options.
- **A place picked by name must not make the room's search fail.** `db.save_search` inserts every found place; if one of them is already a picked place, `UNIQUE (room_id, place_id)` refuses it and the whole search is rejected as "already suggested". → `save_search` **skips place ids that are already options of the room** (the picked option stays as it is, the other places are added). This also holds when a place is picked at the same moment as the search is saved (`ON CONFLICT … DO NOTHING`, see `app/db.py` below).
- **"Been there" (C5) is not offered for picked places.** In a `surprise` room a picked place is someone's deliberate choice, not a surprise, and it has no sub-category to search a replacement in. → The room page shows no `Been there` form for a Google option without a category.
- **The C5 route rejects picked places too** (hiding the button is not a permission check). In `POST /rooms/<room_id>/options/<option_id>/been-there`, directly after C5's check "option is a manual option", one new row in C5's table:

  | Case | Status | Message | Saved |
  |---|---|---|---|
  | option is a Google option without a category (picked by name, C6) | 400 | `Only places from the surprise search can be replaced.` | nothing; Google is not called |

  Without this check, such a request would send an empty place type to Google, which costs a call and only ends in C5's 503 message. The message is a constant in `app/services/surprise.py` (`PICKED_PLACE_MESSAGE`). C5's other checks, their order and `can_press_been_there` stay as they are; the room page decides about the button with the option's category (above).

### The Google call (`app/services/places.py`)

Constants: `TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"`, `NAME_SEARCH_FIELD_MASK = "places.id,places.displayName,places.formattedAddress"` (never `*`), `NAME_SEARCH_PAGE_SIZE = 5`, `NAME_SEARCH_BIAS_RADIUS_M = 5000`, `MAX_NAME_SEARCHES = 10`, `NAME_MAX_LENGTH = 80`.

`search_by_name(api_key: str, name: str, latitude: float | None, longitude: float | None) -> list[dict]` returns the matches in Google's order, each `{"place_id": …, "name": …, "address": …}`, or raises `PlacesError`.
- One `requests.post` to `TEXT_SEARCH_URL` with `timeout=5`, headers as above.
- JSON body: `textQuery` (the name), `pageSize: 5`, and – only if both coordinates are given – `locationBias: {"circle": {"center": {"latitude", "longitude"}, "radius": 5000}}`. No `maxResultCount`, no `locationRestriction`, no other parameter.
- A response without `places` (`{}`) returns `[]`.
- Results that are not a dict, have no `id`, an id that does not match `PLACE_ID_PATTERN`, or an id already in the list are skipped. At most **5** matches are returned, even if Google sends more.
- `name` is `displayName.text`; if missing or empty, `Place from Google Maps`. `address` is `formattedAddress`; if missing or not text, `""`.
- `PlacesError` for: any `requests.RequestException` (as `PlacesUnavailable`), a status other than 200, a body that is not valid JSON or not a JSON object. The message never contains the key.

`validate_name(value: str | None) -> tuple[str, list[str]]` returns the name without leading/trailing whitespace and the error messages:
- empty or only whitespace → `Please enter a name to search for.`
- longer than 80 characters → `A name can be at most 80 characters.`

### Room page

For a **joined** participant of a room with status `collecting`, in every mode, below the options and above the manual add form:
- A form posting to `/rooms/<room_id>/find`: heading `Find a place on Google Maps`, text field `name` (`maxlength="80"`, `required`), submit button `Find on Google Maps`.
- "Use my location" with hidden `latitude`/`longitude` and the `geolocation.js` script only as in decision 5. If the room has a centre, the form says `Places near the room's search area are shown first.`
- Not shown for visitors, in `voting` or `closed` rooms.
- No `Been there` form for a Google option without a category (see "Interactions").

### Step 1: `POST /rooms/<room_id>/find`

Checked in this order:

| Case | Status | Message | Effect |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined (visitor, participant of another room) | 403 | `Please join the room before adding options.` | nothing; Google not called |
| room status is not `collecting` | 400 | `Options can only be added before voting starts.` | nothing; Google not called |
| invalid name (rules above) | 400 | the message; the entered name shown again | nothing; Google not called |
| this participant already searched 10 times in this room | 400 | `You have already searched 10 times in this room. You can still add options yourself.` | nothing; Google not called |
| `GOOGLE_MAPS_API_KEY` not set | 503 | `Place suggestions are not available right now. You can still add options yourself.` | nothing; Google not called; not counted |
| `search_by_name` raises `PlacesError` | 503 | same message | counted; remembered matches of this room cleared |
| no matches | 200 | `No places found with this name. You can still add it as your own option.` | counted; remembered matches of this room cleared |
| matches found | 200 | – | the matches are shown; their ids are remembered for this room (replacing earlier ones); counted |

In every case from "invalid name" on, the manual add form is pre-filled with the cleaned name (decision 8), and the find form is shown again with it. Messages appear above the find form (`role="alert"`), as in A4/C2a.

The result page lists the matches under `Which one do you mean?`, each with its name, its address and its own small form posting to `/rooms/<room_id>/find/add` with a hidden `place_id` and the button `Add this place`. Below: `Not in the list? Add it as your own option below.` and the pre-filled manual add form.

### Step 2: `POST /rooms/<room_id>/find/add`

Never calls Google. Checked in this order:

| Case | Status | Message | Saved |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined | 403 | `Please join the room before adding options.` | nothing |
| room status is not `collecting` | 400 | `Options can only be added before voting starts.` | nothing |
| no remembered matches for this room, or `place_id` is not one of them (decision 4) | 400 | `This search result has expired. Please search again.` | nothing |
| the place is already an option of the room (active or replaced) | 400 | `This place is already an option.` | nothing |
| the room stopped collecting meanwhile (the insert below adds no row) | 400 | `Options can only be added before voting starts.` | nothing |
| the database refuses the insert (the same place added by another request a moment earlier) | 400 | `This place is already an option.` | nothing from this request |
| valid | 303 redirect to `GET /rooms/<room_id>` | – | one option (decision 7); the remembered matches of this room are removed |

The new option appears at the end of the list as a normal C2b card (name, photo, rating, price; distance only if the room has a centre).

### `app/db.py`
- New `add_place_option(room_id: str, place_id: str, participant_id: int) -> bool`: in one `db.transaction()`, (1) locks the room row the same way as `save_vote`: `UPDATE rooms SET status = status WHERE id = ? AND status = 'collecting'`, and stops if this changes not exactly one row (review of #39: `INSERT … SELECT … WHERE EXISTS` alone locks nothing on Postgres, so a "Start voting" at the same moment could still let the insert through); (2) `INSERT INTO options (room_id, source, place_id) VALUES (?, 'google', ?) RETURNING id`; (3) `INSERT INTO option_authors (option_id, room_id, participant_id) VALUES (?, ?, ?)` (decision 9), the same way A7's `add_manual_option` does it. Returns `False` if no option was added (room not collecting); then no author row is written. Raises one of `INTEGRITY_ERRORS` if the place is already an option (as C5's `replace_option`); the transaction is rolled back, so neither row is saved.
- `has_google_options` and `save_search` as described in "Interactions". `save_search` skips an existing place with `INSERT … ON CONFLICT (room_id, place_id) DO NOTHING`, which works the same on SQLite and Postgres (as in `save_vote`), also when a place is picked by name at the same moment.
- Existing `get_room_place_ids` is reused for the duplicate check.

### Session (`app/routes/rooms.py`)
`session["name_searches"] = {room_id: {"place_ids": [...], "count": n}}`, a new dict assigned on every change (like `remember_token`). Only ids and the count; **never names or addresses**.

Kept small, because the session cookie lasts 180 days and can hold many rooms (D15; review of #39): only the room of the latest search or save keeps its `place_ids` (all other rooms get `[]`), and only the **5 most recently used rooms** keep an entry at all (`MAX_REMEMBERED_NAME_SEARCH_ROOMS`). A room that drops out starts again at 0 searches; this is acceptable for a soft guard (decision 2). With at most 5 ids of about 27 characters, the entry stays far below the 4 KB cookie limit. Content of an unexpected form (not a dict, ids that are not a list of texts, a count that is not a whole number) counts as "no matches, 0 searches".

Checks (one line = one test):

`tests/test_place_by_name.py` – the Google call and the form rules, `requests.post` always faked:
- [ ] Sends one POST to the Text Search URL with `timeout=5`.
- [ ] Sends the API key, `Content-Type` and the field mask; the field mask is exactly `places.id,places.displayName,places.formattedAddress` and never contains `*`.
- [ ] Sends `textQuery` and `pageSize: 5`, and no `maxResultCount` or `locationRestriction`.
- [ ] With a location, sends `locationBias.circle` with the centre and radius 5000.
- [ ] Without a location (or with only one coordinate), sends no `locationBias`.
- [ ] Returns place id, name and address of every match, in Google's order.
- [ ] Returns at most 5 matches when Google sends more.
- [ ] A response without `places` returns `[]`.
- [ ] Skips results without an id, with an invalid id, duplicates and non-dict entries.
- [ ] A missing name becomes `Place from Google Maps`, a missing address `""`.
- [ ] A timeout, a connection error, a non-200 status, invalid JSON and a non-object body each raise `PlacesError`; the message never contains the key.
- [ ] `validate_name` accepts and strips a name, rejects empty/whitespace and names over 80 characters with their messages; exactly 80 characters is accepted.

`tests/test_place_by_name_route.py` – room page and routes, Google always faked:
- [ ] A joined participant (creator and guest) of a collecting room sees the find form in every mode.
- [ ] Visitors, and participants of a `voting` or `closed` room, do not see the find form.
- [ ] In a `manual` room the find form has "Use my location" and the geolocation script; in a room with a centre it has neither and says the search area is used; for the creator of a `nearby` room before the search, the ids `use-location` and `latitude` appear only once on the page.
- [ ] Step 1 accepted: status 200, names and addresses of the matches shown, one `Add this place` form per match posting its place id; manual form pre-filled with the name; nothing saved.
- [ ] Step 1: Google is called with the configured key and the cleaned name.
- [ ] Step 1: the room's centre is the bias, even if the browser sends other coordinates.
- [ ] Step 1: without a room centre, the browser's coordinates are used, rounded to 3 decimals; they are not stored in the room.
- [ ] Step 1: without a room centre and without (or with invalid) coordinates, Google is called without a bias.
- [ ] Step 1: the session holds only the ids of the shown matches for this room, no names or addresses.
- [ ] Step 2 accepted: redirect; one option with `source = 'google'`, the place id, label NULL, category NULL, `is_replaced = 0`; Google not called; the remembered matches are removed.
- [ ] Step 2 accepted: the option appears on every participant's room page and in the lobby's option count.
- [ ] Step 2 accepted: one `option_authors` row links the new option to the participant who picked it, in this room; the author's nickname is not shown next to the option.
- [ ] Step 2 accepted (with A7): the participant who picked the place can delete it, another guest cannot (403).
- [ ] Accepted: nothing from Google but the place id is in the database (no name, no address).
- [ ] Accepted: works in `manual`, `nearby` and `surprise` rooms, for creator and guest.
- [ ] Rejected step 1: no matches – 200, message, manual form pre-filled, nothing saved.
- [ ] Rejected step 1: Google error – 503, message, manual form pre-filled, nothing saved.
- [ ] Rejected step 1: no key – 503, message, Google not called.
- [ ] Rejected step 1: empty and too long name – 400, message, Google not called.
- [ ] Rejected step 1: the 11th search of a participant in a room – 400, message, Google not called; another participant can still search.
- [ ] Rejected step 1: visitor, participant of another room – 403, Google not called.
- [ ] Rejected step 1: `voting` or `closed` room – 400, Google not called.
- [ ] Rejected step 1: unknown room – 404, Google not called.
- [ ] Rejected step 2: without a search before – expired message, nothing saved.
- [ ] Rejected step 2: an id that was not among the shown matches – expired message, nothing saved.
- [ ] Rejected step 2: an id from an older search after a new search – expired message, nothing saved.
- [ ] Rejected step 2: pressing `Add this place` again after a successful save – expired message, still one option.
- [ ] Rejected step 2: matches remembered for another room are not accepted in this room.
- [ ] Rejected step 2: a place that is already an active option – message, nothing saved.
- [ ] Rejected step 2: a place that was replaced with "Been there" – message, nothing saved.
- [ ] Rejected step 2: `voting` or `closed` room – message, nothing saved.
- [ ] Rejected step 2: visitor, participant of another room – 403, nothing saved.
- [ ] Rejected step 2: unknown room – 404.
- [ ] Edge case: the room starts voting between the checks and the insert (simulated by making `db.get_room` report `collecting`) – message, nothing saved.
- [ ] Edge case: the database refuses the insert (simulated by making `db.get_room_place_ids` hide the existing option) – message, no crash, still one option and no author row from this request.
- [ ] Rejected step 2 (any case above): no `option_authors` row is written.
- [ ] Interaction: after a guest picked a place, the creator of a `nearby` room still sees the search form and the search saves its places; a found place that was already picked is kept once.
- [ ] Interaction: a picked place in a `surprise` room has no `Been there` form; the surprise places still do.
- [ ] Interaction: pressing `Been there` for a picked place anyway (hand-made request) – 400, `Only places from the surprise search can be replaced.`, Google not called, data unchanged; a surprise place of the same room can still be replaced.
- [ ] Security: the API key never appears in any page (find form, matches, error).
- [ ] Persistence: after an app restart, the picked option is still stored and shown.

## Out of scope
- **Deleting options (F24/A7)**, the delete route and the table `option_authors` itself: all from A7 (PR #38). C6 only writes the author row (decision 9). No schema change here.
- Autocomplete, suggestions while typing, any new JavaScript, any change to `geolocation.js`.
- Changes to the C2a/C4 routes, to the C5 route beyond the one check in "Interactions", `search_nearby`, the C2b card macro or `load_cards`.
- Showing which matches are already options in the step-1 list.
- Storing the participant's location, a text address search for the room centre (F19 parked).
- New dependencies, changes to `app/schema.sql` or existing tests.

## Done when
- All tests in `tests/test_place_by_name.py`, `tests/test_place_by_name_route.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test calls Google (fakes for `requests.post`, root `conftest.py` guard for everything else).
- SQL only in `app/db.py`, the Google call and rules in `app/services/places.py`, thin routes in `app/routes/rooms.py`, Jinja template, no new JavaScript.
- With a real key on the deployed app: in a `manual` room, searching for a known restaurant by name finds it, and the picked place becomes a card with photo; with a wrong key the friendly message appears and the name can be added manually.
- Work is on branch `feature-c6-find-place-by-name`, pushed, pull request opened with Timonhio as reviewer (review circle: B reviews C).
