# A11 fix – the creator's start hint counts hidden options too

Branch: `fix-a11-start-hint`
Tests: `tests/test_start_hint_hidden_options.py`

Follows A11 (`specs/a11-hidden-collecting.md`, F28, D17, PR #64) and B6 (`specs/b6-room-page-layout.md`, PR #68), both merged on 2026-11-20. Found while merging the two (review of #68).

## Why
B6 shows the creator's start hints on the room page with `lobby_rules.start_errors(room["status"], len(options))`. Since A11, `options` in `render_room_page` holds only the options this participant may see. In a room with secret ideas or secret places, the creator therefore sees `Add at least 2 options before starting the voting.` although the room has enough options, and `Start voting` then works. The hint must follow the same rule as the start route (A5), which counts every option in the room.

## What
- The start hints on the room page count **every** active option of the room, also those hidden from the creator (other people's secret ideas, secret suggested places). Only the number is used; nothing about the hidden options is shown.
- Rooms without hidden options: unchanged.
- The lobby, the start route and its messages: unchanged.

### Code
- `app/routes/rooms.py`, `render_room_page`: count the options before the A11 filter and pass that number to `lobby_rules.start_errors`. No other change.

Checks (one line = one test), `tests/test_start_hint_hidden_options.py`:
- [ ] Secret ideas: the creator has one own idea and the guest one hidden idea (2 in all) – the creator's room page shows no `Add at least 2 options` hint, and `Start voting` works.
- [ ] Secret ideas: the only option is the guest's hidden idea (1 in all) – the creator's room page still shows `Add at least 2 options before starting the voting.`
- [ ] Secret places: after "Surprise me" with `reveal_places = 0` and no other option, the creator's room page shows no `Add at least 2 options` hint.
- [ ] All earlier tests pass unchanged.

## Out of scope
- Changing what the hints say, showing them to guests, the lobby page.
- Changes to existing tests.

## Done when
- The tests above and all earlier tests pass (`uv run pytest`), output pasted.
- Work is on branch `fix-a11-start-hint`, pushed, pull request opened for review.
