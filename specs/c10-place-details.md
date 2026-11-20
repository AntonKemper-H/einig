# C10 – F30 Place details: kind and rating count on every card, reviews and more on the back of the rating card

Branch: `feature-c10-place-details`
Tests: `tests/test_place_details_back.py` (field masks and reading the new Google fields, with fake answers) and `tests/test_rating_card_back.py` (cards, rating page, swipe script)

Decision: `docs/decisions.md`, D19. Builds on C2b (`get_place_details`, `read_details`, `build_card`, `load_cards`, the `place_card` macro), C2c (one card per rating step, one Place Details call for it) and A10 (`swipe.js`, `data-swipe-card`, `data-swipe-area`, the menu link). All three are merged.

## Why
A Google suggestion today shows a name, one photo and "4.5 ★ · €€ · 330 m"; people often cannot tell what kind of place it is or whether it is any good, so they rate blindly. The card must say what the place is and how many people rated it, and on demand show a description, reviews, what the place offers and more photos, without making every page more expensive, without storing anything from Google, and **without changing what any reviewed test pins**.

## What

### Reviewed tests this spec must keep true (checked on `main`, review of #62)
- `tests/test_place_details.py`: `DETAILS_FIELD_MASK` is exactly `displayName,rating,priceLevel,location,photos`; the default `get_place_details(api_key, place_id)` call goes to exactly `…/places/<id>` with that mask; its result has exactly the keys `name, rating, price_level, latitude, longitude, photo_name, photo_author, photo_author_uri`; `build_card` returns exactly the dicts in the tests (no extra keys) when Google sent no new fields.
- `tests/test_cards_vote_result.py`, `tests/test_place_cards.py`, `tests/test_winner_map.py`: `4.5 ★ · €€ · 330 m` and `4.5 ★` when Google sent no rating count.
- `tests/test_swipe_rating.py`: exactly **one** menu link per rating page (`menu_links(html) == [...]`), and `swipe.js` contains none of `fetch(`, `XMLHttpRequest`, `import `, `http` (also not in comments).
- The fake `requests.get` functions in the tests accept extra keyword arguments (`**kwargs`) and answer by URL, so a `params=` argument works with them; the URL itself must not change.

### Decisions in this spec (please check in the review)
- **Three field masks, the old one unchanged** (`app/services/places.py`):
  - `DETAILS_FIELD_MASK` stays `displayName,rating,priceLevel,location,photos` and stays the default of `get_place_details`.
  - New `CARD_FIELD_MASK = DETAILS_FIELD_MASK + ",userRatingCount,primaryTypeDisplayName"` – used by `load_cards` for every card.
  - New `BACK_FIELD_MASK = CARD_FIELD_MASK + ",editorialSummary,reviews,servesBreakfast,servesBrunch,servesLunch,servesDinner,servesVegetarianFood,servesCoffee,servesDessert,servesBeer,servesWine,servesCocktails,goodForGroups,outdoorSeating,reservable"` – used only for the one card on the rating page.
  - Never `*`. **Implementer:** check each field name against Google's Place Details (New) field list; drop one that does not exist and name it in the PR.
