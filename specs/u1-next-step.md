# U1 – One next step at a time

Branch: `ux-1-next-step` (built on top of U2, because both change `room.html`)
Tests: `tests/test_u1_next_step.py` (new). No reviewed test is changed.
Decision: `docs/decisions.md`, D27. Proposal: issue #95 (Timon).

## Why
The app should show what to do, not explain it. On the room page the next step depends on the state, but it was spread over several places.

## What
- **One main step at the top of the room page** (for participants, right after the lines about who you are), depending on the state:
  - creator while collecting: a big **Start voting** button that jumps to the start form (`#start-voting`);
  - guest while collecting: the text *Waiting for the creator to start*, no button;
  - while voting: **Rate now** (a link to the rating page), or *Waiting for N more* once you are done;
  - closed: **See the result**.
  Visitors who have not joined see none of these.
- **Joker counter on the rating card:** the slim line above the card shows `Joker · 1 left` or `Joker · used`.
- **Result page:** a button **Again with the same people** for a member of the room's group: it posts to the existing route `POST /groups/<id>/rooms` with the room's title and mode, so the same people get a new room. For everybody else a link **Create a new room** to the home page.
- No new route, no database change, no JavaScript.

## Where this differs from issue #95 (and why)
- The start form (with the time limit) **stays inside the participants section**: a reviewed B6 test pins it there. The new Start voting button therefore jumps to it; the section is already open for the creator.
- The joker button keeps its text *Use my joker on this option (cannot be undone)*: two reviewed tests (`test_joker.py`, `test_fullscreen_card.py`) pin it and the swipe confirmation needs it. The counter is a new line instead.

## Checks (one line = one test), `tests/test_u1_next_step.py`
- [ ] The creator sees Start voting at the top (a link to the start form that exists on the page) while collecting.
- [ ] A guest sees *Waiting for the creator to start* and no Start voting.
- [ ] While voting a participant sees Rate now linking to the rating page.
- [ ] Once done, a participant sees *Waiting for N more* and no Rate now.
- [ ] A closed room shows See the result.
- [ ] A visitor who has not joined sees no main step.
- [ ] The rating page shows `Joker · 1 left`, and `Joker · used` after the joker was used.
- [ ] The result page of a group room shows Again with the same people to a member, and posting it creates a room in the group with the same title and mode.
- [ ] The result page of a room without a group links to Create a new room.
