# E5 – Typed options come back, but only while Google Maps is unavailable

Branch: `feature-e5-typed-fallback` (from `main`)
Tests: `tests/test_typed_fallback.py` (new)
Decision: `docs/decisions.md`, D23. Changes E1 (`specs/e1-places-only-via-maps.md`) for the case that Google cannot be reached.

## Why
Since E1 (#80) every option comes from Google Maps. That gives every card a photo and a map, but when Google cannot be reached (no key, network down, trial credit used up) a group can no longer add **any** option, and the room is stuck. D6 and AGENTS.md promise the opposite ("the group continues with manual options"). The course asks for "External API failures handled gracefully". So the typed field comes back, as a fallback only: normally Google stays the only way, as E1 wants.

## What

### When is the fallback on?
- **On** after a call to Google failed because Google could not be used, in any of these routes: find a place by name (C6), places nearby (C2a), surprise (C4), "Been there" (C5). That is every `except places.PlacesError` branch and every "no server key" branch that today answers with `PLACES_UNAVAILABLE_MESSAGE`.
- It stays on for **10 minutes** after the last failure (`FALLBACK_MINUTES = 10`), then turns off by itself.
- A **successful** Google call in one of these routes turns it off at once.
- The state lives **in the app object** (`current_app.extensions["google_unavailable_until"]`, a UTC `datetime` or missing), set and read only through two functions in `app/services/places.py`: `note_google_unavailable(app, now)` / `note_google_available(app)` and `typed_fallback_active(app, now) -> bool`. `now` is a parameter, so tests can move time.
  - Limit (write it in D23): with several gunicorn workers each worker has its own state, so one worker may show the field a moment later than another. That is acceptable for a fallback.
  - No database or schema change.

### While the fallback is on
- The room page shows the **typed form again** (the one E1 removed: label `Add an option`, `name="label"`, `POST /rooms/<id>/options`, button `Add option`), with one line above it: `Google Maps is not reachable right now – you can add your idea as text.`
  - Only while the room is collecting and the participant is below the options-per-person limit (F27), as before E1.
  - In a manual room it sits where the find form is; in nearby/surprise rooms inside the folded `Add a place by name` row (`details.own-idea`), which then opens (`open`).
- `POST /rooms/<id>/options` works **exactly as before E1**: participant check (403), status check, empty / too long / duplicate label (400, same messages), F28 hidden-idea message, F27 limit in one transaction, Post/Redirect/Get. Restore the removed code from git: `git show 0ebd94c -- app/routes/rooms.py app/db.py app/services/options.py app/templates/room.html` shows everything E1 deleted (`add_option`, `is_someone_elses_hidden_idea`, `db.add_manual_option`, `db.add_manual_option_within_limit`, `db.get_option_labels`, `options.option_errors`, the template block). Typed options are saved with their author in `option_authors`, as before.

### While the fallback is off (the normal case)
- Nothing changes compared with E1: no typed field, and `POST /rooms/<id>/options` answers **404** and saves nothing. So E1's reviewed tests in `tests/test_places_only_via_maps.py` stay unchanged and green.

### Docs (part of this task)
- `docs/decisions.md`: new **D23** (what, why, the 10 minutes, the per-worker limit), and the last bullet of **D6** changed to "If Google fails: friendly message; for 10 minutes the group can add options as text (D23)".
- `AGENTS.md`, External APIs: same change in the line "On any error, show a friendly message and let the group continue with manual options."

### Not in this task
- No change to E2–E4, the design, scoring or voting. No JavaScript. No new dependency.

## Checks (one line = one test), `tests/test_typed_fallback.py`
Tests never call Google: fake `requests.post` / `requests.get` the way `tests/test_place_by_name_route.py` does, and pass `now` to move time.
- [ ] Normal case: no failure so far → no typed field on the room page; `POST /options` → 404, nothing saved (same as E1).
- [ ] A failed search by name (fake Google raises `requests.Timeout`) → the room page now shows the typed form and the line `Google Maps is not reachable right now – you can add your idea as text.`
- [ ] Without a server key, a search by name turns the fallback on (and still shows the friendly 503 message).
- [ ] A failed nearby search and a failed surprise search each turn it on.
- [ ] While on: a typed option is saved with its author and the page redirects to the room (303).
- [ ] While on, rejected with the old messages and nothing saved: empty label, too long label, duplicate label (also other upper/lower case), not joined (403), room not collecting, over the F27 limit.
- [ ] While on, in a room with hidden ideas (F28): someone else's hidden idea as label gives `Someone already had the same idea – it is already in the room.`
- [ ] In a nearby and a surprise room the form is inside `details.own-idea`, and that block is open.
- [ ] 10 minutes after the last failure the field is gone and `POST /options` is 404 again.
- [ ] A successful search by name after a failure turns the fallback off at once.
- [ ] The state belongs to the app: a second app created in the same test has no fallback.

All existing tests stay green and unchanged (`uv run pytest`). Paste the final output and list every file changed.
