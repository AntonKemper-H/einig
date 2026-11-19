# B6 – Room page layout: one calm page instead of room page + lobby

Branch: `feature-b6-room-page-layout`
Tests: `tests/test_room_page_layout.py`

Decision: `docs/decisions.md`, D17 ("Room page layout"). Built after **C9** is merged (the setup section is part of the page). Mostly templates and CSS; routes only pass a little more data.

## Why
The room page is long: the invite link is shown twice and comes first, every Google place is a full card with photo, and to see who has joined people must switch to the lobby. The page should show what matters while collecting (setup, own options, who is there) in a short list, open details only on tap, and keep invite link and QR code at the end, without JavaScript and without breaking any reviewed test.

## What

### Decisions in this spec (please check in the review)
- **Collapsible without JavaScript:** `<details>`/`<summary>`, built into every browser, for the participant list and for each Google place.
- **Order of the page for a joined participant:** title and "You joined as …" → setup line (C9) → participants (collapsed) → options → creator's setup form (C9) → search forms → add form → "I'm done – wait for the others" → invite link and QR code (at the end).
- **The creator's setup form stays below the options** *(changed when the tests were written, needs the reviewer's OK)*: A4's reviewed test `test_options_appear_on_room_page_in_order_added` finds the option names with `html.index(...)`. The kind names in the setup form's select ("Cinema", "Bowling", …) would come first if the form stood above the options, and that test would fail. So only the one-line setup text sits at the top; the form stays where C9 put it.
- **Participants on the room page:** `<details>` with the summary `Participants (3 · 1 done)`; inside, the list as in the lobby (nickname, `(creator)`, `– done`). For the creator, inside the same section, the start hints and the `Start voting` form (the same form and route as in the lobby, A5, including B5's time-limit choice `time_limit`, which was added after this spec was written). Nothing about votes.
- **Not live:** the room page never reloads itself (a reload would wipe what someone is typing; a reviewed test checks there is no refresh). The section has a link `Refresh` to the room page itself.
- **The lobby stays as the waiting page** and is unchanged (its reviewed tests stay). The room page links to it as `I'm done – wait for the others`; this link replaces "Go to the lobby to see who has joined".
- **Options compact:** a Google option is `<details>` with the place name as summary and the C2b card inside (photo, facts, attribution); a manual option is a plain list item with its label. *(Added when the tests were written:)* a Google option whose details are missing ("Place from Google Maps", "Details are not available right now.") is shown as the plain C2b card, without `<details>`: there is nothing to open, and repeating the fallback name in a summary would break the reviewed tests that count it (`test_place_cards.py`, `test_places_search.py`, `test_surprise_search.py`). "Been there" (C5) and "Delete" (A7) stay next to each option, outside the `<details>`, so they are reachable without opening it.
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
- [ ] When Ben is done, the summary reads `Participants (2 · 1 done)` and Ben has `– done`, Anna does not.
- [ ] The creator's participants section contains the `Start voting` form posting to `/rooms/<id>/start`; a guest's does not.
- [ ] That form also has B5's time-limit choice (`<select name="time_limit">` with `""`, `15`, `30`, `60`), and starting from the room page with `time_limit=30` stores a deadline.
- [ ] The setup line comes before the participants section; the creator's setup form comes after the options list.
- [ ] Starting the voting from the room page works (redirect, room status `voting`), and a rejected start (too few options) shows the message.
- [ ] The section has a `Refresh` link to the room page; the room page still has no meta refresh.
- [ ] The room page links to the lobby with the text `I'm done – wait for the others`.
- [ ] A Google option is inside a `<details>` whose `<summary>` is the place name, with the card (photo URL, facts) inside; a manual option is not inside a `<details>`.
- [ ] A Google option without details (fallback) is the plain card, not inside a `<details>`, and "Place from Google Maps" appears once per such option.
- [ ] "Been there" and "Delete" buttons are outside the option's `<details>`, and still work.
- [ ] The invite field and the QR code come after the options and the add form in the HTML (position check).
- [ ] The invite URL appears in exactly one block at the end (field and small link in the same element).
- [ ] Number of Place Details calls for a room page with 3 Google options is still 3.
- [ ] A visitor still sees only the join form; a closed room still shows the closed text (unchanged).
- [ ] No page shows who voted what or who added which option.
- [ ] All earlier tests pass unchanged, in particular `test_lobby.py`, `test_proxy_headers.py`, `test_qr_code.py`, `test_place_cards.py`.

Manual checks (in the pull request): on a phone (≈ 380 px) no horizontal scrolling, participants at the top, places open on tap; on a laptop (≥ 900 px) participants in the side column.

## Changes to reviewed tests (need the reviewers' OK, `AGENTS.md`)

Found when the tests were written: two reviewed tests check that a participant's nickname appears **nowhere** on the room page, as a stand-in for "nobody sees who added which option". With the participants list on the room page (decided in D17), every nickname appears there. Both tests now remove the participants section first and then check that the name appears nowhere else, so they still prove that no option shows its author. Own commit, no other change:

- `tests/test_delete_option.py::test_author_is_not_shown_to_others` (A7: written by AntonKemper-H, reviewed by mkim-nova)
- `tests/test_place_by_name_route.py::test_picker_is_stored_as_author_and_not_shown` (C6: written by mkim-nova, reviewed by Timonhio)

Both changed tests still pass on today's `main`.

## Out of scope
- Removing the lobby or its route, changing the lobby page.
- Live updates on the room page, JavaScript of any kind, a "copy link" button (needs JavaScript).
- Changing the C2b card macro, the rating page or the result page.
- Hiding other participants' options (A11).
- Colours, logo and the general look of the app (separate design work).
- Changing any other reviewed test (also `invite_urls_in` in `tests/test_proxy_headers.py`).

## Done when
- All tests in `tests/test_room_page_layout.py` and all earlier tests pass (`uv run pytest`), output pasted.
- Manual checks on a phone and a laptop written in the pull request, with a screenshot of each.
- Work is on branch `feature-b6-room-page-layout`, pushed, pull request opened for review.
