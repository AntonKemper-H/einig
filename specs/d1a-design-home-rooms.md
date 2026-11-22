# D1a – Design: home page, groups and the room page

Branch: `design-1a-home-rooms` (from `design` after D0 is merged, merged back into `design`)
Tests: `tests/test_design_home_rooms.py`

Decision: `docs/decisions.md`, D21. Builds on D0 (`specs/d0-design-foundation.md`). Runs in parallel with D1b; the two tasks share no template and write in different sections of `app.css`.

## Why
The home page is one long list: groups, rooms and the create form one below the other. The room page shows every tool at once (participants, options, setup, searches, add form, invite link, QR code), so the host has to scroll and search. Both should feel like a phone app: a few big buttons, one thing at a time, the main action easy to find.

## What

### Decisions in this spec (please check in the review)
- **Home page:** two big tiles, `My rooms` and `Create a room`, and a smaller `My groups` button below. A tap on a tile shows only that part, with a back control to the tiles. This is done with `<details>` and CSS (`:has()`), **not** with new pages: the reviewed tests require the create form and both lists on the home page (A2, A8, A9). After a rejected create (form shown again with errors), the create part is open.
- **My rooms and My groups lists:** each room or group is one big button (title, then status / members and "You are …"), one below the other.
- **Create a room:** three numbered steps in cards: 1. what to decide, 2. where the options come from (the three modes), 3. your nickname, then the `Create room` button.
- **Room page as host:** a short head (title, one line "Collecting ideas · You are the host"), the options as white cards with a small delete button, the add field right below them with "or find a place on Google Maps" as a smaller link, the room setup as one collapsible card, and **"Start voting" with the time limit at the bottom**. Invite link and QR code are one compact block.
- **Room page as guest:** the same without the host's parts.
- **Surprise and "Places nearby" rooms:** the search card comes first and stands out. Adding one's own idea and finding a place by name stay available (F23 and its tests) but are collapsed into one row `Add your own idea` below the options.
- **Join page (invite link):** the logo large, "You're invited to decide", the room title, then the nickname field and `Join` (or `Join as …` for group members).
- **Group pages** (`group.html`, `new_group.html`) and **404** in the same style.
- **The HTML order stays.** Reviewed tests pin the order in the source (setup line < participants < options < setup form < add form < invite < QR code; the start form inside the participants section). Every new visual order is CSS (`order`, grid). The participants section may be open by default for the creator so the start form can sit at the bottom.
- The time limit and the search filters stay `<select>` fields (the tests check them), styled to fit.

### Code
- `app/templates/home.html`, `room.html`, `group.html`, `new_group.html`, `404.html`, `_place_card.html` only where the room list uses it, and the `/* D1a … */` section of `app.css`.
- No Python change, no JavaScript, no new dependency.

Checks (one line = one test), `tests/test_design_home_rooms.py`:
- [ ] The home page has the three parts (`My rooms`, `Create a room`, `My groups`) as `<details>` blocks, and still contains the create form and both lists (A2, A8, A9 stay green).
- [ ] After a rejected create, the `Create a room` part is open and shows the errors.
- [ ] In a surprise room the add form and the find form are inside a collapsed `<details>` named `Add your own idea`; in a manual room they are not collapsed.
- [ ] The room page keeps its source order (as B6's tests) and the start form stays in the participants section.

All existing tests stay green and unchanged. Checked in the browser at 380 px and 1280 px, light and dark, before and after screenshots in the PR.

## Not in this task
- Rating page, lobby, result (D1b). Any change to routes, forms or the texts tests check.
