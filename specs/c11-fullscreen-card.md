# C11 – F4/F30 Full-screen rating card with pages, joker by swiping down

Branch: `feature-c11-fullscreen-card`
Tests: `tests/test_fullscreen_card.py` (page structure, hidden buttons, joker question, script) – replaces the turning tests of `tests/test_rating_card_back.py` (list below)

Decision: `docs/decisions.md`, D20. Builds on C10 (details and back data), A10 (`swipe.js`), B4 (joker). **Starts only after C10 is merged.**

## Why
Testing C10 on a phone showed that turning the card makes the page long and confusing and that the buttons below take the space the card needs. The rating page should be one full-screen card you swipe away, like the swipe apps people know.

## What

### Layout
- On the one-card rating page the card fills the screen (`100dvh`) and the page does not scroll (`overflow: hidden` on this page only, set by a class on the page, not on every page). The overview, room page, lobby and result page are unchanged.
- Above or on the card a slim line shows `Option 2 of 5`. **Decision to check in the review:** the creator's `Close the room` button and the `Back to the lobby` link move into one small menu link in this line that opens a page where both are (the lobby, if it already has the close button; if not, the implementer says so in the PR before building).
- The place text and photo sizes are the design phase's business; C11 fixes only structure and behaviour.

### Pages of the card
- Three pages in this order inside `article[data-swipe-card]`, as a horizontal scroll container with CSS scroll snapping (`scroll-snap-type: x mandatory`): `[data-card-page="front"]` (the C10 front: name, first photo, kind, facts, the menu link), `[data-card-page="photos"]` (the extra photos with their authors), `[data-card-page="reviews"]` (description, offers, `Reviews selected by Google`, reviews, exactly as in C10).
- A page without content (no extra photos, no back details) shows `Google has no more details for this place.` (as C10) and keeps its dot, so the card always has three pages. A card without Google details and a manual option have **one page** and no dots.
- Inside a page, long content scrolls vertically inside the card (`overflow-y: auto`); the card does not move.
- Three dots in the bottom bar: `<a href="#card-page-<option id>-<name>" data-card-dot>` for each page, the current one marked `aria-current="true"` (set by `swipe.js` while scrolling; without JavaScript the first dot is marked). The links make the dots work with a click and without JavaScript. The dots have an accessible name (`Page 1 of 3: Front`).
- **The flip of C10 is removed:** no `[data-flip-toggle]`, no `[data-flip-open]`, no `[data-flip-close]`, no `[data-card-back]`, no `More about this place`, no `Back to the card`. The back data and the single details call of C10 (`BACK_FIELD_MASK`, one call per rating step) stay unchanged; `places.py` is not touched.
- The menu link (A10) stays on the front page, exactly one on the rating page.

