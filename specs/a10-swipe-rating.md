# A10 – F4 Swipe to rate, and a menu link on the rating card

Branch: `feature-a10-swipe-rating`
Tests: `tests/test_swipe_rating.py`

Decision: `docs/decisions.md`, D16. Built after **C2c** (`specs/c2c-cards-vote-result.md`, place cards on the rating page) is merged. Builds on B2 (`specs/b2-rating.md`): one form per card, a hidden `option_id`, three submit buttons `name="rating"` with the values `yes`, `ok`, `no`.

## Why
Rating a stack of place cards feels natural as a swipe, like the apps people already know, and it makes the demo more fun. The swipe must only be a faster way to press a button that is already there, so the voting rules, the privacy of votes and the server tests stay exactly as they are, and the page still works without JavaScript.

## What

### Decisions in this spec (please check in the review)
- **Progressive enhancement:** the page is complete without the script. `swipe.js` adds the gesture and, when a swipe counts, calls `.click()` on the matching existing button. It sends nothing itself (no `fetch`, no `XMLHttpRequest`, no new form fields); the normal POST and Post/Redirect/Get do the rest.
- **Directions:** right → `yes` ("Rather yes"), up → `ok` ("Fine with me"), left → `no` ("Rather not"). Down does nothing (the card springs back), so scrolling down by accident never rates.
- **When a swipe counts:** the finger is let go with the card moved at least `SWIPE_DISTANCE = 110` px (constant at the top of the file) in that direction, and that direction is clearly the main one (more than the other axis). Otherwise the card springs back to its place and nothing is sent. A quick flick that ends below the distance does not count (simple rule, easy to explain).
- **Feedback while dragging:** the card moves and tilts slightly with the finger, and a label on the card shows the rating it would give (`Rather yes` green, `Fine with me` grey/blue, `Rather not` red). Colours and the label live in CSS; the script only sets one attribute (`data-swipe-choice="yes|ok|no"`, removed when below the distance) and the `transform`.
- **Only on one card:** the gesture is active only on the rating page's single card (the next unrated option), not on the overview where all options are listed, not on the room page, the lobby or the result page.
- **What can be dragged:** only the place area of the card (name, photo, facts), marked with `data-swipe-area`; the form with the three buttons below it is not part of it. Pressing a button or a link starts no drag, so taps keep working. Only the place area sets `touch-action: none` (the browser does not scroll while dragging it); a finger that starts on the buttons or anywhere else scrolls the page normally, which matters on small phones where the card is taller than the screen.
- **Manual options swipe too:** a manual option has no photo, but its card (the `<h2>` label) can be swiped in the same way.
- **One rating per gesture:** after a swipe counts, further gestures and clicks on that card are ignored until the next page has loaded (prevents a double submit).
- **Reduced motion:** with `prefers-reduced-motion: reduce` there is no fly-out animation; the button is pressed straight away.
- **Hint:** above the card, `Swipe right: Rather yes · up: Fine with me · left: Rather not`, in an element with the `hidden` attribute that the script removes. So the hint appears only where swiping actually works.
- **Menu link:** on the rating page, a Google option's card gets a link `Menu & reviews on Google Maps` (`target="_blank" rel="noopener noreferrer"`) to the place's Google Maps page. Built by a new `places.place_page_url(place_id: str, name: str) -> str | None`: `https://www.google.com/maps/search/?api=1&query=<name>&query_place_id=<place_id>` (URL-encoded), `None` for a place id that does not match `PLACE_ID_PATTERN` – the same pattern and style as C3's `route_url`. No key, no API call. The name is the card's `card["name"]`, as C3's `route_url` uses it; when the details failed this is the fallback `Place from Google Maps` (`FALLBACK_PLACE_NAME`), which is fine because the place id decides which place Google Maps opens. Shown also when the details failed; not shown for manual options. The `Google Maps` attribution of the C2b card stays.

