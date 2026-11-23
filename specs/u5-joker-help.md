# U5 – Explain the joker on the rating card

Branch: `ux-5-joker-help`
Tests: `tests/test_joker_help.py` (new). **No reviewed test changes.**
Decision: none needed (no rule changes; F10 and D20 stay as they are).
Builds on U1 (the counter `Joker · 1 left` / `Joker · used` in the card line, D27).

## Why
The joker is not explained anywhere in the app. The card line says `Joker · 1 left`, but nobody learns what a joker does, that there is only one per room, or how to use it. A short explanation one tap away fixes that without changing the card, the buttons or swiping.

## What
- **The counter becomes a small `<details data-joker-help>`** in the card line. Its `<summary>` is the counter text from U1 (`Joker · 1 left` / `Joker · used`, unchanged) plus a small `?` (`aria-hidden="true"`) and, for screen readers, the visually hidden text `What is the joker?`.
- **Opened, it shows a panel** in the same style as the ⋯ menu panel (`menu-panel`):
  - while the joker is free:
    - `Your joker takes this option out for the whole group (unless every option gets a joker).`
    - `You have one joker per room. It can't be undone.`
    - `To use it, swipe the card down or tap the joker button.`
  - once used:
    - `You used your joker in this room.`
    - `Your joker takes that option out for the whole group (unless every option gets a joker).`
- Only this participant's own joker is mentioned (as today). Nothing reveals who else used a joker.
- **No JavaScript** (`<details>` opens without it), no new file, `swipe.js` unchanged. The rating buttons, the joker button, the joker question (D20), the ⋯ menu and all routes stay as they are.
- The overview after the last card is unchanged (it has no card line).

## Checks (one line = one test), `tests/test_joker_help.py`
- [ ] The card line holds `<details data-joker-help>` whose summary contains `Joker · 1 left`, a `?` inside an `aria-hidden="true"` element, and `What is the joker?` in a `visually-hidden` element.
- [ ] The panel (`menu-panel`) shows the three lines for a free joker.
- [ ] After using the joker: the summary contains `Joker · used`, the panel shows the two lines for a used joker and not `To use it, swipe the card down or tap the joker button.`
- [ ] The ⋯ menu is still there with its lobby link (the details element is a second one, not a replacement).
- [ ] The help is only on the one-card rating page, not on the overview after the last card.
- [ ] A guest who has not used the joker still sees `Joker · 1 left` and the free-joker lines after the creator used theirs (nothing about others' jokers).
- [ ] The page still has only the scripts it had before (no new `<script>`).

## Out of scope
- U4 (rating buttons as icons, "?" for all ratings): after the submission.
- Showing the points, changing the joker button, the joker question or swiping.
- Explaining the joker anywhere else (room page, lobby).

## Done when
- All tests pass (`uv run pytest`), output pasted.
- On a phone (380 px): the counter opens and closes the panel; swiping and the ⋯ menu still work.
- Work is on branch `ux-5-joker-help`, pushed, pull request opened; spec and tests reviewed by Anton before the implementation.
