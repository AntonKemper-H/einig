# C3 – F9 Map and route to the winner

Branch: `feature-c3-winner-map`
Tests: `tests/test_winner_map.py`

Builds on B3 (`specs/b3-result.md`, PR #19), which closes the room, stores the winner and adds the result page `GET /rooms/<room_id>/result`. C3 only adds to that page. The implementation starts after B3 is merged.

## Why
Once the group has decided on a place, the next question is "where is it and how do we get there?". The result page should answer that right away with a map of the winning place and one tap to open the route in Google Maps, without ever showing our server's API key and without storing anything from Google except the place id.

## What
F9 in `docs/concept.md` and "Google Maps integration" in `AGENTS.md`. Decisions for this task (2026-11-15):
- **Maps Embed API, not the Maps JavaScript API.** The concept names the JavaScript API; `AGENTS.md` (no JavaScript libraries, "Map of the winner: Maps Embed API in an `<iframe>`") overrides it. The embed is a plain `<iframe>` and needs no JavaScript from us. Embed requests are free.
- **Two keys, two jobs.** The iframe uses `GOOGLE_MAPS_EMBED_KEY`, the browser key restricted to our domain (decision D6). This key is meant to be seen by browsers. The server key `GOOGLE_MAPS_API_KEY` never appears in any page.
- **The route link needs no key and no API call.** It is a normal Google Maps URL that opens the Google Maps app or website.
- **Only Google winners get a map.** A manual option ("Movie night at my place") has no location, so it gets no map and no route link.
- **The place id appears in the page** (iframe and route link). Place ids are public Google identifiers, not secrets. B3's test `test_google_winner_is_named_as_a_google_place` currently checks `"place-x" not in html`; that line has to go in PR #19 (raised in the review), otherwise C3 cannot pass it.

### Map and route helpers (`app/services/places.py`, no Flask, no database)

- `EMBED_PLACE_URL = "https://www.google.com/maps/embed/v1/place"`, `ROUTE_URL = "https://www.google.com/maps/dir/"`.
- `map_embed_url(embed_key, place_id) -> str | None`: `EMBED_PLACE_URL + "?" + urlencode({"key": embed_key, "q": "place_id:" + place_id})`. `None` if `embed_key` is empty or `None`, or if `place_id` does not match `PLACE_ID_PATTERN` (C2b).
- `route_url(place_id, name) -> str | None`: `ROUTE_URL + "?" + urlencode({"api": "1", "destination": name, "destination_place_id": place_id})` (Google Maps URLs: the place id decides the destination, the name is shown while it loads). `None` if `place_id` does not match `PLACE_ID_PATTERN`. Both use `urllib.parse.urlencode`, so a name like `Bar & Grill "Lisboa"` cannot break the URL.
- `load_winner(api_key, embed_key, option) -> dict`: what the result page shows for the stored winner (a row with `source`, `label`, `place_id`):
  - manual option: `{"card": build_card(option, None, None, None), "map_url": None, "route_url": None}`, Google is not called;
  - Google option: `card` from `load_cards(api_key, [option], None, None)[0]` (one Place Details call, the C2b fallback card if there is no key or Google fails), `map_url = map_embed_url(embed_key, place_id)`, `route_url = route_url(place_id, card["name"])`. No centre is passed: B3 deletes the search centre when the room closes, so the card has no distance.
  - Map and route only need the place id, so they are shown even when the details fail.

### Config (`app/__init__.py`)
- `create_app()` reads `GOOGLE_MAPS_EMBED_KEY` from the environment (stripped, default `""`), like `GOOGLE_MAPS_API_KEY`. Tests set it in the test config. `.env.example` and `render.yaml` already list it.

### Result page (B3's result template)
For a **closed room with a Google winner**, below B3's "The group's choice: <name>" (the name is the card's name, so `Place from Google Maps` if the details fail):
- the C2b card (`_place_card.html` macro): photo through the photo proxy, rating, price, `Google Maps` attribution;
- if `map_url`: `<iframe src="<map_url>" title="Map of <name>" width="100%" height="300" style="border: 0" loading="lazy" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>` (the referrer policy sends our origin, which the key restriction checks);
- if there is no embed key: no iframe, the rest of the page is unchanged;
- if `route_url`: a link `Open route in Google Maps` to `route_url` with `target="_blank" rel="noopener noreferrer"`.

Everything else on the page stays as in B3 (anonymous counts, no nicknames). Names from Google are escaped by Jinja, also inside the `title` attribute.

No Google call and no map or route link for: a manual winner, a closed room without a winner, a room that is not closed yet, a visitor (B3 redirects them). Viewing the result writes nothing to the database.

Checks (one line = one test):

#### Helpers
- [ ] `map_embed_url("embed-key", "place-a")` is the embed URL with exactly the query `key=embed-key` and `q=place_id:place-a`.
- [ ] `map_embed_url` returns `None` without a key (`""` and `None`) and for a bad place id (`../x`, `a/b`, `a?b`, `""`).
- [ ] `route_url("place-a", "Pizza Roma")` is `https://www.google.com/maps/dir/` with exactly `api=1`, `destination=Pizza Roma`, `destination_place_id=place-a`.
- [ ] `route_url` encodes a name with `&`, `"`, `#` and spaces so the query reads back unchanged, and returns `None` for a bad place id.
- [ ] `load_winner` for a manual option: the manual card, no map, no route, Google not called.
- [ ] `load_winner` for a Google option: one Place Details call, the card with name and photo, no distance, map and route URLs for the place id.
- [ ] `load_winner` when Google fails (error status or timeout): fallback card (`details_missing`), map and route URLs still there; route destination `Place from Google Maps`.
- [ ] `load_winner` without a server key: Google not called, fallback card, map and route URLs still there.
- [ ] `load_winner` without an embed key: `map_url` is `None`, route URL still there.

#### Config
- [ ] A real run (no test config) reads `GOOGLE_MAPS_EMBED_KEY` from the environment, stripped; an empty variable gives `""`.

#### Result page
- [ ] Closed room with a Google winner: the page shows "The group's choice: Pizza Roma", the photo through `/photo/…`, the rating, an iframe whose `src` is the embed URL for the winner's place id and whose `title` is `Map of Pizza Roma`, and the link `Open route in Google Maps` to the route URL (opens in a new tab, `rel="noopener noreferrer"`).
- [ ] Only the winner's details are loaded: one Place Details call per page view, none for the other options.
- [ ] The server key never appears in the page; the embed key appears only inside the iframe `src`.
- [ ] Without an embed key: no `<iframe>`, the route link is still there, status 200.
- [ ] Google fails for the winner: status 200, "The group's choice: Place from Google Maps", "Details are not available right now.", the map and the route link still there.
- [ ] A manual winner: "The group's choice: Pizza", no `<iframe>`, no route link, Google not called.
- [ ] A closed room without a winner, and a room that is still voting: no `<iframe>`, no route link, Google not called.
- [ ] A name with HTML and quotes (`<script>"x"</script>`) is escaped in the heading and the iframe title, and correctly encoded in the route link.
- [ ] Viewing the result page writes nothing to the database.
- [ ] Persistence: after an app restart, the result page shows the map and the route link again (nothing from Google was stored).

## Out of scope
- Names and photos for the other options in B3's count list (would mean one Place Details call per option on every view). Possible follow-up.
- A map for manual options, or a search link built from their label.
- Distance or travel time to the winner (F20 is parked); the user's own location.
- The Maps JavaScript API, any JavaScript, markers for several places.
- Changes to B3's close logic, counts or privacy rules, to `app/schema.sql`, or to existing tests.
- Setting up or restricting the embed key in Google Cloud (done by a human: Maps Embed API only, HTTP referrer `https://nod-lqeq.onrender.com/*` and the local address).

## Done when
- All tests in `tests/test_winner_map.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network (root `conftest.py` guard).
- Helpers in `app/services/places.py`, config in `app/__init__.py`, the result route stays thin, Jinja only, no new JavaScript.
- On the deployed app with real keys, a closed "Places nearby" room shows the winner on a map and the route link opens Google Maps; without the embed key the page still works without a map.
- Work is on branch `feature-c3-winner-map`, pushed, pull request opened with Timonhio as reviewer (B reviews C).
