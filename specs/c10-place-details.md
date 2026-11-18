# C10 – F30 Place details: kind and rating count on every card, reviews and more on the back of the rating card

Branch: `feature-c10-place-details`
Tests: `tests/test_place_details_back.py` (reading the new Google fields, with fake answers) and `tests/test_rating_card_back.py` (cards, rating page, swipe script)

Decision: `docs/decisions.md`, D19. Builds on C2b (`build_card`, `load_cards`, the `place_card` macro), C2c (one card per rating step, one Place Details call for it) and A10 (`swipe.js`, `data-swipe-card`, `data-swipe-area`, the menu link). All three are merged.

## Why
A Google suggestion today shows a name, one photo and "4.5 ★ · €€ · 330 m"; people often cannot tell what kind of place it is or whether it is any good, so they rate blindly. The card must say what the place is and how many people rated it, and on demand show reviews, a summary, what the place offers and more photos, without making every page more expensive and without storing anything from Google.

## What

### Decisions in this spec (please check in the review)
- **Two levels of detail:**
  - **Front** (every Google card, everywhere it is shown today: room page, rating page, overview, result): the kind of place and the number of ratings. These fields come with the call every card already makes.
  - **Back** (only the one card on the rating page, `next_option`): summary, reviews, "offers", more photos. These fields are in Google's most expensive Place Details tier, so they are requested only there, **in the same single call** as the front (C2c's "one call per rating step" stays).
- **Turning the card without JavaScript:** a checkbox with the `hidden` attribute and two `<label>`s (`More about this place` on the front, `Back to the card` on the back) switch the sides with CSS (`:checked ~`). With JavaScript, `swipe.js` also turns the card on a **tap**: a pointer that goes up after moving less than `TAP_DISTANCE = 10` px clicks the checkbox. A drag of 110 px or more still rates (A10), anything in between springs back as before.
- **The labels sit outside `data-swipe-area`**, because `swipe.js` captures the pointer inside it, so a label there would not receive the tap.
- **Swiping only on the front:** the back has no `data-swipe-area`, so its text can be read and scrolled. The rating buttons stay below the card and work on both sides.
- **No animation in C10:** the sides switch instantly (`display: none` / `block`). The 3D flip and the look of both sides are done in the design phase (D19). Because the back is `display: none` until it is turned, its photos with `loading="lazy"` are not loaded before someone looks (no photo cost for cards nobody turns). The design phase must keep this.
- **Language:** every details request sends `languageCode=en` (the app is in English), so the kind reads "Italian Restaurant". Reviews are shown in the language Google sends them.
- **What is shown on the back, in this order, each part only if Google sent it:**
  1. **Summary:** Google's review summary (`reviewSummary.text.text`) with its disclosure text (`reviewSummary.disclosureText.text`, e.g. "Summarized with Gemini") right below it; if there is none, the editorial summary (`editorialSummary.text`). At most one of them.
  2. **Offers:** short labels for every "serves"/feature field that is `true`, in this fixed order: `Breakfast` (`servesBreakfast`), `Brunch`, `Lunch`, `Dinner`, `Vegetarian` (`servesVegetarianFood`), `Coffee`, `Dessert`, `Beer`, `Wine`, `Cocktails`, `Good for groups` (`goodForGroups`), `Outdoor seating` (`outdoorSeating`), `Reservations` (`reservable`), joined with ` · `. `false` or missing fields are left out.
  3. **Reviews:** at most `MAX_REVIEWS_SHOWN = 3`, in Google's order (Google picks the most relevant, not the newest; the page says `Reviews selected by Google`). Each: stars (`rating`, e.g. `5 ★`), age (`relativePublishTimeDescription`, e.g. `2 weeks ago`), the full text (`text.text`, unchanged, not cut), and the author (`authorAttribution.displayName`) as a link to `authorAttribution.uri` (`target="_blank" rel="noopener noreferrer"`). A review without text is skipped.
  4. **More photos:** the 2nd to 4th photo (`MAX_EXTRA_PHOTOS = 3`) through the existing `/photo/...` proxy, each with its author attribution as on the front.
  5. **The A10 link** `Menu & reviews on Google Maps`.
  If none of 1–4 exists: `Google has no more details for this place.` and the link.
