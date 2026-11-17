# C7 – F26 "I was there": collect places and earn badges

Branch: `feature-c7-collect-places`
Tests: `tests/test_collection.py` (badge rules), `tests/test_collection_route.py` (result page, route, "My places" page, photo proxy)

Decision: `docs/decisions.md`, D15. Built after **A9** is merged (needs the `groups` and `group_rooms` tables). The new table is a schema change: Track A (schema owner, D10) reviews it.

## Why
The app ends at the result page. Collecting the places a group really went to turns every decision into a small step in a game, gives people a reason to come back, and is the data for the map (C8). It must stay as private as the rest: no account, nothing from Google stored but the place id, and nobody sees what someone else collected.

## What

### Decisions in this spec (please check in the review)
- **Only on purpose:** a place is collected only when a participant presses `I was there ✓` on the result page. The winner alone is not collected, because groups do not always go.
- **Only Google winners:** a manual winner has no place id and no location, so it cannot be collected.
- **Only after the decision:** the room must be `closed` with a winner. There is no time limit after that (until the room is deleted after 7 days).
- **A person token:** `session["person_token"]`, `secrets.token_urlsafe(32)`, created at the first `I was there`, in the permanent cookie (A8). It is never shown and never part of a URL.
- **Once per room:** pressing it again for the same room changes nothing (unique constraint). Collecting the same place from two different rooms is two visits, but counts as **one** collected place.
- **Not linked to the room:** `visits.room_id` has no foreign key, so a visit stays when the room is deleted after 7 days.
- **Badges** come only from our own data (numbers of places), so they cost no Google call.

### Schema (`app/schema.sql`)
```
visits (
    id            INTEGER PRIMARY KEY,
    person_token  TEXT NOT NULL,
    place_id      TEXT NOT NULL CHECK (trim(place_id) <> ''),
    room_id       TEXT NOT NULL,           -- no foreign key: the visit outlives the room
    group_id      TEXT REFERENCES groups (id) ON DELETE SET NULL,
    from_surprise INTEGER NOT NULL DEFAULT 0 CHECK (from_surprise IN (0, 1)),
    visited_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (person_token, room_id)
)
```
A new table, so `CREATE TABLE IF NOT EXISTS` is enough for the deployed database.

### Badge rules (`app/services/collection.py`, no Flask, no database)
`BADGES` is a module-level list; each badge has `key`, `title`, `description`, `counts` (`"places"`, `"surprise"` or `"group"`) and `goal`:

| key | title | description | counts | goal |
|---|---|---|---|---|
| `first_place` | First place | Collect your first place | places | 1 |
| `regular` | Regular | Collect 5 places | places | 5 |
| `explorer` | Explorer | Collect 10 places | places | 10 |
| `globetrotter` | Globetrotter | Collect 25 places | places | 25 |
| `surprise_hunter` | Surprise hunter | Collect 3 places from "Surprise me" | surprise | 3 |
| `squad` | Squad | Collect 3 places with a group | group | 3 |

- `badge_progress(place_count: int, surprise_count: int, group_count: int) -> list[dict]` returns one entry per badge, in table order, with `title`, `description`, `earned` (count ≥ goal) and `progress` (`min(count, goal)`) and `goal`. Negative counts are treated as 0.
- `next_badge(progress: list[dict]) -> dict | None` – the first badge not yet earned, or `None` if all are earned.

All counts are numbers of **different** place ids.

### Result page and route
- `GET /rooms/<id>/result` for a participant of a closed room with a Google winner: if this browser has no visit for this room, a form posting to `POST /rooms/<id>/visited` with the button `I was there ✓`; otherwise the text `In your collection ✓` and a link `My places`. Nothing for a manual winner, no winner, or a room that is not closed. Nothing about other participants' visits.
- `POST /rooms/<id>/visited`, checked in this order:

| Case | Status | Message | Saved |
|---|---|---|---|
| unknown room | 404 | – | nothing |
| not joined | 403 | `Please join the room first.` | nothing |
| room not `closed` | 400 | `You can collect the place once the group has decided.` | nothing |
| no winner | 400 | `There is no place to collect in this room.` | nothing |
| winner is a manual option | 400 | `Only places from Google Maps can be collected.` | nothing |
| this browser already has a visit for this room | 303 redirect to the result page (**ignored**) | – | nothing |
| valid | 303 redirect to the result page | – | one visit: person token (created now if missing), the winner's place id, room id, the room's group id from `group_rooms` (A9) or NULL, `from_surprise` = room mode is `surprise` |