### `app/static/js/swipe.js`
- Plain JavaScript, no library, at most about 100 lines, every block commented.
- Finds the element with `data-swipe-card` on the page; if there is none, it does nothing. Inside it, finds the three buttons by `button[name="rating"][value="yes|ok|no"]`.
- Uses Pointer Events (`pointerdown`, `pointermove`, `pointerup`, `pointercancel`) so it works with finger and mouse.
- Is loaded only by the rating page, with `<script src="…/js/swipe.js" defer>`.

### Template changes (`vote.html`, CSS)
- In the one-card-at-a-time view: the article gets `data-swipe-card`, the hint element (hidden by default) is added above it, and the script tag is added.
- The overview view gets none of these.
- CSS for the drag (label colours, tilt, spring back with a short transition, `touch-action: none` only on the `data-swipe-area`) goes into the existing stylesheet or the page's `<style>` block; no external files.
- The menu link is passed into the card from the rating route (or the card macro gets an optional `menu_url` argument, default `None`, so the room page is unchanged).

Checks (one line = one test), `tests/test_swipe_rating.py`:
- [ ] `app/static/js/swipe.js` exists and is served by the app (`GET /static/js/swipe.js` → 200, JavaScript content type).
- [ ] The rating page with a next card includes the `swipe.js` script tag, an element with `data-swipe-card` around the card, a `data-swipe-area` around the place part that does not contain the rating buttons, and the hint text with the `hidden` attribute.
- [ ] The three rating buttons with the values `yes`, `ok`, `no` and the hidden `option_id` are still inside the swipe card's form (the script needs them, and they work without it).
- [ ] The overview (all options rated) has no `data-swipe-card`, no hint and no `swipe.js`.
- [ ] Room page, lobby and result page do not include `swipe.js`.
- [ ] A rating sent the way the script sends it (the normal POST with `option_id` and `rating`) is saved and redirects, exactly as in B2.
- [ ] `swipe.js` contains none of the texts `fetch(`, `XMLHttpRequest`, `import ` or `http` (it only presses existing buttons; static check of the whole file text, so the comments must avoid these words too).
- [ ] `places.place_page_url` builds the documented URL with the encoded name and place id, and returns `None` for an invalid place id.
- [ ] The rating card of a Google option shows `Menu & reviews on Google Maps` linking to that URL, opening in a new tab with `rel="noopener noreferrer"`; when the details failed, the link is still there and uses `Place from Google Maps` as the name.
- [ ] A manual option's card has no menu link and still has `data-swipe-card`.
- [ ] Building the menu link does not call Google (the number of Place Details calls is the same as in C2c).
- [ ] The room page's place cards are unchanged (no menu link there).
- [ ] The rating page never shows other participants' ratings (unchanged privacy, checked again because the template changed).

Manual checks (written down in the pull request with phone, browser and result):
- [ ] iPhone Safari and Android Chrome on the deployed app: swiping right, up and left saves "Rather yes", "Fine with me", "Rather not" (check on the overview); the next card appears.
- [ ] A short drag springs back and saves nothing; dragging down saves nothing.
- [ ] Tapping the three buttons still works; tapping the menu link opens Google Maps and does not rate.
- [ ] Scrolling the page still works when the finger starts outside the card or on the rating buttons, also on a small phone where the card is taller than the screen.
- [ ] With JavaScript turned off in the browser, the hint is not shown and the buttons work.

## Out of scope
- Any change to the voting route, the rating rules, the order of cards, scoring or the overview page.
- Undo of the last swipe (the overview already lets people change a rating), keyboard shortcuts, sound or vibration.
- Swiping in other places (room page, "Been there"), a card stack animation that shows the next card underneath.
- Menu photos or any other new Google field; loading the menu inside the app.
- Any JavaScript library or framework, a build step, new dependencies.
- Changes to `app/schema.sql` or existing tests.

## Done when
- All tests in `tests/test_swipe_rating.py` and all earlier tests pass (`uv run pytest`), output pasted.
- The manual checks above are done on two phones and written in the pull request.
- `AGENTS.md` lists `swipe.js` as allowed (done by D16).
- Work is on branch `feature-a10-swipe-rating`, pushed, pull request opened for review.