- **Manual options** have no back and no labels (nothing to show). A Google card whose details failed (`details_missing`) has no back either.
- **Nothing is stored**, also not the reviews (Google terms, AGENTS.md). The API key never appears in the page.

### Google calls (`app/services/places.py`)
- `DETAILS_FIELD_MASK` gets `primaryTypeDisplayName,userRatingCount`: `displayName,rating,userRatingCount,priceLevel,location,photos,primaryTypeDisplayName`.
- New `BACK_FIELD_MASK` = `DETAILS_FIELD_MASK` + `reviews,reviewSummary,editorialSummary,servesBreakfast,servesBrunch,servesLunch,servesDinner,servesVegetarianFood,servesCoffee,servesDessert,servesBeer,servesWine,servesCocktails,goodForGroups,outdoorSeating,reservable`. Never `*`.
  **Note for the implementer:** check each field name against Google's Place Details (New) field list before building; drop one that does not exist and name it in the pull request (e.g. if `reviewSummary` is not available for the API version or region, the editorial summary alone is used).
- `get_place_details(api_key, place_id, with_back: bool = False)` uses `BACK_FIELD_MASK` when `with_back` is true, `DETAILS_FIELD_MASK` otherwise; both with `languageCode=en`. Everything else (timeout 5 s, errors) unchanged.
- `read_details` also reads `kind` (`primaryTypeDisplayName.text` or `None`) and `rating_count` (a non-negative int or `None`), and, only when the back fields are present, `back`: `{"summary", "summary_disclosure", "offers": [labels], "reviews": [{"stars", "age", "text", "author", "author_uri"}], "extra_photos": [{"name", "author", "author_uri"}]}`. Wrong types are ignored field by field, never an error (as C2b). An author URI that does not start with `https://` is dropped (only the name is shown). Extra photo names must match `PHOTO_NAME_PATTERN` and belong to the same place, otherwise they are skipped.
- `build_card` adds `kind` and changes `rating_text`: with a rating count, `4.5 ★ (812)`; **without one, exactly as today** (`4.5 ★`). It adds `back` when `read_details` returned one.
- `load_cards(..., back_for: set[str] | None = None)`: place ids in `back_for` are loaded with `with_back=True`. Default unchanged.
- The rating route passes `back_for = {place id of next_option}` (only in the one-card view). Overview, room page and result page do not pass it.

### Templates
- `_place_card.html`: the kind as a line above the facts (`<p class="place-kind">Italian Restaurant</p>`), only if present. Room page, overview and result page get it automatically.
- `vote.html`, one-card view, for a Google card with `back`:
  - inside `article[data-swipe-card]`: `<input type="checkbox" id="card-side-<option id>" data-flip-toggle hidden>`, then the front (`data-swipe-area`, unchanged), then `<label for="card-side-<option id>" data-flip-open>More about this place</label>` (outside the swipe area), then `<div data-card-back>` with the parts above and `<label for="…" data-flip-close>Back to the card</label>`, then the rating form (unchanged).
  - CSS: `[data-card-back]` hidden; `[data-flip-toggle]:checked ~ [data-swipe-area], [data-flip-toggle]:checked ~ [data-flip-open] { display: none; }` and `[data-flip-toggle]:checked ~ [data-card-back] { display: block; }`. The labels look like links or small buttons and are at least 44 px high (tap target).
- The menu link of A10 stays on the front as well.

