# U4 – Rating buttons as icons, a "?" for help, labels on the first card

Branch: `ux-4-rating-icons`
Tests: `tests/test_rating_icons.py` (new); 5 reviewed tests change with the team's OK (list below).
Decision: `docs/decisions.md`, D27 (supersedes the "no buttons in sight" part of D20 and the hint row of D1b).
Proposal: issue #86 (part 1), discussed on 2026-11-23. **For after the submission;** not merged before 20:00 on 2026-11-23.

## Why
On the rating card you can only swipe; the buttons are hidden (D20) and a text row under the card explains the four directions. Testers did not see at a glance what to do. A row of four icon buttons under the card (as in dating apps) shows the choices and doubles as the swipe legend: left button = swipe left, right button = swipe right.

## What

### Decisions in this spec (please check in the review)
- **The rating buttons and the joker button become visible again** on the one-card rating page, as one row of round icon buttons under the card, inside the card's `<article>` (swipe.js looks for them there). From left to right: **✕ Rather not · 🚫 Joker · 🤷 Fine with me · ♥ Rather yes**. ✕ is on the side you swipe for "no", ♥ on the side for "yes"; the two middle buttons are the two vertical swipes (down = joker, up = fine).
- **Same forms, same fields, no route change.** The three rating buttons stay in their one form with `name="rating"` (so swipe.js keeps pressing them, unchanged); the joker stays its own form without `name="rating"`, so a swipe can still never use the joker (B4, D20). The visual order (joker between ✕ and 🤷) is done in CSS (`display: contents` on the two forms inside one flex row, `order` on the buttons); the HTML order stays.
- **Each button:** the icon (`aria-hidden="true"`) and below it the label in small text: `Rather not`, `Joker`, `Fine with me`, `Rather yes`. The joker button keeps its full text `Use my joker on this option (cannot be undone)` for screen readers (visually hidden), after the visible word `Joker`.
- **Labels only on the first card:** while this participant has rated nothing yet in this room (no row in `votes` for them), the small labels are shown under the icons and one line above the row says `Tap a button or swipe the card.` From the second card on, the labels are visually hidden (still read by screen readers) and the line is gone. Server-side, from the database; **no cookie and no JavaScript**, so "first use" means "first card in each room".
- **A "?" in the card line,** next to the ⋯ menu: a `<details data-rating-help>` with the summary `?` (`aria-label="How rating works"`). Opened, it shows:
  - `✕ Rather not – counts −4`
  - `🤷 Fine with me – counts +1`
  - `♥ Rather yes – counts +2`
  - `🚫 Joker – rules this option out; once per room` (left out once the joker is used)
  - `Swipe: right = Rather yes, up = Fine with me, left = Rather not, down = Joker` (`down = Joker` left out once used)
  The points come from `scoring.POINTS`, not written twice.
- **The text row under the card (`data-swipe-legend`, D1b) is removed;** the icon row takes its place. The old visually hidden hint line `data-swipe-hint` stays unchanged (pinned by A10/C11 tests).
- **Without JavaScript** the row is visible and works, as before (the buttons were already visible without JavaScript).
- **Once the joker is used,** its button is not shown (as today, the joker form is left out); the row has three buttons.
- **The overview after the last card** is unchanged (text buttons per option).

### Tests changed with the team's OK
- `test_design_vote_result.py`: `test_the_swipe_hints_sit_under_the_card_as_hidden_from_screen_readers_text` and `test_the_joker_hint_is_left_out_once_the_joker_is_used` (D1b's hint row is gone: they now check the icon row in its place and that the joker button is left out once used); `test_d1b_styles_are_only_in_the_d1b_section` (`swipe-legend` leaves `D1B_ONLY_SELECTORS`, nothing else changes).
- `test_fullscreen_card.py`: `test_the_css_hides_the_buttons_visually_and_shows_them_on_focus_within` and `test_the_buttons_are_hidden_only_once_swipe_js_has_started` (D20's visually hidden buttons: they now check that the buttons are **not** clipped, also not under `.swipe-ready`).
No test is removed or skipped; `test_no_hint_row_on_the_overview_after_all_options_are_rated` stays true unchanged.

## Checks (one line = one test), `tests/test_rating_icons.py`
- [ ] The rating card has one row (`data-rating-row`) inside `<article data-swipe-card>` with the three rating buttons (`name="rating"`, values `no`, `ok`, `yes`) and the joker button, with the icons ✕, 🤷, ♥, 🚫, each icon `aria-hidden="true"`.
- [ ] The rating form and the joker form keep their actions, hidden `option_id` field and button types; the joker button has no `name="rating"`.
- [ ] The CSS orders the row ✕, 🚫, 🤷, ♥ and never clips or hides the rating or joker buttons (also not under `.swipe-ready`).
- [ ] First card (nothing rated yet): labels visible (`data-rating-labels="shown"`) and `Tap a button or swipe the card.` on the page.
- [ ] After one rating, the next card has `data-rating-labels="hidden"`, the labels are still in the HTML (screen readers), the hint line is gone.
- [ ] The "?" panel: summary `?` with `aria-label="How rating works"`; the five lines with the points from `scoring.POINTS`.
- [ ] Once the joker is used: no joker button, and the "?" panel leaves out the joker line and `down = Joker`.
- [ ] No `data-swipe-legend` on the rating card any more.
- [ ] The overview after all options are rated is unchanged (text buttons, no icon row, no "?").
- [ ] Rating by pressing an icon button still saves the vote and redirects (Post/Redirect/Get); the joker button still saves the veto.
- [ ] Persistence: after an app restart, a participant who already rated sees the labels hidden.

## Out of scope
- U1 (joker as a button with a counter, "Again with the same people"), removing rooms by swiping (#86 part 2; E3 already has buttons).
- Changing swipe.js, the routes, the rating labels (`voting.RATING_LABELS`), the scoring, or the overview page.
- A tutorial with several steps or an overlay; remembering "seen the help" across rooms (would need a cookie field, AGENTS.md "Privacy").
- New JavaScript.

## Done when
- All tests pass (`uv run pytest`), output pasted.
- On a phone (380 px): the card plus the icon row fit without scrolling; swipe and tap both work; the "?" opens and closes.
- Work is on branch `ux-4-rating-icons`, pushed, pull request opened; spec and tests reviewed by Anton and Mika **before** the implementation.
