# C2c – F8 Place cards on the rating page and real names on the result page

Branch: `feature-c2c-cards-on-vote-and-result`
Tests: `tests/test_cards_vote_result.py`

Track C follow-up to C2b (`specs/c2b-place-cards.md`, "Out of scope": cards on the rating page). Builds on B2 (`specs/b2-rating.md`), B3 (`specs/b3-result.md`) and C3 (`specs/c3-winner-map.md`).

## Why
On the rating page every Google option still reads "Place from Google Maps", so in a "Places nearby" room nobody knows what they are rating. The result page's count list ("How the options were rated") has the same problem. Each Google option must show its real name (and on the rating page the whole card), while Google is called as rarely as possible, because every Place Details call counts against the quota.

## What
Cost rule for this task: **at most one Place Details call per Google option that is actually shown, per page view.** Neither the rating page nor the result page has a meta refresh (only the lobby has one, and the lobby shows no option names), so calls only happen when someone opens, reloads or submits a page.

### Rating page (`GET /rooms/<room_id>/vote`, and the page shown again after a rejected vote)

- `db.get_rateable_options` also returns `source` and `place_id` (still only options with `is_replaced = 0`, ordered by id).
- **One card at a time** (the next unrated option): only **this one option** is loaded with `places.load_cards` (the room's search centre gives the distance). So a rating step costs at most one call, however many options the room has.
- **Overview** (every option rated, "You have rated all options."): every rateable option is shown, so `load_cards` is called once with all of them, in the participant's order: one call per Google option.
- A Google option is shown with the `place_card` macro from `app/templates/_place_card.html` (name, photo through `/photo/…`, rating · price · distance, `Google Maps`; or the fallback `Place from Google Maps` + `Details are not available right now.`). A manual option keeps its `<h2>` label. The rating buttons, the hidden `option_id`, "Option 2 of 5" and "Your rating: …" stay exactly as in B2.
- No card is shown, so Google is **not** called, when the room is `collecting` or `closed`, or when there are no options to rate.
- All C2b rules carry over through `load_cards`: no key → fallback without calls; an error for one place → only that card falls back; after the first `PlacesUnavailable` (timeout / no connection) no further calls on this page view.
- `GOOGLE_OPTION_LABEL` is no longer used by the rating page.

### Result page (`GET /rooms/<room_id>/result`)

- While the room is not `closed`, nothing is loaded from Google (as today: the page only says the result comes later).
- When `closed`: the count list "How the options were rated" shows each Google option's **name** from `load_cards` (fallback `Place from Google Maps` if its details are missing). Only the name, no photo or facts, so the list stays short and loads no photos. Manual options keep their label.
- `load_cards` is called **once** for all rateable options (no centre: B3 deletes it when the room closes, so there is no distance). The winner's card is taken from these cards instead of being loaded a second time:
  - `places.load_winner(api_key, embed_key, option, card=None)` gets an optional `card`. If a card is passed, Google is not called and that card is used; map and route URLs are built as before (C3). Without `card` it works exactly as in C3.
  - So a closed room with *n* Google options costs exactly *n* Place Details calls per view (plus the map, which the browser loads with the embed key).
- The heading "The group's choice: …" and the C3 card/map/route stay as they are.
- `GOOGLE_OPTION_LABEL` is no longer used by the result page.

### Unchanged
- Lobby, room page, voting rules, privacy (only anonymous counts), scoring.
- Nothing from Google is stored. The API key never appears in a page.

Checks (one line = one test):

Rating page:
- [ ] One card at a time, next option is a Google place: the page shows its name, the photo `<img src="/photo/places/<id>/photos/…"`, `4.5 ★ · €€ · 330 m`, `Google Maps`, the three rating buttons and the hidden `option_id`; Google was called **once**, for exactly this place.
- [ ] One card at a time, next option is a manual option: its label in `<h2>`, Google not called.
- [ ] Overview (all rated): every option is shown (Google names and manual label), each with "Your rating: …"; one Details call per Google option.
- [ ] Overview, Google times out on the first place: page loads (200), Google called once, every Google option shows the fallback exactly once.
- [ ] Details fail for the shown place: `Place from Google Maps` exactly once and `Details are not available right now.`, rating buttons still there.
- [ ] No API key: fallback, Google not called.
- [ ] Room `collecting` or `closed`: the rating page does not call Google.
- [ ] A Google name with HTML is shown escaped.
- [ ] The API key never appears in the rating page.
- [ ] A rejected vote (e.g. `rating=maybe` for a Google option) shows the page again with status 400, the message, the card's name, and exactly one Details call; nothing is saved (added after review of #36).
- [ ] Rating a Google option still works (POST redirects, the vote is saved) and the next page view again calls Google at most once.

Result page:
- [ ] Closed room with two Google options (one is the winner) and one manual option: the count list shows both real names and the manual label; the winner heading shows the winner's name; Details called **exactly once per Google option** (the winner is not loaded twice).
- [ ] Details fail for one (non-winning) place: that entry in the count list reads `Place from Google Maps`, the other names are shown.
- [ ] No API key: count list and heading use the fallback, Google not called.
- [ ] Google times out on the first place: page loads (200), Google called once, the winner's route link is still there.
- [ ] Room not closed: the result page does not call Google.
- [ ] The count list shows only names: no `/photo/` image for non-winning places.
- [ ] A Google name with HTML is shown escaped in the count list.
- [ ] `places.load_winner(..., card=card)` does not call Google and returns that card with the C3 map and route URLs; without `card` it still loads the details (C3 behaviour).

## Out of scope
- Cards or names in the lobby (it only shows counts; it has the meta refresh, so loading names there would multiply the calls).
- Caching details (Google terms, decided in C2b).
- Photos or facts in the result page's count list.
- Changing the rating rules, the order of the cards, or the result calculation.
- Changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_cards_vote_result.py` and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network (root `conftest.py`).
- Google calls only in `app/services/places.py`, SQL only in `app/db.py`, thin routes, Jinja templates, no JavaScript.
- Work is on branch `feature-c2c-cards-on-vote-and-result`, pushed, pull request opened with Timonhio as reviewer (B2/B3 owner).