- **`get_place_details(api_key, place_id, field_mask: str = DETAILS_FIELD_MASK)`**: with the default, the request is exactly as today (same URL, headers and timeout, no `params`). With `CARD_FIELD_MASK` or `BACK_FIELD_MASK` it also sends `params={"languageCode": "en"}` (so the kind reads "Italian Restaurant"; reviews are shown in the language Google sends them). The URL never changes.
- **New keys only when Google sent them:** `read_details` adds `kind` (`primaryTypeDisplayName.text`), `rating_count` (a non-negative int) and `back` (see below) **only if** the answer contains them with a valid value. An answer without them gives exactly today's dict. `build_card` likewise adds `kind` and `back` only when present, and `rating_text` becomes `4.5 ★ (812)` only with a count; otherwise it is exactly as today.
- **Two levels of detail:**
  - **Front** (every Google card where `load_cards` is used: room page, rating page, overview, result): kind and rating count.
  - **Back** (only `next_option` on the rating page): description, offers, reviews, more photos. Same single call as the front (C2c's "one call per rating step" stays).
- **No AI review summary:** Google does not offer review summaries for Portugal, and showing one needs a "Review summary" heading, the disclosure text, a "Report summary", an "About this summary" and a "See reviews" link. The back uses Google's short description (`editorialSummary.text`) instead. Adding review summaries is out of scope.
- **What the back shows, in this order, each part only if Google sent it:**
  1. **Description:** `editorialSummary.text`.
  2. **Offers:** short labels for every field that is `true`, in this fixed order: `Breakfast` (`servesBreakfast`), `Brunch`, `Lunch`, `Dinner`, `Vegetarian` (`servesVegetarianFood`), `Coffee`, `Dessert`, `Beer`, `Wine`, `Cocktails`, `Good for groups` (`goodForGroups`), `Outdoor seating` (`outdoorSeating`), `Reservations` (`reservable`), joined with ` · `. `false` or missing fields are left out.
  3. **Reviews:** at most `MAX_REVIEWS_SHOWN = 3`, in Google's order, under the line `Reviews selected by Google`. Each review, as Google's terms require:
     - stars (`rating`, e.g. `5 ★`) and age (`relativePublishTimeDescription`, e.g. `2 weeks ago`);
     - the full text (`text.text`), **unchanged and not cut** (the design phase may fold long texts, but every word stays reachable);
     - the author: photo (`authorAttribution.photoUri`, `<img>` 32 × 32, `alt=""`, `loading="lazy"`, `referrerpolicy="no-referrer"`), name (`authorAttribution.displayName`) as a link to `authorAttribution.uri`;
     - a link `Read on Google Maps` to the review's `googleMapsUri`.
     All links `target="_blank" rel="noopener noreferrer"`. Any URI (author, photo, review) that does not start with `https://` is dropped; a review without text or without an author name is skipped.
  4. **More photos:** the 2nd to 4th photo (`MAX_EXTRA_PHOTOS = 3`) through the existing `/photo/...` proxy (it already allows photos of places in the browser's rooms), each with its author attribution as on the front. A photo name that does not match `PHOTO_NAME_PATTERN` or belongs to another place is skipped.
  If none of 1–4 exists: `Google has no more details for this place.`
- **The menu link is not repeated on the back.** It stays where A10 put it, below the swipe area and outside the back, so it is visible on both sides and the page keeps exactly one menu link.
- **Turning the card without JavaScript:** a checkbox `<input type="checkbox" id="card-side-<option id>" data-flip-toggle class="visually-hidden">` (visually hidden with CSS but **focusable**, so keyboard users can turn the card with Tab and Space; not the `hidden` attribute) and two `<label for="card-side-<option id>">`s: `More about this place` (front) and `Back to the card` (back). CSS: `[data-card-back]` is hidden; `[data-flip-toggle]:checked ~ [data-swipe-area], [data-flip-toggle]:checked ~ [data-flip-open] { display: none; }`, `[data-flip-toggle]:checked ~ [data-card-back] { display: block; }`. The checkbox gets a visible focus outline on its labels: `[data-flip-toggle]:focus-visible ~ [data-flip-open]` and `[data-flip-toggle]:focus-visible ~ [data-card-back] [data-flip-close]` (the element right after the checkbox is the front, not a label). Labels are at least 44 px high.
- **The labels sit outside `data-swipe-area`**, because `swipe.js` captures the pointer inside it, so a label there would not receive the tap.
- **Turning with a tap (`swipe.js`):** new constant `TAP_DISTANCE = 10`. In `pointerup`, if the pointer moved less than `TAP_DISTANCE` in both directions and the card has a `[data-flip-toggle]`, the script clicks it and springs back; nothing is rated. **A touch that starts on a link** (`event.target.closest("a")`, e.g. the photo author link on the front) is left alone: no drag, no turn, the link works normally.
- **Swiping only on the front:** the back has no `data-swipe-area`, so its text can be read and scrolled. The rating buttons stay below the card and work on both sides.
- **No animation in C10:** the sides switch instantly. The 3D flip and the look of both sides are done in the design phase (D19). The back is `display: none` until it is turned, so its lazy photos and author pictures are not loaded before someone looks; the design phase must keep this.
- **Manual options** have no back, no checkbox and no labels. A Google card whose details failed (`details_missing`) has none either.
- **Nothing is stored**, also not the reviews (Google terms, AGENTS.md). The API key never appears in the page.

### Code
- `places.py`: the masks and `get_place_details` as above; `read_details` reads the new fields as above (wrong types ignored field by field, never an error, as C2b); `build_card` as above; `load_cards(..., back_for: set[str] | None = None)` loads every card with `CARD_FIELD_MASK`, and place ids in `back_for` with `BACK_FIELD_MASK`. `load_winner` (C3) is unchanged.
- The rating route passes `back_for = {place id of next_option}` (only in the one-card view). Overview, room page and result page do not pass it.
- `_place_card.html`: the kind as a line above the facts (`<p class="place-kind">Italian Restaurant</p>`), only if present.
- `vote.html`, one-card view, for a Google card with `back`, inside `article[data-swipe-card]` in this order: the checkbox, the front (`data-swipe-area`, unchanged), `<label … data-flip-open>More about this place</label>`, `<div data-card-back>` with the parts above and `<label … data-flip-close>Back to the card</label>`, the menu link (unchanged, A10), the rating form (unchanged).
- `swipe.js` as above; it stays short and commented and passes A10's static check.

Checks (one line = one test):

`tests/test_place_details_back.py` (`requests.get` always faked)
- [ ] `DETAILS_FIELD_MASK` is unchanged; `CARD_FIELD_MASK` is it plus `userRatingCount,primaryTypeDisplayName`; `BACK_FIELD_MASK` is `CARD_FIELD_MASK` plus the back fields; none contains `*`.
- [ ] `get_place_details` with the default mask sends no `params` and the same URL as before; with `CARD_FIELD_MASK` or `BACK_FIELD_MASK` it sends that mask, `params={"languageCode": "en"}` and the same URL; one call each.
- [ ] `read_details` with an answer without the new fields returns exactly today's keys; with them it adds `kind` and `rating_count`; a wrongly typed or negative count is left out.
- [ ] `build_card` with a count: `rating_text` is `4.5 ★ (812)` and `kind` is passed through; without the new fields the card dict is exactly today's.
- [ ] Back: the description comes from `editorialSummary.text`; without it, no description.
- [ ] Back: offers contain only `true` fields, in the fixed order, with the labels above.
- [ ] Back: at most 3 reviews in Google's order, each with stars, age, full text, author name, author link, author photo and the review's Google Maps link; a review without text or without author name is skipped; a non-`https://` URI is dropped and the rest kept.
- [ ] Back: extra photos are the 2nd to 4th photo, at most 3, with authors; a photo of another place or with a wrong name is skipped.
- [ ] Back: a damaged answer (wrong types everywhere) gives no `back` key or an empty back and never raises.
- [ ] `load_cards` uses `CARD_FIELD_MASK` for every card and `BACK_FIELD_MASK` only for the place ids in `back_for`; still one call per Google option.

`tests/test_rating_card_back.py` (Google faked)
- [ ] Rating page, next option is a Google place with back details: one Place Details call, with `BACK_FIELD_MASK`; the page has the `data-flip-toggle` checkbox (no `hidden` attribute), the `More about this place` label outside `data-swipe-area`, a `data-card-back` with description, offers, up to 3 reviews (stars, age, text, author photo and link, `Read on Google Maps` link) and extra photo URLs through `/photo/`, the `Back to the card` label, and the rating buttons.
- [ ] The rating page still has exactly one menu link, outside `data-card-back`.
- [ ] A Google place without any back details shows `Google has no more details for this place.` on the back.
- [ ] A manual option, and a Google option whose details failed, have no checkbox, no labels and no back.
- [ ] The overview, the room page and the result page make no call with `BACK_FIELD_MASK` and show no back; with a count and kind in the fake answer, their cards show `Italian Restaurant` and `4.5 ★ (812)`.
- [ ] Review text and author names with HTML are shown escaped.
- [ ] The API key never appears in the page; nothing new is written to the database.
- [ ] Rating from the one-card view still works (POST, redirect, vote saved).
- [ ] `swipe.js` contains `TAP_DISTANCE`, clicks `[data-flip-toggle]` on a tap, checks `closest("a")`, and still passes A10's static check.
- [ ] All earlier tests pass unchanged; no reviewed test is edited.

Manual checks (in the pull request, on the deployed app with a real key, on a phone):
- [ ] Tapping the card turns it to the back; tapping `Back to the card` turns it back; a swipe still rates; tapping the photo author link opens it and does not turn the card.
- [ ] With the keyboard (laptop): Tab reaches the turn control and Space turns the card.
- [ ] Without JavaScript, the labels turn the card.
- [ ] The extra photos and author pictures are only requested after the card was turned (browser network list).
- [ ] A real restaurant in Lisbon shows its kind, rating count, reviews with author and Google Maps links and, where Google has one, a description.

## Out of scope
- Google's AI review summary (`reviewSummary`), generative summaries.
- The 3D flip animation, colours and layout of both sides (design phase, D19).
- Backs on the room page, the overview or the result page; a separate details page.
- Opening hours, "open now", phone number, website, a full photo gallery, sorting reviews by date, translating reviews, a "report review" link.
- Storing or caching any Google field, a server-side cache of backs, a proxy for author pictures.
- Changes to the voting rules, the order of cards, `load_winner`, or other JavaScript files.
- Changes to existing tests.

## Done when
- All tests in both test files and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network (root `conftest.py`).
- The pull request names any Google field that had to be dropped, and the price tier and free amount (from Google's current price list) that `CARD_FIELD_MASK` and `BACK_FIELD_MASK` are billed in.
- The manual checks above are done and written in the pull request.
- Work is on branch `feature-c10-place-details`, pushed, pull request opened for review.