### `app/static/js/swipe.js`
- New constant `TAP_DISTANCE = 10`. In `pointerup`: if the pointer moved less than `TAP_DISTANCE` in both directions and the card has a `[data-flip-toggle]`, click it and spring back; nothing is rated.
- Everything else unchanged; the file stays short and commented, and still contains none of `fetch(`, `XMLHttpRequest`, `import `, `http` (A10's static check).

Checks (one line = one test):

`tests/test_place_details_back.py` (`requests.get` always faked)
- [ ] `get_place_details` without `with_back` sends `DETAILS_FIELD_MASK` (with `primaryTypeDisplayName` and `userRatingCount`, without `reviews`) and `languageCode=en`.
- [ ] With `with_back=True` it sends `BACK_FIELD_MASK`, which contains `reviews`, `editorialSummary` and the serves fields and never `*`; still one call.
- [ ] `read_details` reads `kind` and `rating_count`; a missing or wrongly typed value gives `None`; a negative count gives `None`.
- [ ] `build_card`: with a count, `rating_text` is `4.5 ★ (812)`; without one, `4.5 ★` exactly as before; `kind` is passed through.
- [ ] Back: the review summary and its disclosure are read; without it, the editorial summary; without both, no summary.
- [ ] Back: offers contain only `true` fields, in the fixed order, with the labels above.
- [ ] Back: at most 3 reviews in Google's order; a review without text is skipped; stars, age, text, author and author URI are read; a non-`https://` URI is dropped, the name kept.
- [ ] Back: extra photos are the 2nd to 4th photo, at most 3, with authors; a photo name of another place or with a wrong format is skipped.
- [ ] Back: a damaged answer (wrong types everywhere) gives an empty back and never raises.
- [ ] `load_cards` with `back_for` loads exactly those places with the back mask and the others with the normal mask; still one call per Google option.

`tests/test_rating_card_back.py` (Google faked)
- [ ] Rating page, next option is a Google place with back details: one Place Details call, with the back mask; the page has the hidden `data-flip-toggle` checkbox, the `More about this place` label for it outside `data-swipe-area`, a `data-card-back` with the summary, offers, up to 3 reviews (stars, age, text, author link) and extra photo URLs through `/photo/`, the `Back to the card` label, and the rating buttons.
- [ ] A review summary is shown together with its disclosure text.
- [ ] A Google place without any back details shows `Google has no more details for this place.` and the menu link on the back.
- [ ] A manual option, and a Google option whose details failed, have no checkbox, no labels and no back.
- [ ] The overview, the room page and the result page make no call with the back mask and show no back; their cards show the kind and `4.5 ★ (812)`.
- [ ] Review text and author names with HTML are shown escaped.
- [ ] The API key never appears in the page; nothing new is written to the database.
- [ ] Rating from the one-card view still works (POST, redirect, vote saved), with the back open or closed.
- [ ] `swipe.js` contains `TAP_DISTANCE` and still passes A10's static check (no `fetch(`, `XMLHttpRequest`, `import `, `http`).
- [ ] All earlier tests pass unchanged (in particular C2b, C2c and A10: the rating text without a count is unchanged).

Manual checks (in the pull request, on the deployed app with a real key, on a phone):
- [ ] Tapping the card turns it to the back; tapping `Back to the card` turns it back; a swipe still rates.
- [ ] Without JavaScript, the labels turn the card.
- [ ] The extra photos are only requested after the card was turned (browser network list).
- [ ] A real restaurant shows its kind, rating count, reviews with author links and, where Google has it, a summary.

## Out of scope
- The 3D flip animation, colours and layout of both sides (design phase, D19).
- Backs on the room page, the overview or the result page; a separate details page.
- Opening hours, "open now", phone number, website, a full photo gallery, sorting reviews by date, translating reviews.
- Storing or caching any Google field, a server-side cache of backs.
- Changes to the voting rules, the order of cards, or other JavaScript files.
- Changes to existing tests.

## Done when
- All tests in both test files and all earlier tests pass (`uv run pytest`), output pasted.
- No test reaches the network (root `conftest.py`).
- The pull request names any Google field that had to be dropped and the price tier the back mask is billed in, with the free amount from Google's current price list.
- The manual checks above are done and written in the pull request.
- Work is on branch `feature-c10-place-details`, pushed, pull request opened for review.
