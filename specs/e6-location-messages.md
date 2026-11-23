# E6 – Clearer messages when "Use my location" fails

Branch: `feature-e6-location-messages`
Tests: `tests/test_location_messages.py`

Builds on C2a/C6 (`app/static/js/geolocation.js`). Asked for after a test on an iPad (2026-11-23).

## Why
On an iPad "Use my location" only said "Location not shared. Please allow location access and try again." and no permission prompt appeared, because Location Services for Safari Websites were switched off in iOS Settings. The app said the same for every error, so nobody could tell what to fix.

## What
- In the error callback of `getCurrentPosition`, `geolocation.js` reads `error.code` and shows one of three messages in `#location-status`:
  - `1` (PERMISSION_DENIED): `Location is blocked. Allow it for this site in your browser. On iPhone or iPad: Settings → Privacy & Security → Location Services → Safari Websites.`
  - `2` (POSITION_UNAVAILABLE): `Your location could not be found. Please try again.`
  - `3` (TIMEOUT): `Finding your location took too long. Please try again.`
- Any other code keeps the old text: `Location not shared. Please allow location access and try again.`
- Nothing else changes: still an explicit tap, the same rounding, the same options, the status text for "no geolocation" and for success stays.
- No new JavaScript file, no new dependency, no server change. `geolocation.js` is an allowed JS file (AGENTS.md).

The browser behaviour itself (the real error codes) cannot run in pytest and is checked by hand on a phone/iPad after deploying, like `swipe.js`. The tests check the file's source.

Checks (one line = one test), `tests/test_location_messages.py`:
- [ ] The error callback receives the error and reads `error.code`.
- [ ] Code 1 shows the "blocked" message with the iPhone/iPad path (`Location Services`, `Safari Websites`).
- [ ] Code 2 shows the "could not be found" message.
- [ ] Code 3 shows the "took too long" message.
- [ ] The three messages are different from each other.
- [ ] Other codes still get the old generic message.
- [ ] The "browser cannot share its location" and "Location shared" messages are unchanged.
- [ ] The rounding to 3 decimals and the `getCurrentPosition` options are unchanged.
- [ ] No new JavaScript file: `app/static/js/` still holds only `geolocation.js` and `swipe.js`.

## Out of scope
- Detecting the platform to show only the matching hint.
- Translating the messages.
- Any change to the server, templates or the search forms.

## Done when
- All tests in `tests/test_location_messages.py` pass (`uv run pytest`), output pasted.
- Checked by hand on the deployed app (iPad: Location Services off → blocked message).
- Work is on branch `feature-e6-location-messages`, pushed, pull request opened for review.
