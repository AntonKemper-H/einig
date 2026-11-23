# E7 – The creator's lobby does not reload by itself while collecting

Branch: `fix-lobby-host-refresh`
Tests: `tests/test_lobby_host_refresh.py` (new); two A5 tests in `tests/test_lobby.py` changed with the team's OK.
Decision: `docs/decisions.md`, D25.

## Why
Found while testing on a phone (2026-11-23): the lobby reloads every 4 seconds (meta refresh, AGENTS.md). The creator picks the time limit in the lobby's start form, and every reload set the choice back to "No time limit" before they could press "Start voting". So a room could start without the limit the creator had picked. Without JavaScript a page cannot keep an unsent choice across a reload.

## What
- **The creator's lobby while the room is collecting** has no meta refresh. It shows a **Refresh** button (a link to the lobby) instead, as the room page does since B6 for the same reason.
- **Everybody else** (guests) keeps the automatic reload while collecting, and **everybody** reloads automatically while voting. A closed room never reloads (as before).
- A rejected start (shown as the answer to `POST /start`) is the creator's collecting lobby, so it has the Refresh button and no meta refresh; the button leads to the lobby, never back to `/start`.
- No change to routes, the start form, the time limits or the database. No JavaScript.

## Tests changed with the team's OK (Mika, Timo, Anton – 2026-11-23)
- `test_lobby_refreshes_while_room_is_open`: checks the guest while collecting and both while voting (it checked only the creator before).
- `test_rejected_start_refreshes_to_lobby_not_to_start`: checks that there is no meta refresh and a link to the lobby (it checked the meta refresh before). Its point – never reload `/start` – stays.

## Checks (one line = one test), `tests/test_lobby_host_refresh.py`
- [ ] The creator's lobby while collecting has no meta refresh, has the Refresh button to the lobby, and still has the time limit choice.
- [ ] A guest's lobby while collecting keeps the meta refresh and has no Refresh button.
- [ ] While voting, creator and guest both have the meta refresh and no Refresh button.
- [ ] In a closed room nobody has a meta refresh.
- [ ] A rejected start shows the Refresh button, no meta refresh, and nothing points to `/start`.
