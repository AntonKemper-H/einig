# C2a – F8 Suggest places nearby: search and save

Branch: `feature-c2-places-search` (started from `feature-a4-add-options`, because it extends A4's option list; rebased on `main` once A4 is merged)
Tests: `tests/test_places.py` (the Google call, with fake responses) and `tests/test_places_search.py` (the room page and the search route)

C2 (F8) is split in two tasks:
- **C2a (this spec):** search form, location, one Places API call, saving the found places as options.
- **C2b (next spec):** option cards with name, photo, rating, price level and distance, plus the `/photo/<photo_name>` proxy.

## Why
In a "Places nearby" room the group should not have to type in restaurants they already know: the creator picks a category and a radius, and the app fills the option list with real places from Google Maps. The API key costs money and must never reach the browser, so the search runs once per room on the server, and a broken or missing Google connection must never stop the group from adding options by hand.

## What
F8 in `docs/concept.md` and "Google Maps integration" in `AGENTS.md`.

"Joined" means the same as in A3/A4: the token in the signed session belongs to a participant of this room in the database.

### The Google call (`app/services/places.py`)

`search_nearby(api_key, latitude, longitude, radius_m, category, max_price_level, min_rating) -> list[str]` returns the place ids of the results, in Google's order, or raises `PlacesError`.

- One `requests.post` to `https://places.googleapis.com/v1/places:searchNearby` with `timeout=5`.
- Headers: `Content-Type: application/json`, `X-Goog-Api-Key: <api_key>`, `X-Goog-FieldMask: places.id,places.rating,places.priceLevel` (constant `SEARCH_FIELD_MASK`; never `*`). Rating and price level are requested because the filters below need them and C2b shows them.
- JSON body: `includedTypes: [category]`, `maxResultCount: 15`, `locationRestriction.circle.center.latitude/longitude` and `locationRestriction.circle.radius` (the radius as a number in metres).
- Filters run in Python on the results, because Nearby Search has no price or rating parameter:
  - `max_price_level` (`None` or 1–4): Google's `priceLevel` text is turned into a number (`PRICE_LEVEL_FREE` 0, `INEXPENSIVE` 1, `MODERATE` 2, `EXPENSIVE` 3, `VERY_EXPENSIVE` 4). Places above the maximum are dropped. **Places without a price level are kept** (many places have none; dropping them would empty the list).
  - `min_rating` (`None` or a number): places with a lower `rating` are dropped. **Places without a rating are dropped** when a minimum is set (they cannot prove they meet it).
  - Without filters every result is kept.
- A response without `places` (Google sends `{}` when nothing is found) returns `[]`.
- Results without an `id`, or with an id that is already in the list, are skipped.
- `PlacesError` is raised for: a timeout or connection error (any `requests.RequestException`), an HTTP status other than 200, and a body that is not valid JSON. The message of `PlacesError` never contains the API key.

`round_coordinate(value: float) -> float` rounds to 3 decimal places (about 100 m, AGENTS.md "Privacy").

### Form rules (`app/services/places.py`)

`validate_search(form) -> tuple[dict, list[str]]` cleans the search form and returns the cleaned values and the error messages (all problems at once).

| Field | Allowed values | Message |
|---|---|---|
| `category` | `restaurant`, `bar`, `cafe`, `movie_theater` (Google place types; shown as Restaurant, Bar, Café, Cinema) | `Please choose a category.` |
| `radius_m` | `500`, `1000`, `2000`, `5000` | `Please choose a radius.` |
| `latitude`, `longitude` | both present, numbers, latitude −90…90, longitude −180…180 (`nan`/`inf` rejected) | `Please share your location so we can search nearby.` (one message for any location problem) |
| `min_rating` | empty (no filter), `3.5`, `4.0`, `4.5` | `Please choose a valid minimum rating.` |
| `max_price_level` | empty (no filter), `1`, `2`, `3`, `4` | `Please choose a valid price level.` |

Cleaned values: `category` (text), `radius_m` (int), `latitude` and `longitude` (float, rounded with `round_coordinate`), `min_rating` (float or `None`), `max_price_level` (int or `None`).

### Room page and route

- `GET /rooms/<room_id>`, for the **creator** of a room with mode `nearby`, status `collecting` and **no Google option yet**, additionally shows a search form posting to `/rooms/<room_id>/suggest` with the fields above. `latitude` and `longitude` are hidden fields; a "Use my location" button runs `app/static/js/geolocation.js`, which asks the browser for the location, rounds it to 3 decimals and fills the hidden fields. Nobody else sees this form, and it disappears after a successful search.
- `POST /rooms/<room_id>/suggest`, checked in this order:

| Case | Status | Message | Saved |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined | 403 | `Please join the room before adding options.` (same as A4) | nothing |
| joined, but not the creator | 403 | `Only the creator can search for places.` | nothing |
| room mode is not `nearby` | 400 | `Places can only be suggested in a "Places nearby" room.` | nothing |
| room status is not `collecting` | 400 | `Options can only be added before voting starts.` (same as A4) | nothing |
| the room already has Google options | 400 | `Places have already been suggested for this room.` | nothing |
| invalid form (table above) | 400 | every message; the form is shown again with the entered values | nothing |
| `GOOGLE_MAPS_API_KEY` is not set (empty) | 503 | `Place suggestions are not available right now. You can still add options yourself.` | nothing; Google is not called |
| `search_nearby` raises `PlacesError` | 503 | same message as above | nothing |
| Google finds nothing (after the filters) | 200 | `No places found. Try a larger radius or fewer filters.`; the search form is shown again | nothing |
| the database refuses the insert (e.g. the same search sent twice at the same moment) | 400 | `Places have already been suggested for this room.` | nothing from this request |
| valid and places found | 303 redirect to `GET /rooms/<room_id>` | – | see below |

- Saved on success, in **one transaction** (all or nothing, via `db.transaction()` so it works on Postgres):
  - one option per place id: `source = 'google'`, `place_id`, `label` empty (NULL), `category` = the chosen category, `is_replaced = 0`, in Google's order;
  - on the room: `search_center_lat`, `search_center_lng` (rounded), `radius_m`, and `filters` as JSON text `{"category": …, "min_rating": …, "max_price_level": …}` (C2b needs the centre for the distance, C4 the filters).
- **Never stored:** names, ratings, price levels or anything else from Google except the place id (Google terms, AGENTS.md).
- The API key is read from `app.config["GOOGLE_MAPS_API_KEY"]`, which `create_app()` fills from the environment variable of the same name. It never appears in a page, a message or a log.
- Until C2b, the option list shows a Google option as `Place from Google Maps` (no name is stored to show). Manual options still show their label; manual adding (A4) keeps working in `nearby` rooms, before and after the search.

Checks (one line = one test):

`tests/test_places.py` – the Google call, `requests.post` always replaced by a fake:
- [ ] Sends one POST to the Nearby Search URL with `timeout=5`.
- [ ] Sends the API key and the field mask headers; the field mask is exactly `places.id,places.rating,places.priceLevel` and never contains `*`.
- [ ] Sends category, `maxResultCount: 15`, centre and radius in the JSON body.
- [ ] Returns the place ids in Google's order.
- [ ] A response without `places` returns `[]`.
- [ ] Results without an id and duplicate ids are skipped.
- [ ] `max_price_level` drops more expensive places and keeps places without a price level.
- [ ] `min_rating` drops lower-rated places and places without a rating; a rating exactly at the minimum is kept.
- [ ] Without filters, all results are kept.
- [ ] A timeout, a connection error, a non-200 status and an invalid JSON body each raise `PlacesError`.
- [ ] The `PlacesError` message never contains the API key.
- [ ] `round_coordinate` rounds to 3 decimals.
- [ ] `validate_search` accepts a valid form and returns cleaned, typed values with rounded coordinates.
- [ ] `validate_search` rejects an unknown or missing category, an unknown radius, a missing, non-numeric, `nan` or out-of-range location, an unknown minimum rating and an unknown price level – each with its message.
- [ ] `validate_search` with several problems returns every message.

`tests/test_places_search.py` – room page and route, Google always faked:
- [ ] Creator of a `nearby` room sees the search form with all fields, the hidden location fields and the geolocation script.
- [ ] A joined non-creator, a visitor, and the creator of a `manual` or `surprise` room do not see the search form.
- [ ] Accepted: a valid search redirects to the room page.
- [ ] Accepted: each found place is stored as a Google option with place id, chosen category, empty label, `is_replaced = 0`, in Google's order.
- [ ] Accepted: the room stores the rounded centre, the radius and the filters as JSON.
- [ ] Accepted: the coordinates are rounded on the server even if the browser sends more decimals.
- [ ] Accepted: Google is called with the configured key and the cleaned form values (category, rounded centre, radius, filters).
- [ ] Accepted: after the search, every participant sees one `Place from Google Maps` entry per place, and the search form is gone.
- [ ] Accepted: manual options can still be added after the search, and earlier manual options are kept.
- [ ] Accepted: nothing but the place id is stored from Google (no name in the database).
- [ ] Rejected: no places found – message, search form shown again, nothing saved.
- [ ] Rejected: Google error – friendly message, status 503, nothing saved, manual add form still shown.
- [ ] Rejected: no API key configured – same message, status 503, Google not called, nothing saved.
- [ ] Rejected: invalid form – status 400, messages, entered values shown again, Google not called, nothing saved.
- [ ] Rejected: a second search in the same room – message, Google not called, data unchanged.
- [ ] Rejected: a joined non-creator – status 403, Google not called, nothing saved.
- [ ] Rejected: a visitor, and a participant of another room – status 403, Google not called, nothing saved.
- [ ] Rejected: a `manual` or `surprise` room – message, Google not called, nothing saved.
- [ ] Rejected: a room that is `voting` or `closed` – message, Google not called, nothing saved.
- [ ] Rejected: unknown room – 404, Google not called.
- [ ] Edge case: if the database refuses the insert (simulated by making the "already suggested" check return False although Google options exist), the app shows the message, does not crash and leaves the data unchanged.
- [ ] Security: the API key never appears in any page (search form, success, error).
- [ ] Persistence: after an app restart, the Google options and the room's search settings are still stored and shown.

## Out of scope
- Option cards with name, photo, rating, price level, distance and the `/photo/<photo_name>` proxy (C2b). Place Details calls.
- "Open at the planned time" filter (needs opening hours and a planned time, which no room has yet).
- Surprise mode searches and widening the radius (C4/F12); "Been there" (C5/F13).
- Searching around the group's midpoint, participants' locations, or a typed address (F19 is parked).
- Repeating a search, or deleting Google options to search again.
- Deleting the search centre when the room closes (belongs to the task that closes rooms).
- Map and route (C3/F9). PWA files.
- Switching A4's `add_manual_option` from `with connection:` to `db.transaction()` (A4's follow-up; A4 is not merged yet).
- No changes to `app/schema.sql` (all columns exist) or to existing tests.

## Done when
- All tests in `tests/test_places.py`, `tests/test_places_search.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test calls Google: every test replaces `requests.post`.
- SQL only in `app/db.py`, rules and the Google call in `app/services/places.py`, thin route in `app/routes/rooms.py`, Jinja templates, JavaScript only in `app/static/js/geolocation.js`.
- With a real key: a search in a `nearby` room on the deployed app (HTTPS, for the location) fills the option list; with a wrong key the friendly message appears and manual options still work.
- Work is on branch `feature-c2-places-search`, pushed, pull request opened with Timonhio as reviewer (review circle: B reviews C).
