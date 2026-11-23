# U3 – Invite in one tap, and groups first

Branch: `ux-3-invite-groups` (built on top of U1 and U2: all three change `room.html`)
Tests: `tests/test_u3_invite_groups.py` (new); **one reviewed test changed** (see below).
Decision: `docs/decisions.md`, D28; `AGENTS.md` (list of JavaScript files). Proposal: issue #95 (Timon).

## Why
Inviting friends today means opening a fold, copying a link and pasting it into a chat. And the home page shows the groups last, although "same people again" is the quickest way to start.

## What
- **An Invite block on the room page** (while the room is not closed) **and on the group page** (members only):
  - a button **Invite** that opens the phone's own share menu (Web Share API) with the invite link. It is hidden until `invite.js` finds `navigator.share`;
  - **without JavaScript or without the Web Share API** the same place shows plain links: **WhatsApp · Mail · SMS** (like the share links of the result, B7/D18; WhatsApp through its app link `whatsapp://send`, because a reviewed test wants no `https://` on the room page). The message holds only the room or group name and the invite link, never nicknames or votes.
  - The invite link and the QR code stay folded below as before (a reviewed test pins them).
- **`app/static/js/invite.js` (new, allowed by D28):** about 15 lines; it only calls `navigator.share` after a tap and sends nothing anywhere itself.
- **Home page:** the groups come first (visual order in CSS only; the HTML order stays as the reviewed A2/A8/A9 tests want). Each group tile has a **New decision** button that opens the group page at its *Plan a new activity* form.
- No new route, no database change, no new dependency.

## Reviewed test that changes (needs the team's OK, flagged in the PR)
`tests/test_location_messages.py::test_no_new_javascript_file_was_added` pins the JavaScript folder to `{geolocation.js, swipe.js}`. With `invite.js` it expects the set plus `invite.js`. The JavaScript is its **own commit**, so the team can drop it and keep the plain links.

## Checks (one line = one test), `tests/test_u3_invite_groups.py`
- [ ] A participant's room page has the Invite button (hidden) and the three links with the room name and the invite link, and still the folded link and QR code.
- [ ] A visitor and a closed room show no Invite block.
- [ ] A group member's group page has the same block with the group's invite link; a non-member sees none.
- [ ] The invite message contains no nicknames.
- [ ] `invite.js` exists, calls `navigator.share`, is loaded by both pages, and the JavaScript folder holds exactly the three files.
- [ ] A group tile on the home page has a New decision link to the group page's plan form (`#plan`); that form has the id.
- [ ] The stylesheet puts the groups first on the home page; the HTML order is unchanged.
