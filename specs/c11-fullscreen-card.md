# C11 – F4/F30 Full-screen rating card: swipe on the front, pages on the back, joker by swiping down

Branch: `feature-c11-fullscreen-card`
Tests: `tests/test_fullscreen_card.py` (layout, pages on the back, hidden buttons, joker question, script)

Decision: `docs/decisions.md`, D20. Builds on C10 (turning of the card, details and back data), A10 (`swipe.js`), B4 (joker). **Starts only after C10 is merged.**

## Why
Testing C10 on a phone showed that the page gets long and confusing and that the buttons below the card take the space the card needs. The rating page should be one full-screen card you swipe away, like the swipe apps people know.

## What

### Layout
- On the one-card rating page the card fills the screen (`100dvh`) and the page does not scroll (`overflow: hidden` on this page only, set by a class on the page, not on every page). The overview, room page, lobby and result page are unchanged.
- A slim line shows `Option 2 of 5`. **Decision to check in the review:** the creator's `Close the room` button and the `Back to the lobby` link move into one small menu in this line. The lobby has no close button, so it is a `<details>` menu on the rating page itself (no new page, no new route): the lobby link, the creator's close button and the note about a used joker.
- Colours, fonts and animations are the design phase's business; C11 fixes only structure and behaviour.

### Front and back (the turning of C10 stays)
- The checkbox `[data-flip-toggle]`, the labels `[data-flip-open]` (`More about this place`) and `[data-flip-close]` (`Back to the card`) and the details call of C10 stay as they are, including without JavaScript. Both labels stay in the page (visible as a small hint line, not part of the swipe zone).
- **Front** (`[data-swipe-area]`, the whole front): name, first photo, kind, facts. **Swiping to rate works here only.** A tap on the front turns the card (C10, `TAP_DISTANCE = 10`); a touch that starts on a link is left alone.
- **Back** (`[data-card-back]`, no swipe area): **no rating gestures**. A tap on a free part of the back (not on a link, a dot or a button) turns the card back to the front; a movement of `TAP_DISTANCE` or more is no tap.
- The back has **three pages** as a horizontal scroll container with CSS scroll snapping (`scroll-snap-type: x mandatory`), in this order:
  1. `[data-card-page="about"]`: description, offers and the one menu link (`Menu & reviews on Google Maps`);
  2. `[data-card-page="photos"]`: the extra photos with their authors;
  3. `[data-card-page="reviews"]`: `Reviews selected by Google` and the reviews, exactly as in C10.
- A page without content shows `Google has no more details for this place.` and keeps its dot: the back always has three pages. Inside a page, long content scrolls inside the card (`overflow-y: auto`).
- Three dots at the bottom of the back: `<a href="#card-page-<option id>-<name>" data-card-dot>`, the current one `aria-current="true"` (set by `swipe.js` while scrolling; without JavaScript the first one), each with an accessible name (`Page 1 of 3: About`). Without JavaScript and with a mouse, a click on a dot changes the page.
- The back keeps `BACK_FIELD_MASK`, one details call per rating step and no storing (C10). `places.py` is not touched.
- A manual option and a Google card without details have no back (as C10): they have only the front and are swiped like any card.

### Rating on the front
- Right, up and left (110 px, as A10) press the matching hidden button; **down** is the joker (below). The card moves and tilts with the finger as in A10.

### Joker by swiping down
- A downward swipe of 110 px or more on the front does **not** use the joker. It opens `[data-joker-question]`: `Use my joker on <place name>? This cannot be undone.` with the buttons `Use joker` and `Cancel`. `Use joker` clicks the existing joker button (B4, unchanged); `Cancel` closes the question and puts the card back. Nothing is sent before `Use joker`.
- Only offered while the participant still has their joker (`own_veto is none`); otherwise a downward swipe only springs back.
- The question is in the card's markup and `hidden` until opened: no new route, no new server code.

### The buttons stay, out of sight
- The rating form (three buttons) and the joker form stay in the page, **visually hidden but focusable** (not `display: none`, not the `hidden` attribute), and visible while one of them has the keyboard focus (`:focus-within`). The routes, the forms and their fields are exactly as before. **They are hidden only once `swipe.js` has started**: it adds the class `swipe-ready` to the card, and the CSS hides the buttons only under `[data-swipe-card].swipe-ready`. Without JavaScript (or when the script fails to load) the buttons stay visible, so a phone user can still rate (D16). Turning works with the labels.
- Tab order: the front labels, the menu link, the dots (when the back is open), then the rating buttons, then the joker button.

### Script (`swipe.js`, still short and commented)
- Adds: the tap on the back, the joker question, the current-dot marker. Still none of `fetch(`, `XMLHttpRequest`, `import `, `http` (also not in comments); it only clicks buttons that are already on the page.

