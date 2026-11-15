# C2b – F8 Place cards: name, photo, rating, price level, distance

Branch: `feature-c2b-place-cards`
Tests: `tests/test_place_details.py` (the Google calls and the card rules, with fake responses) and `tests/test_place_cards.py` (room page and photo proxy)

Second half of C2 (F8). C2a (`specs/c2-places-search.md`, merged in #12) saves the found places as options, but stores only their place id, so every Google option still shows as `Place from Google Maps`. C2b loads the details when the option list is shown and turns each Google option into a card.

## Why
In a "Places nearby" room the group cannot tell the places apart yet, so nobody can choose between them. Each card must show what F8 promises (name, photo, rating, price level and distance) without storing anything from Google except the place id (Google terms) and without ever showing the API key, which is why photos go through our own server.

## What
F8 in `docs/concept.md` and "Google Maps integration" in `AGENTS.md`. Decisions for this task (2026-11-15):
- **Room page now, rating page later.** The card is a reusable Jinja macro. C2b uses it in the room page's option list. The rating page (`vote.html`) only exists in B2 (PR #11, not merged), so using the macro there is a small follow-up after B2 is merged.
- **No cache.** Details are loaded fresh on every view (Google terms allow storing only the place id). One Place Details call per Google option per page view, nothing for manual options. The room page has no meta refresh, so calls only happen when someone opens or reloads it. Cost protection is the daily quota in Google Cloud (raise the Place Details quota to about 500/day).

### Place Details (`app/services/places.py`)

`get_place_details(api_key, place_id) -> dict` loads one place, or raises `PlacesError`.

- One `requests.get` to `https://places.googleapis.com/v1/places/<place_id>` with `timeout=5` and the headers `X-Goog-Api-Key: <api_key>` and `X-Goog-FieldMask: displayName,rating,priceLevel,location,photos` (constant `DETAILS_FIELD_MASK`; never `*`).
- The place id is checked before it is put into the URL: only letters, digits, `_` and `-` (`PLACE_ID_PATTERN`). Anything else raises `PlacesError` without calling Google.
- Returns a dict with exactly these keys (missing or unusable values are `None`):
  - `name`: `displayName.text`
  - `rating`: `rating` (a number)
  - `price_level`: `priceLevel` as a number with the C2a mapping (`PRICE_LEVEL_FREE` 0 … `VERY_EXPENSIVE` 4; anything else `None`)
  - `latitude`, `longitude`: from `location`
  - `photo_name`: the `name` of the **first** photo, only if it has the form `places/<place id>/photos/<photo reference>` with the same place id (`PHOTO_NAME_PATTERN`, letters, digits, `_`, `-`), else `None`
  - `photo_author`, `photo_author_uri`: `displayName` and `uri` of the first photo's first `authorAttributions` entry; the uri only if it starts with `https://` (no `javascript:` links), else `None`
- `PlacesError` for a timeout or connection error, an HTTP status other than 200, a body that is not valid JSON or not an object. The message never contains the API key.

### Card rules (`app/services/places.py`, no Flask, no database)

- `distance_m(latitude_1, longitude_1, latitude_2, longitude_2) -> int`: great-circle (haversine) distance in metres, Earth radius 6 371 000 m, rounded to whole metres.
- `format_distance(metres) -> str`: under 1000 m → rounded to 10 m, e.g. `330 m`; from 1000 m → kilometres with one decimal, e.g. `1.2 km`. (A value that rounds to 1000 m is shown as `1.0 km`.)
- `format_price_level(level) -> str`: `0` → `Free`, `1`–`4` → `€` … `€€€€`, `None` → `""`.
- `format_rating(rating) -> str`: one decimal and a star, e.g. `4.0 ★`; `None` → `""`.
- `build_card(option, details, centre_latitude, centre_longitude) -> dict` turns one option (a row with `source`, `label`, `place_id`) and its details into what the template shows:
  - manual option: `{"source": "manual", "label": …}` (no Google data);
  - Google option with details: `source`, `name`, `photo_name`, `photo_author`, `photo_author_uri`, `rating_text`, `price_text`, `distance_text`, and `details_missing = False`. `distance_text` is `""` if the room has no centre or the place has no location. A place without a name gets the name `Place from Google Maps`.
  - Google option without details (`details` is `None`): `name = "Place from Google Maps"`, every text empty, no photo, `details_missing = True`.
- `load_cards(api_key, options, centre_latitude, centre_longitude) -> list[dict]`: one card per option, in the given order. Calls `get_place_details` once per Google option. A `PlacesError` for one option only makes **that** card fall back (`details_missing`); the others are still shown. Without an API key (empty or `None`) Google is not called and every Google card falls back.

### Room page (`app/templates/room.html`, macro in `app/templates/_place_card.html`)

- For a joined participant, the option list shows one entry per option, as before. A manual option still shows its label. A Google option shows the card:
  - the name as a heading;
  - if there is a `photo_name`: `<img src="/photo/<photo_name>" alt="Photo of <name>" loading="lazy">` and below it `Photo: <author>`, linked to `photo_author_uri` if there is one;
  - a line with the rating text, the price text and the distance text that are not empty, e.g. `4.5 ★ · €€ · 330 m`;
  - the attribution text `Google Maps` (Google terms);
  - if `details_missing`: `Place from Google Maps` and `Details are not available right now.`
- Everything from Google is shown escaped (Jinja autoescape); a name like `<script>` is text, never a tag.
- `db.get_room` also returns `search_center_lat` and `search_center_lng`, so the route can pass the room's centre to `load_cards`.
- Visitors still see no options, so their page view never calls Google.
- Nothing from the details is written to the database.

### Photo proxy (`GET /photo/<path:photo_name>`, new blueprint in `app/routes/pwa.py`)

`fetch_photo(api_key, photo_name) -> tuple[bytes, str]` in `app/services/places.py` loads one photo, or raises `PlacesError`:
- one `requests.get` to `https://places.googleapis.com/v1/<photo_name>/media` with `params={"maxWidthPx": 400}`, the header `X-Goog-Api-Key`, `timeout=5`; `requests` follows Google's redirect to the image itself, so the browser never sees the key or the redirect URL;
- returns the image bytes and the `Content-Type`;
- `PlacesError` for a network error, a status other than 200, or a `Content-Type` that does not start with `image/`; also (without calling Google) for a `photo_name` that does not match `PHOTO_NAME_PATTERN`. The message never contains the key.

The route, checked in this order:

| Case | Status | Google called? |
|---|---|---|
| `photo_name` does not match `places/<place id>/photos/<reference>` | 404 | no |
| the place id is not a Google option of a room this browser has joined (token in the session that belongs to a participant of that room) | 404 (same page as an unknown URL, so it does not reveal anything) | no |
| `GOOGLE_MAPS_API_KEY` is not set | 503, plain text `Photo not available.` | no |
| `fetch_photo` raises `PlacesError` | 503, plain text `Photo not available.` | yes |
| success | 200, the image bytes with Google's `Content-Type` and `Cache-Control: private, max-age=600` | yes |

- Why the room check: without it, anyone could use our server (and our quota) to load any Google photo.
- The response never contains the API key (body or headers).

### Tests never call the network

`tests/` is frozen for C2a, and C2a's tests replace only `requests.post`. With C2b the room page also calls `requests.get`, so the C2a page tests would reach Google with a fake key. A new **`conftest.py` in the project root** (not in `tests/`) adds an autouse fixture that makes every real `requests` call raise `requests.ConnectionError("Tests never call the network")` (it replaces `requests.Session.request`). Tests that fake `requests.get` or `requests.post` replace those functions directly, so their fakes still work; everything else behaves as if Google were unreachable, which the app already handles (fallback card).

Checks (one line = one test):

`tests/test_place_details.py`:
- [ ] `get_place_details` sends one GET to the Place Details URL for the place id, with `timeout=5`, the key and exactly the field mask `displayName,rating,priceLevel,location,photos` (no `*`).
- [ ] It returns name, rating, price level as a number, latitude, longitude, the first photo's name and its first author's name and https uri.
- [ ] Missing fields give `None` (an empty `{}` answer gives `None` for every key).
- [ ] `PRICE_LEVEL_UNSPECIFIED` and unknown price texts give `price_level = None`.
- [ ] A photo name for a different place id or with other characters gives `photo_name = None`.
- [ ] An author uri that is not `https://` (e.g. `javascript:alert(1)`, `http://…`) gives `photo_author_uri = None`.
- [ ] A place id with characters other than letters, digits, `_`, `-` (e.g. `../x`, `a/b`, `a?b`, empty) raises `PlacesError` without calling Google.
- [ ] A timeout, a connection error, a non-200 status, invalid JSON and a JSON list each raise `PlacesError`; the message never contains the key.
- [ ] `distance_m` gives about 333 m for 0.003° of latitude and 0 for the same point.
- [ ] `format_distance`: 0 → `0 m`, 334 → `330 m`, 995 → `1.0 km`, 1000 → `1.0 km`, 1250 → `1.2 km`, 12345 → `12.3 km`.
- [ ] `format_price_level`: 0 → `Free`, 1 → `€`, 4 → `€€€€`, `None` → `""`.
- [ ] `format_rating`: 4 → `4.0 ★`, 4.56 → `4.6 ★`, `None` → `""`.
- [ ] `build_card` for a manual option, for a Google option with full details (incl. distance from the centre), for one without centre or location (no distance), for one without a name, and for missing details.
- [ ] `load_cards` keeps the order, calls Google once per Google option and never for manual options.
- [ ] `load_cards`: an error for one place only makes that card fall back.
- [ ] `load_cards` without a key does not call Google and makes every Google card fall back.
- [ ] `fetch_photo` sends one GET to `https://places.googleapis.com/v1/<photo_name>/media` with `maxWidthPx=400`, the key header and `timeout=5`, and returns the bytes and the content type.
- [ ] `fetch_photo` raises `PlacesError` for a bad photo name (without calling Google), a network error, a non-200 status and a non-image content type; the message never contains the key.
- [ ] Without a fake, a real `requests` call in a test raises `requests.ConnectionError` (the root `conftest.py` guard), so `get_place_details` raises `PlacesError`.

`tests/test_place_cards.py`:
- [ ] Creator and a joined guest see each Google option as a card: name, photo `<img>` with the proxy URL and alt text, `Photo:` with the author link, `4.5 ★ · €€ · 330 m`, and `Google Maps`.
- [ ] Manual options in the same room still show their label; Google is called once per Google option and not for manual options.
- [ ] A place without photo, rating, price or location shows its name and no `<img>`, and no empty separators.
- [ ] If Google fails for one place, that entry shows `Place from Google Maps` and `Details are not available right now.`; the other places still show their cards; status 200.
- [ ] Without an API key, every Google entry shows the fallback and Google is not called.
- [ ] A visitor's page view does not call Google.
- [ ] A name with HTML (`<script>`) and a `javascript:` author uri are shown safely: escaped text, no link.
- [ ] Viewing the page writes nothing to the database (rooms and options unchanged).
- [ ] The API key never appears in the room page.
- [ ] Photo proxy, joined participant: 200, the fake image bytes, Google's content type, `Cache-Control: private, max-age=600`, no key in body or headers; Google was called with the photo name.
- [ ] Photo proxy: a malformed photo name → 404, Google not called.
- [ ] Photo proxy: a visitor, a participant of another room, and a place id that is no option of the joined room → 404, Google not called.
- [ ] Photo proxy: no key → 503 `Photo not available.`, Google not called; Google error or non-image answer → 503 `Photo not available.`.
- [ ] Persistence: after an app restart, the room page shows the cards again (details are loaded fresh, nothing was stored).

## Out of scope
- Cards on the rating page (B2's `vote.html`): follow-up after B2 is merged; the macro is ready for it.
- Caching details or photos on the server (Google terms; decided 2026-11-15).
- Opening hours, address, reviews, more than one photo, a "more photos" view.
- Map and route to the winner (C3/F9), surprise mode (C4), "Been there" (C5).
- Showing the room's search settings (radius, filters) on the page.
- Changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_place_details.py`, `tests/test_place_cards.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network (root `conftest.py` guard).
- SQL only in `app/db.py`, Google calls and card rules in `app/services/places.py`, thin routes in `app/routes/rooms.py` and `app/routes/pwa.py`, Jinja templates, no new JavaScript.
- With a real key on the deployed app, a "Places nearby" room shows real cards with photos; with a wrong key the fallback appears and the page still works.
- Work is on branch `feature-c2b-place-cards`, pushed, pull request opened with Timonhio as reviewer.