Error pages are the result page with the message (`role="alert"`). Two presses at once: the unique constraint lets only one insert win; the other is ignored the same way.

### "My places" page (`GET /places`, template `places.html`)
- Header link `My places` next to `My rooms` (A8) on every page.
- Without a person token or without visits: `You have not collected any places yet. After your next decision, press "I was there ✓" on the result page.` and every badge as not earned.
- Otherwise: `You have collected <n> places` (`1 place` for one), the next badge with its progress (e.g. `Explorer: 7 / 10`), all badges (earned ones marked), and cards (C2b `build_card`/the card macro) for the **20 most recently collected** different places, newest first, with the date. If Google fails or no key is set, the cards show `Place from Google Maps` and the page still works (C2b behaviour).
- **Photo proxy** (`/photo/...`): a place in this person's visits is also allowed, so photos work after the room is deleted.

### `app/db.py`
New: `add_visit(person_token, place_id, room_id, group_id, from_surprise) -> bool` (False if the unique constraint refuses it), `has_visit(person_token, room_id) -> bool`, `get_visited_places(person_token, limit) -> list` (different place ids, newest visit first, with the date), `count_visited_places(person_token) -> dict` (`places`, `surprise`, `group`), `person_has_visited(person_token, place_id) -> bool`.

Checks (one line = one test):

`tests/test_collection.py`
- [ ] `badge_progress` with all counts 0: no badge earned, every progress 0.
- [ ] `badge_progress(1, 0, 0)`: only "First place" earned; "Regular" shows 1 / 5.
- [ ] `badge_progress` at exactly the goal earns the badge; above the goal the progress stays at the goal.
- [ ] Surprise and group badges use only their own counts.
- [ ] Negative counts are treated as 0.
- [ ] `next_badge` returns the first not-earned badge in table order, and `None` when all are earned.

`tests/test_collection_route.py` (Google always faked)
- [ ] The result page of a closed room with a Google winner shows the `I was there ✓` form to a participant.
- [ ] No form for a manual winner, for a room without winner, for a room that is still voting, and nothing for a visitor.
- [ ] Accepted: pressing it stores one visit with the winner's place id, the room id, `group_id` NULL for a normal room, `from_surprise` 0; the result page then shows `In your collection ✓` and the `My places` link.
- [ ] Accepted: in a group room (`group_rooms` row) `group_id` is that group; in a "Surprise me" room `from_surprise` is 1.
- [ ] Accepted: the first press creates a person token in the session; a second room uses the same token.
- [ ] Ignored: pressing again for the same room redirects and stores nothing new.
- [ ] Rejected: room not closed, no winner, manual winner – status 400, message, nothing saved.
- [ ] Rejected: a visitor and a participant of another room – 403, nothing saved; unknown room – 404.
- [ ] Privacy: another participant of the same room still sees the button (one person's visit is not shown to others), and nothing on any page says who collected what.
- [ ] "My places" in a new browser: the empty text and all badges not earned.
- [ ] "My places" after collecting two different places and the first one again from another room: `You have collected 2 places`, "First place" earned, `Regular: 2 / 5`, two cards, newest first.
- [ ] "My places" shows at most 20 cards even with more places, and the count is still the full number.
- [ ] "My places" with a Google error or no key: the page loads with the count, badges and `Place from Google Maps` cards.
- [ ] Another browser's "My places" shows none of these places.
- [ ] Photo proxy: a photo of a collected place loads after its room was deleted; a photo of a place the browser never collected and is in no joined room gives 404.
- [ ] Security: the API key and the person token never appear in a page.
- [ ] Persistence: after an app restart and after the room is deleted, the place is still in "My places".

## Out of scope
- The map (C8), the group's places on the group page (C8).
- Removing a place from the collection, collecting without a decision (e.g. any place by name), collecting manual options.
- Moving the collection to another phone, sharing it, leaderboards, comparing with friends.
- Storing names, types, locations or anything else from Google.
- The cleanup command (visits deleted after 180 days, D15; planned, not built yet).
- JavaScript, changes to existing tests.

## Done when
- All tests in both test files and all earlier tests pass (`uv run pytest`), output pasted.
- On the deployed app with a real key: close a room with a Google winner, press `I was there ✓`, open "My places" → the place card with photo and the "First place" badge.
- Work is on branch `feature-c7-collect-places`, pushed, pull request opened; Track A reviews the schema change.
