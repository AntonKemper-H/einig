# B6 – Room page layout: one calm page instead of room page + lobby

Branch: `feature-b6-room-page-layout`
Tests: `tests/test_room_page_layout.py`

Decision: `docs/decisions.md`, D17 ("Room page layout"). Built after **C9** is merged (the setup section is part of the page). Mostly templates and CSS; routes only pass a little more data.

## Why
The room page is long: the invite link is shown twice and comes first, every Google place is a full card with photo, and to see who has joined people must switch to the lobby. The page should show what matters while collecting (setup, own options, who is there) in a short list, open details only on tap, and keep invite link and QR code at the end, without JavaScript and without breaking any reviewed test.

## What

### Decisions in this spec (please check in the review)
- **Collapsible without JavaScript:** `<details>`/`<summary>`, built into every browser, for the participant list and for each Google place.
- **Order of the page for a joined participant:** title and "You joined as …" → setup line / creator's setup form (C9) → participants (collapsed) → options → add form and search forms → "I'm done – wait for the others" → invite link and QR code (at the end).
- **Participants on the room page:** `<details>` with the summary `Participants (3 · 1 done)`; inside, the list as in the lobby (nickname, `(creator)`, `– done`). For the creator, inside the same section, the start hints and the `Start voting` form (the same form and route as in the lobby, A5). Nothing about votes.
- **Not live:** the room page never reloads itself (a reload would wipe what someone is typing; a reviewed test checks there is no refresh). The section has a link `Refresh` to the room page itself.
- **The lobby stays as the waiting page** and is unchanged (its reviewed tests stay). The room page links to it as `I'm done – wait for the others`; this link replaces "Go to the lobby to see who has joined".
- **Options compact:** a Google option is `<details>` with the place name as summary and the C2b card inside (photo, facts, attribution); a manual option is a plain list item with its label. "Been there" (C5) and "Delete" (A7) stay next to each option, outside the `<details>`, so they are reachable without opening it.
- **Invite link:** at the end of the page, in one block with the QR code. A reviewed test (`tests/test_proxy_headers.py`, `invite_urls_in`) requires both the read-only text field and a link with the URL as text. Decided in the review of D17: **both stay**, in one compact block: the text field with the label `Invite link`, the link below it in small text. `invite_urls_in` is not changed.
- **Wide screens:** at a viewport width of at least 900 px, the participants section sits in a right-hand column next to the options (CSS grid in the stylesheet); on a phone it stays at the top. Same HTML, CSS only.
- **Photos inside closed `<details>`** keep `loading="lazy"`, so most browsers load them only when the place is opened. No extra Google calls compared to C2b (one Place Details call per Google option per page view, as today; the name in the summary needs it anyway).

### Template and route changes
- `room.html` reordered and changed as above; the C2b `place_card` macro is reused inside `<details>`; the summary shows the card's name (or `Place from Google Maps` if details are missing).
- `show_room` passes the participants, the finished count and, for the creator, the start hints (the same data the lobby uses, via the existing `app/services/lobby.py` functions; no new SQL).
- A rejected `Start voting` from the room page shows the lobby with the message, as today (the form posts to the same route).
- CSS in `app/static/css/` (existing app stylesheet): spacing of the list, the two-column grid at ≥ 900 px, a compact invite block. No external CSS, no new dependency.

Checks (one line = one test), `tests/test_room_page_layout.py`:
- [ ] A joined participant's room page has a `<details>` whose summary reads `Participants (2 · 0 done)` and lists every nickname with `(creator)` for the creator.
- [ ] The creator's participants section contains the `Start voting` form posting to `/rooms/<id>/start`; a guest's does not.
- [ ] Starting the voting from the room page works (redirect, room status `voting`), and a rejected start (too few options) shows the message.
- [ ] The section has a `Refresh` link to the room page; the room page still has no meta refresh.
- [ ] The room page links to the lobby with the text `I'm done – wait for the others`.
- [ ] A Google option is inside a `<details>` whose `<summary>` is the place name, with the card (photo URL, facts) inside; a manual option is not inside a `<details>`.
- [ ] "Been there" and "Delete" buttons are outside the option's `<details>`, and still work.
- [ ] The invite field and the QR code come after the options and the add form in the HTML (position check).
- [ ] The invite URL appears in exactly one block at the end (field and small link in the same element).
- [ ] Number of Place Details calls for a room page with 3 Google options is still 3.
- [ ] A visitor still sees only the join form; a closed room still shows the closed text (unchanged).
- [ ] No page shows who voted what or who added which option.
- [ ] All earlier tests pass unchanged, in particular `test_lobby.py`, `test_proxy_headers.py`, `test_qr_code.py`, `test_place_cards.py`.

Manual checks (in the pull request): on a phone (≈ 380 px) no horizontal scrolling, participants at the top, places open on tap; on a laptop (≥ 900 px) participants in the side column.

## Out of scope
- Removing the lobby or its route, changing the lobby page.
- Live updates on the room page, JavaScript of any kind, a "copy link" button (needs JavaScript).
- Changing the C2b card macro, the rating page or the result page.
- Hiding other participants' options (A11).
- Colours, logo and the general look of the app (separate design work).
- Changing any reviewed test (also `invite_urls_in` in `tests/test_proxy_headers.py`).

## Done when
- All tests in `tests/test_room_page_layout.py` and all earlier tests pass (`uv run pytest`), output pasted.
- Manual checks on a phone and a laptop written in the pull request, with a screenshot of each.
- Work is on branch `feature-b6-room-page-layout`, pushed, pull request opened for review.
