# A6 – F22 QR code for the invite link

Branch: `feature-a6-qr-code`
Tests: `tests/test_qr_code.py`

## Why
When the group sits at the same table, typing or sending the invite link is slower than pointing a phone camera at a screen. A QR code of the invite link lets everyone join in seconds; without JavaScript it has to be drawn on the server.

## What
F22 in `docs/concept.md`: a QR code display for joining at the same table. `docs/concept.md` §4, step 2: the app generates an invite link and a QR code.

**How the QR code is made.**
- New pinned dependency `segno==1.6.6` (pure Python, no other dependencies; approved by the team on 2026-11-15). It draws the QR code as SVG text, so no image file, no image library and no JavaScript is needed.
- `app/services/qr.py`: `invite_qr_svg(invite_url: str) -> str` returns `segno.make(invite_url, error="m").svg_inline(scale=4, title="QR code to join this room")`. Error level `m` still reads when part of the code is covered or the screen reflects. No Flask, no database.
- The QR code holds exactly the invite URL that A2 shows as text (`url_for("rooms.show_room", room_id=…, _external=True)`), nothing else.
- The SVG is put straight into the HTML (inline). It is marked safe in Jinja because it comes only from `segno` and our own URL, never from user input (the room id is a random `token_urlsafe`, the title is a fixed text). No external image or service is used (`AGENTS.md`, privacy: no external resources).

**Where it is shown.**
- Room page (`GET /rooms/<room_id>`) for a joined participant (creator or not), next to the invite link, inside a `<figure>` with the caption `Scan to join this room.`
- Lobby (`GET /rooms/<room_id>/lobby`) for a joined participant, with the same figure, because that is the screen the group looks at while waiting for others.
- Only while the room is `collecting` or `voting`. A `closed` room cannot be joined (A3), so neither page shows the QR code then.
- Visitors who have not joined see no QR code (they are already on the join page).

Checks (one line = one test):
- [ ] `invite_qr_svg(url)` returns an SVG (`<svg …>…</svg>`) with the title `QR code to join this room`.
- [ ] `invite_qr_svg(url)` is exactly `segno.make(url, error="m").svg_inline(scale=4, title="QR code to join this room")`, so the code holds the given URL.
- [ ] Different URLs give different QR codes; the same URL always gives the same QR code.
- [ ] `services/qr.py` imports neither Flask nor `app.db`.
- [ ] Room page: the creator and a joined participant see the QR code of this room's invite URL and the caption `Scan to join this room.`
- [ ] Lobby: a joined participant sees the same QR code and caption.
- [ ] Two rooms show two different QR codes, each for its own invite URL.
- [ ] The QR code is shown while `collecting` and `voting`; when `closed`, neither the room page nor the lobby shows it.
- [ ] A visitor who has not joined sees no QR code on the room page.
- [ ] The QR code is inline SVG: the page loads no external image (`<img` with `http`) and no script for it.
- [ ] Rejected: a room title with HTML is still shown escaped on a page with the QR code (marking the SVG safe does not unescape anything else).

(No "survives a restart" line: nothing is stored. The QR code is drawn fresh from the invite URL on every page view.)

## Out of scope
- A download or print button for the QR code, a QR code as a PNG file or as a separate route.
- Changing how the invite URL is built (e.g. forcing `https` behind Render's proxy); the QR code uses the same URL as the text link.
- Any JavaScript (copy button, camera scanning).
- The QR code on any other page (rating, result).
- No changes to `app/schema.sql` or to existing tests.

## Done when
- All tests in `tests/test_qr_code.py` and all earlier tests pass (`uv run pytest`), output pasted.
- The QR code on the room page opens the room when scanned with a phone camera (checked by hand).
- `segno` is pinned in `pyproject.toml` and `uv.lock`.
- Work is on branch `feature-a6-qr-code`, pushed, pull request opened with mkim-nova as reviewer.