### Code (where things are after C10, `main`)
- `app/templates/vote.html`, one-card view: `article[data-swipe-card]` holds, in this order, the checkbox `[data-flip-toggle]` (only for a Google card with details, `has_back`), `div[data-swipe-area]` (the front, built by the `place_card` macro), the label `[data-flip-open]`, the back (macro `place_card_back` in `_place_card.html`, `div[data-card-back]` with the label `[data-flip-close]`), the menu link, `rating_form`, `joker_form`. The page also has `<p data-swipe-hint>` and `Option N of M` above the card, and the creator's close button and the lobby link below.
- `app/templates/_place_card.html`: `place_card` (front) and `place_card_back` (back: description, offers, reviews, extra photos). C11 splits the back into the three `data-card-page` sections here and moves the menu link into `about`.
- `app/static/css/app.css`: `.visually-hidden`, the `[data-flip-toggle]:checked ~ …` rules, the focus outlines, `.place-kind`, and the A10 swipe rules (`[data-swipe-choice]`). The Pico classless CSS makes every `button[type=submit]` full width: the hidden-button rules must beat it.
- `app/static/js/swipe.js`: `SWIPE_DISTANCE = 110`, `TAP_DISTANCE = 10`, `choiceFor(dx, dy)`, `moveCard`, `springBack`, pointer events on the swipe area; a touch that starts on a link is ignored; `done` stops a second rating. C11 adds the downward joker question, the tap on the back and the current-dot marker here.
- `app/routes/rooms.py` `render_vote_page`: loads the one next card with `back_for`; already passes `own_veto`, `menu_url`, `cards`, `next_option`. C11 needs no new route and no new database access.
- The joker form is `joker_form(option_id)` in `vote.html` (no `name="rating"`, so the A10 script can never press it by mistake); it exists only while `own_veto is none`.
- Tests to reuse as models: `tests/test_rating_card_back.py` (HTML helpers `ElementFinder`, `tags`, fake Google with `back_answer()`), `tests/test_swipe_rating.py`, `tests/test_joker.py`.

### How to start and check (for the agent building C11, also in a new chat)
1. Read `AGENTS.md`, `docs/decisions.md` D16, D19, D20 and this spec. Check that PR #72 (this spec) is merged; start from `main` on `feature-c11-fullscreen-card`.
2. Tests first (`tests/test_fullscreen_card.py` plus the listed C10 test changes, each change named), stop for the team's review, then build. Never edit other reviewed tests.
3. There is no `.env` on the checkout and agents never create one: to look at the page, run a small throwaway server with a faked `requests.get` (copy the fake from `tests/test_rating_card_back.py`), outside the repository; to check with real Google data, the team deploys the branch on Render (Settings → Branch, then Manual Deploy) and tests on a phone. After the test the branch is set back to `main`.
4. CSS scroll snapping, `100dvh` and pointer events behave differently on phones and laptops: the manual checks on a phone are part of "done".

### C10 tests this spec changes (team approval needed in the spec review)
- `test_a_manual_option_...` and the tests about the back stay true. Changed: the order test (`test_parts_of_the_card_come_in_the_specified_order`: the menu link moves into the back, so the menu-link tests `test_the_rating_page_still_has_exactly_one_menu_link_outside_the_back` and the back-content tests move to the `about` page) and `test_swipe_js_turns_the_card_on_a_short_tap_and_leaves_links_alone` (a tap on the back also turns it back). The spec's author lists the exact lines in the PR. Everything about data, escaping, one call and the other pages stays.

Checks (one line = one test), `tests/test_fullscreen_card.py` (Google faked):
- [ ] The back has three `data-card-page` sections in the order about, photos, reviews with the C10 content in them (description, offers, menu link / extra photos through `/photo/` / reviews with author and Google Maps links).
- [ ] Three dots as links to the three pages inside the back, the first `aria-current="true"`, each with an accessible name.
- [ ] A page without content shows `Google has no more details for this place.`; the back still has three dots.
- [ ] Exactly one menu link on the rating page, on the `about` page.
- [ ] The front is the only `data-swipe-area`; the back has none and no rating buttons inside it.
- [ ] The three rating buttons and the joker button are in the card, still `button` elements, **not** `display: none` and **without** the `hidden` attribute; the CSS hides them visually and shows them on `:focus-within` (CSS file checked).
- [ ] The joker question exists, is `hidden`, contains the place name, `Use joker` and `Cancel`, and only while the participant has their joker; viewing the page saves no vote and no joker.
- [ ] A manual option and a Google option whose details failed have no back and no dots.
- [ ] The page has the class that stops page scrolling on the rating page only; the overview, room page, lobby and result page do not.
- [ ] The close room button (creator only) and the lobby link stay reachable from the rating page; a non-creator never sees the close button.
- [ ] Rating by the form still works (POST, redirect, vote saved); the joker form still works (one joker per participant and room, a second attempt is rejected).
- [ ] One Place Details call with `BACK_FIELD_MASK` per rating step; the API key never appears in the page; viewing writes nothing.
- [ ] `swipe.js` contains the joker question handling, the dot handling and the tap on the back, and passes A10's static check.
- [ ] All other earlier tests pass unchanged, except the C10 tests listed above.

Manual checks (in the pull request, on the deployed app with a real key, on a phone):
- [ ] The card fills the screen, the page does not scroll.
- [ ] On the front: right, up and left rate; down opens the joker question; `Cancel` puts the card back; `Use joker` uses it; a tap turns the card.
- [ ] On the back: swiping sideways changes the page and the dots follow; long reviews scroll inside the card; swiping does not rate; a tap on a free spot turns the card back; links still open.
- [ ] With a mouse on a laptop: dragging the front rates; clicking a dot changes the page.
- [ ] With the keyboard: Tab reaches the labels, the dots, the menu link and the (now visible) buttons.
- [ ] The creator can still close the room; everyone can reach the lobby.

## Out of scope
- Looks: colours, fonts, the 3D flip and fly-out animation, shadows (design phase).
- The overview, the result page, the room page.
- Changes to scoring, voting rules, routes, the database, or the Google calls.
- A new JavaScript file or any library.
- Removing the rating buttons from the page.

## Done when
- All tests in `tests/test_fullscreen_card.py` and all earlier tests pass (`uv run pytest`), output pasted; only the C10 tests listed above changed.
- The manual checks above are done and written in the pull request.
- Work is on branch `feature-c11-fullscreen-card`, pushed, pull request opened for review.
