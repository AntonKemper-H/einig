# D1b – Design: rating card, lobby and result

Branch: `design-1b-vote-result` (from `design` after D0 is merged, merged back into `design`)
Tests: `tests/test_design_vote_result.py`

Decision: `docs/decisions.md`, D21. Builds on D0 (`specs/d0-design-foundation.md`) and keeps everything C11 decided (D20). Runs in parallel with D1a; the two tasks share no template and write in different sections of `app.css`.

## Why
The rating card already fills the screen and can be swiped (C11), but it looks like a plain white box. The lobby and the result page are plain lists. They should look like the rest of the redesigned app and give clear feedback: what a swipe does, who is done, who won.

## What

### Decisions in this spec (please check in the review)
- **Swiping stays exactly as it is** (D16, D20): right = "Rather yes", up = "Fine with me", left = "Rather not", down = joker question, tap = turn the card. Distances, timing and the buttons `swipe.js` presses do not change.
- **Rating card front:** a large white card with rounded corners and a shadow; photo on top (Google places), name and small fact pills below.
- **Stamp while dragging:** `swipe.js` shows a stamp on the card while it is dragged (`RATHER YES`, `RATHER NOT`, `FINE WITH ME`, `JOKER?`), growing with the distance. Only a class and a text on an element that is already in the page; nothing else in `swipe.js` changes.
- **Rating buttons stay visually hidden while swiping works** (D20, `test_the_buttons_are_hidden_only_once_swipe_js_has_started`), decided 2026-11-22. Under the card a small row of swipe hints is shown instead: `← Rather not · ↑ Fine with me · Rather yes →` and `↓ Joker`. The hints are text, not buttons, and `aria-hidden`, because the hidden buttons already serve the keyboard and screen readers. Without JavaScript the buttons show as today (D16).
- **Back of the card** (pages About / Photos / Reviews with dots): same content, new look.
- **The card menu** (`Menu`: back to the lobby, the creator's close button): a round `⋯` button that opens a small white panel.
- **Lobby:** a ring with "2/3 done", the participant list with a green `Done` or grey `Still adding` pill, and at the bottom either "Waiting for the host to start the voting." or the big `Rate the options` button. The meta refresh stays.
- **Result:** the winner as a large card with a yellow `Winner` pill, the map, `Open route in Google Maps`; `Share in WhatsApp` and `Add to calendar` as two tiles (the calendar fields open on tap); "How the options were rated" as one card per option with a coloured bar (yes / fine / not) plus the counts as text. Still anonymous (AGENTS.md).

### Code
- `app/templates/vote.html`, `_place_card.html` (card front and back), `lobby.html`, `result.html`, `_qr_code.html`, `app/static/js/swipe.js` (stamp only), and the `/* D1b … */` section of `app.css`.
- No Python change, no new JavaScript file, no new dependency.

Checks (one line = one test), `tests/test_design_vote_result.py`:
- [ ] The rating card has one stamp element, empty and hidden when the page loads.
- [ ] `swipe.js` still presses the same rating buttons for right, up and left (C11's tests stay green).
- [ ] The result page shows one bar per option, and the counts as text next to it.
- [ ] The lobby still has the meta refresh and shows each participant's done state.

All existing tests stay green and unchanged. Checked in the browser at 380 px and 1280 px, light and dark, before and after screenshots in the PR.

## Not in this task
- Home, groups and room page (D1a). Any change to routes, forms, scoring or the texts tests check.
