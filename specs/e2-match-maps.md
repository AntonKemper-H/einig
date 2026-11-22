# E2 – Small map for every match of the search by name

Branch: `feature-e2-match-maps`
Tests: `tests/test_match_maps.py`

Builds on C6 (find a place by name) and C3 (`places.map_embed_url`).

## Why
Two places can have the same name at different locations, and people often do not know the address. A small map next to each match shows at once which place is meant.

## What
- In step 2 of the search by name ("Which one do you mean?"), every match shows a small Google Maps embed (`<iframe>`) of that place, under its name and address, above the "Add this place" button.
- The iframe uses `places.map_embed_url(GOOGLE_MAPS_EMBED_KEY, place_id)` (C3): the browser key, restricted to our domain, never the server key. Embed requests are free.
- `loading="lazy"`, a `title` naming the place, `referrerpolicy="strict-origin-when-cross-origin"`. No JavaScript.
- Without an embed key (or with an invalid place id) the match is shown as before, without a map.
- Nothing is stored: the matches are still only shown, and the session still holds only their ids. The Text Search request is unchanged (no extra fields, no extra cost).
- **No scrolling:** after the search the page jumps to the matches (`autofocus` on the heading "Which one do you mean?", which has `tabindex="-1"`), so they appear right below the search field. Suggestions while typing are not possible without JavaScript and are not built (AGENTS.md).