### Two zones (so the gestures do not collide)
- **Page area** (`[data-card-pages]`): sideways swipe changes the page (the browser's scrolling does this, `touch-action: pan-x pan-y`); vertical movement scrolls the page. **No rating starts here.**
- **Grip** (`[data-swipe-area]`, the bottom bar with the name and the dots, the dots are links and keep working): the A10 gestures start here: right = `Rather yes`, up = `Fine with me`, left = `Rather not` (110 px, as A10), **down = joker**. `touch-action: none` on the grip only.
- The whole card (page area and grip together) moves and tilts with the finger while a grip gesture runs, as in A10.
- A tap on the grip does nothing (the C10 tap-to-turn is removed).

### Joker by swiping down
- A downward swipe of 110 px or more on the grip does **not** use the joker. It opens `[data-joker-question]`: the text `Use my joker on <place name>? This cannot be undone.` and two buttons, `Use joker` and `Cancel`. `Use joker` clicks the existing joker button (B4, unchanged); `Cancel` closes the question and puts the card back. Nothing is sent before `Use joker`.
- Only shown if the participant still has their joker (`own_veto is none`); otherwise a downward swipe only springs back.
- The question is inside the card's markup and hidden until opened (`hidden`), so the page has no new route and no new server code.

### The buttons stay, out of sight
- The rating form (three buttons) and the joker form stay in the page inside the card, **visually hidden but focusable** (not `display: none`, not the `hidden` attribute), and visible while one of them has the keyboard focus (`:focus-within`). So rating with the keyboard, with a screen reader and without JavaScript still works, and the routes, the forms and their fields are exactly as before.
- Tab order: the page dots, the menu link, then the rating buttons, then the joker button.

### Script (`swipe.js`, still short and commented)
- New constants and behaviour only for the grip, the dots (current page) and the joker question. It still contains none of `fetch(`, `XMLHttpRequest`, `import `, `http` (also not in comments). It only clicks buttons that are already on the page. `TAP_DISTANCE` and the `[data-flip-toggle]` code are removed.
- Without the script the page still works: dots change the page, hidden buttons rate.

### Tests of C10 this spec replaces (team approval needed in the spec review)
In `tests/test_rating_card_back.py`: `test_card_has_checkbox_labels_and_back`, `test_labels_sit_outside_the_swipe_area_and_the_open_label_outside_the_back`, `test_parts_of_the_card_come_in_the_specified_order`, `test_a_manual_option_has_no_checkbox_no_labels_and_no_back`, `test_a_google_option_whose_details_failed_has_no_checkbox_no_labels_and_no_back`, `test_the_rating_page_still_has_exactly_one_menu_link_outside_the_back`, `test_swipe_js_turns_the_card_on_a_short_tap_and_leaves_links_alone`, and the parts of the other back tests that look for `data-card-back`. Everything about the data (reviews, photos, offers, escaping, one call, other pages show the front only) stays true and is kept; the content tests are moved to the new page markers.

Checks (one line = one test), `tests/test_fullscreen_card.py` (Google faked):
- [ ] Rating page, next option a Google place with details: the card has three `data-card-page` sections in the order front, photos, reviews, with the C10 content in them (kind and facts, extra photos through `/photo/`, description, offers, up to 3 reviews with author and Google Maps links).
- [ ] Three dots as links to the three pages, the first with `aria-current="true"`, each with an accessible name; the dots sit in the grip.
- [ ] The grip is `data-swipe-area` and holds the name and the dots; the page area is outside it and has no `data-swipe-area`.
- [ ] A page without content shows `Google has no more details for this place.`; the card still has three dots.
- [ ] A manual option and a Google option whose details failed have one page and no dots.
- [ ] The three rating buttons and the joker button are in the card, still `button` elements with their names, **not** `display: none` and **without** the `hidden` attribute; the CSS hides them visually and shows them on `:focus-within` (CSS file checked).
- [ ] The joker question exists, is `hidden`, contains the place name, `Use joker` and `Cancel`, and is only present while the participant has their joker; sending nothing happens before the joker button is pressed (no vote, no joker saved by viewing the page).
- [ ] Exactly one menu link, on the front page.
- [ ] No `data-flip-toggle`, `data-flip-open`, `data-flip-close`, `data-card-back`, `More about this place` or `Back to the card` anywhere.
- [ ] The page has the class that stops page scrolling on the rating page only; the overview, room page, lobby and result page do not have it.
- [ ] The close room button (creator only) and the lobby link stay reachable from the rating page; a non-creator never sees the close button.
- [ ] Rating by the form still works (POST, redirect, vote saved) and the joker form still works (one joker per participant and room, second attempt rejected).
- [ ] One Place Details call with `BACK_FIELD_MASK` per rating step; the API key never appears in the page; viewing writes nothing.
- [ ] `swipe.js`: contains the 110 px distance, the joker question handling and the dot handling, no `TAP_DISTANCE`, no `data-flip-toggle`, and passes A10's static check.
- [ ] All other earlier tests pass unchanged.

Manual checks (in the pull request, on the deployed app with a real key, on a phone):
- [ ] The card fills the screen, the page does not scroll; sideways swipe in the photo/text area changes the page, the dots follow.
- [ ] A long review list scrolls inside the card; the card stays.
- [ ] Right, up and left on the bottom bar rate; down opens the joker question; `Cancel` puts the card back; `Use joker` uses it.
- [ ] With a mouse on a laptop: dragging the bottom bar rates; clicking a dot changes the page.
- [ ] With the keyboard: Tab reaches the dots, the menu link and the (now visible) buttons.
- [ ] The creator can still close the room; everyone can reach the lobby.

## Out of scope
- Looks: colours, fonts, the fly-out animation, the card shadow (design phase).
- The overview, the result page, the room page.
- Changes to scoring, voting rules, routes, the database, or the Google calls.
- A new JavaScript file or any library.
- Moving the rating buttons to another screen or removing them from the page.

## Done when
- All tests in `tests/test_fullscreen_card.py` and all earlier tests pass (`uv run pytest`), output pasted; the replaced C10 tests are exactly the ones listed above.
- The manual checks above are done and written in the pull request.
- Work is on branch `feature-c11-fullscreen-card`, pushed, pull request opened for review.
