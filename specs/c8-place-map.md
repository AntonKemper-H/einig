# C8 – F26 Map of my places and of a group

Branch: `feature-c8-place-map`
Tests: `tests/test_place_map.py` (map rules and Google calls, with fake responses), `tests/test_place_map_route.py` (map routes, "My places" page, group page)

Decision: `docs/decisions.md`, D15. Built after **C7** is merged (the `visits` table and the "My places" page). Needs the **Maps Static API** enabled in Google Cloud and allowed for `GOOGLE_MAPS_API_KEY` (mkim-nova, before testing on the deployed app).

## Why
A number and a list are a collection; a map with your own pins is the game. The same picture on the group page shows where a group has been together. It must work without JavaScript, never show the API key, and keep the Google bill small.

## What

### Decisions in this spec (please check in the review)
- **A picture, not an interactive map:** the server loads a PNG from the Maps Static API and sends it on through its own route, like the photo proxy (C2b). No JavaScript, the key never reaches the browser. The C3 Embed map shows only one place, so it cannot be used.
- **Pins only, Google fits the view:** without `center` and `zoom`, the Static API zooms to show every pin (a city or the whole world). With **one** pin it would zoom in all the way, so then `center` = that pin and `zoom=14`.
- **At most 25 pins** (`MAX_MAP_PINS`): the 25 most recently collected different places. Each pin needs one location call, so this caps the cost of one picture at 25 + 1 calls.
- **Locations are loaded fresh** with a separate, small call (field mask `location` only) and never stored (Google terms). A place whose location cannot be loaded is left out; the rest of the map still works.
- **Cached in the browser for 10 minutes** (`Cache-Control: private, max-age=600`), like photos, so reloading the page does not cost new calls. A newly collected place may appear up to 10 minutes later in a browser that already loaded the map; the image URL contains the number of places (`?n=<count>`) so a new place changes the URL and loads a new picture.
- **Group map:** every place collected in one of the group's rooms (`visits.group_id`), by anyone who took part, members or guests. Only places are shown, never who collected them or how many people did.
- **Who may load a map:** the personal map only for the browser's own person token; a group map only for a member of that group. Everything else is the same 404 as an unknown URL (reveals nothing, as in C2b).

### Rules and Google calls
`app/services/places.py`:
- `LOCATION_FIELD_MASK = "location"`.
- `get_place_location(api_key: str, place_id: str) -> tuple[float, float] | None` – `GET https://places.googleapis.com/v1/places/<place_id>` with `X-Goog-Api-Key` and `X-Goog-FieldMask: location`, timeout 5 s. Returns `(latitude, longitude)`, or `None` if the answer has no valid numbers. Timeout, connection error or an error status raise `PlacesError`.

`app/services/place_map.py` (new; no Flask, no database):
- `MAX_MAP_PINS = 25`, `MAP_SIZE = "640x400"`, `MAP_CACHE_CONTROL = "private, max-age=600"`, `SINGLE_PIN_ZOOM = 14`.
- `static_map_params(locations: list[tuple[float, float]]) -> dict[str, str] | None` – the query parameters **without the key**: `size` = `MAP_SIZE`, `scale` = `"2"`, `markers` = `"color:red|<lat>,<lng>|<lat>,<lng>…"` with each coordinate written with 5 decimals, at most `MAX_MAP_PINS` locations (the first ones in the list). With exactly one location also `center` = `"<lat>,<lng>"` and `zoom` = `"14"`. `None` for an empty list.
- `load_locations(api_key, place_ids, get_location) -> list[tuple[float, float]]` – calls `get_location` for at most the first `MAX_MAP_PINS` place ids, in order; skips a place that gives `None` or raises `PlacesError`. (`get_location` is passed in so tests can fake it.)
- `fetch_static_map(api_key: str, params: dict[str, str]) -> tuple[bytes, str]` – `GET https://maps.googleapis.com/maps/api/staticmap` with the params plus `key`, timeout 5 s; returns the body and its content type. An error status, a content type that is not an image, a timeout or a connection error raise `PlacesError`. **The error message never contains the URL** (the key is in it).

### Routes (in `app/routes/pwa.py`, next to the photo proxy)

| Route | Allowed when | Pins |
|---|---|---|
| `GET /map/me.png` | the browser has a person token with at least one visit | this person's 25 most recently collected different places |
| `GET /map/groups/<group_id>.png` | the browser is a member of that group and the group has at least one visit | the group's 25 most recently collected different places |

| Case | Answer |
|---|---|
| not allowed (no token, no visits, not a member, unknown group) | 404, Google not called |
| no `GOOGLE_MAPS_API_KEY` | 503 `Map not available.` (plain text), Google not called |
| no location could be loaded | 503 `Map not available.`, the Static API is not called |
| `fetch_static_map` raises `PlacesError` | 503 `Map not available.` |
| success | the image with its content type and `MAP_CACHE_CONTROL` |

### Pages
- **"My places"** (C7): between the count and the badges, if the person has visits and a key is set: `<img src="/map/me.png?n=<count>" alt="Map of the places you have collected" width="640" height="400">` (CSS: `max-width: 100%; height: auto`, so it fits a 380 px phone without horizontal scrolling). If more than 25 places: the note `The map shows your 25 most recent places.` No image and no note without visits.
- **Group page** (A9), for members only: a section **"Places we've been"** with `<n> places` and the image `/map/groups/<id>.png?n=<count>`; without visits: `No places yet. Press "I was there ✓" after your next decision.` Not shown to non-members.
- When the image cannot load, the browser shows the `alt` text; the rest of the page is unchanged.

### `app/db.py`
New: `get_group_place_ids(group_id, limit)` and `count_group_places(group_id)` (different place ids, newest visit first). C7's `get_visited_places` is reused for the personal map.

Checks (one line = one test):

`tests/test_place_map.py` (`requests.get` always faked)
- [ ] `get_place_location` sends `GET` to the place URL with the key header, the field mask `location` and timeout 5; returns `(lat, lng)` for a valid answer.
- [ ] `get_place_location` returns `None` for an answer without location or with non-numbers; raises `PlacesError` for a timeout and an error status.
- [ ] `static_map_params` with three locations: `size`, `scale`, one `markers` value with three pins with 5 decimals, no `center`, no `zoom`, no `key`.
- [ ] `static_map_params` with one location adds `center` and `zoom` 14.
- [ ] `static_map_params` with 30 locations has exactly 25 pins (the first 25); with none it returns `None`.
- [ ] `load_locations` calls the location function at most 25 times, keeps the order, and skips places that give `None` or raise `PlacesError`.
- [ ] `fetch_static_map` sends `GET` to the Static Maps URL with the params and the key, timeout 5; returns the bytes and the content type.
- [ ] `fetch_static_map` raises `PlacesError` for an error status, a non-image answer, a timeout; the error message does not contain the key.

`tests/test_place_map_route.py` (Google always faked, visits and groups set up in the database)
- [ ] `/map/me.png` for a browser with visits: an image answer with `MAP_CACHE_CONTROL`; Google gets one location call per place and one Static call with these pins.
- [ ] `/map/me.png` with 30 collected places: 25 location calls, the most recent places.
- [ ] `/map/me.png` without person token, and with a token without visits: 404, Google not called.
- [ ] `/map/groups/<id>.png` for a member: the image with the places collected in the group's rooms, including a guest's visit; a place collected twice is one pin.
- [ ] `/map/groups/<id>.png` for a non-member and for an unknown group: 404, Google not called.
- [ ] No key: 503 `Map not available.`, Google not called.
- [ ] Every location call fails: 503, the Static API is not called.
- [ ] One location call fails: the map is loaded with the other pins.
- [ ] Static API error: 503 `Map not available.`; the key is not in the answer.
- [ ] "My places" with visits shows the image with `?n=<count>` and the alt text; with more than 25 places also the note; without visits no image.
- [ ] The group page shows "Places we've been" with the count and the image to members, the "No places yet" text without visits, and nothing of it to non-members.
- [ ] Security: the API key never appears in any page or map answer.
- [ ] Privacy: no page and no map shows who collected a place or how many people did.

## Out of scope
- An interactive map (zoom, tap on a pin), the Maps JavaScript API, clustering, different pin colours per category.
- Storing locations or any other Google data; a server-side cache of pictures.
- A world map with countries coloured in, distances travelled, more badges (C7 owns the badges).
- Maps on the result page or the room page (C3's map stays as it is).
- JavaScript, changes to existing tests.

## Done when
- All tests in both test files and all earlier tests pass (`uv run pytest`), output pasted.
- No test calls Google (fakes for `requests.get`, root `conftest.py` guard for everything else).
- On the deployed app with a real key: "My places" shows a map with a pin for each collected place, and the group page shows the group's places; with a wrong key the alt text appears and the pages still work.
- Work is on branch `feature-c8-place-map`, pushed, pull request opened for review.
